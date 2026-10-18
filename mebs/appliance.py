"""Dedicated image runtime. First USB = destination, second USB = source.

Never formats media. Requires the image marker and root; not a host automounter.
Only one filesystem per disk is accepted. Destination must currently be ext4.
"""
import ctypes
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import time

from .backup import BackupError, Cancelled, backup, verify
from .devices import Roles, usb_disks


def command(*args):
    # Buildroot's init shell need not export PATH; /sbin is omitted from Python's
    # default exec search path even though blockdev is installed there.
    binary = "/sbin/blockdev" if args[0] == "blockdev" else args[0]
    return subprocess.run((binary, *args[1:]), check=True, capture_output=True, text=True, timeout=30)


def disk_identity(disk):
    """Kernel insertion sequence prevents reusing a removed disk's major:minor."""
    node = os.stat(disk["path"], follow_symlinks=False)
    if not stat.S_ISBLK(node.st_mode):
        raise BackupError("블록 장치가 아닙니다.")
    major_minor = f"{os.major(node.st_rdev)}:{os.minor(node.st_rdev)}"
    if major_minor != disk["id"]:
        raise BackupError("저장장치 식별 정보가 바뀌었습니다.")
    sysnode = Path("/sys/dev/block") / major_minor
    if not (sysnode / "diskseq").is_file():
        raise BackupError("장치 연결 순번을 확인할 수 없습니다.")
    sequence = (sysnode / "diskseq").read_text().strip()
    if not sequence.isdigit():
        raise BackupError("장치 연결 순번이 잘못되었습니다.")
    return f"{major_minor}:{sequence}"


def inventory():
    disks = usb_disks()
    for disk in disks:
        disk["token"] = disk_identity(disk)
    return disks


def volume(disk, destination=False):
    """Reject already mounted, multi-partition, stacked or unknown media."""
    children = disk.get("partitions", [])
    nodes = [disk, *children]
    if any(any(n.get("mountpoints") or []) for n in nodes):
        raise BackupError("이미 사용 중인 저장장치입니다. 자동 백업을 중단합니다.")
    if len(children) > 1 or any(n.get("children") for n in children):
        raise BackupError("여러 파티션/중첩 장치는 아직 지원하지 않습니다.")
    node = children[0] if children else disk
    if children and node.get("type") != "part":
        raise BackupError("일반 파티션이 아닌 장치입니다.")
    fs = node.get("fstype")
    allowed = ("ext4",) if destination else ("vfat", "exfat", "ntfs", "ext4")
    if fs not in allowed:
        raise BackupError("외장 하드는 ext4 형식이 필요합니다. 자동 포맷하지 않습니다." if destination
                          else "지원하지 않는 SD 파일시스템입니다.")
    if destination and (disk.get("readonly") or node.get("ro")):
        raise BackupError("백업 외장 하드가 읽기 전용입니다.")
    return {"path": node.get("name", disk["path"]), "fstype": fs,
            "id": node.get("maj:min", disk["id"])}


class Mounts:
    def __init__(self, root="/run/mebs", run=command):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.run = run
        self.mounted = []

    def mount(self, disk, selected, role):
        if disk_identity(disk) != disk["token"]:
            raise BackupError("장치가 교체되었습니다.")
        node = os.stat(selected["path"], follow_symlinks=False)
        if (not stat.S_ISBLK(node.st_mode) or
                f"{os.major(node.st_rdev)}:{os.minor(node.st_rdev)}" != selected["id"]):
            raise BackupError("파티션 식별 정보가 바뀌었습니다.")
        mountpoint = self.root / role
        mountpoint.mkdir(mode=0o700, exist_ok=True)
        if mountpoint.is_symlink() or os.path.ismount(mountpoint) or any(mountpoint.iterdir()):
            raise BackupError("안전하지 않은 마운트 경로입니다.")
        source = role == "source"
        fs = selected["fstype"]
        options = "ro,nosuid,nodev,noexec,noatime" if source else "rw,nosuid,nodev,noexec,noatime"
        # Pi kernels can default VFAT to ASCII. Without this, non-ASCII long
        # names appear as '?' before scanning, so content hashes alone cannot
        # detect the loss of the original filenames.
        if fs == "vfat":
            options += ",utf8=1"
        if source:
            # Block-layer protection also prevents filesystem journal writes.
            self.run("blockdev", "--setro", disk["path"])
            self.run("blockdev", "--setro", selected["path"])
            if self.run("blockdev", "--getro", selected["path"]).stdout.strip() != "1":
                raise BackupError("원본 읽기 전용 보호에 실패했습니다.")
            if fs == "ext4":
                options += ",noload"
        self.run("mount", "-t", "ntfs3" if fs == "ntfs" else fs,
                 "-o", options, "--", selected["path"], str(mountpoint))
        self.mounted.append(mountpoint)
        if (disk_identity(disk) != disk["token"] or os.stat(mountpoint).st_dev != node.st_rdev
                or bool(os.statvfs(mountpoint).f_flag & os.ST_RDONLY) != source):
            raise BackupError("마운트된 장치 또는 읽기 전용 상태가 일치하지 않습니다.")
        return mountpoint

    def close(self):
        errors = []
        for mountpoint in reversed(self.mounted[:]):
            try:
                # Normal unmount flushes the FS. Never lazy/force-unmount.
                self.run("umount", "--", str(mountpoint))
                if os.path.ismount(mountpoint):
                    raise BackupError("마운트 해제가 완료되지 않았습니다.")
                self.mounted.remove(mountpoint)
            except (OSError, BackupError, subprocess.SubprocessError) as exc:
                errors.append(str(exc))
        if errors:
            raise BackupError("안전 분리 실패: " + "; ".join(errors))


def sync_filesystem(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.syncfs(fd) != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))
    finally:
        os.close(fd)


def run_job(source, target, emit, stopped, mounts=None, current=inventory, sync=sync_filesystem):
    mounts = mounts or Mounts()
    state = dict(state="MOUNTING", source_connected=True, target_connected=True,
                 safe_to_remove=False, copied_bytes=0, total_bytes=0, verified_files=0)
    expected = {source["token"], target["token"]}
    last_check = -1.0

    def cancelled(force=False):
        nonlocal last_check
        if stopped():
            return True
        now = time.monotonic()
        if force or now - last_check >= .25:
            if {d["token"] for d in current()} != expected:
                raise BackupError("저장장치 연결이 변경되었습니다. 백업을 중단합니다.")
            last_check = now
        return False

    def event(e):
        phase = e["state"]
        if phase == "VERIFIED":
            state["state"] = "FINAL_CHECK"
        elif phase not in ("SCANNED", "FILE_VERIFIED"):
            state["state"] = phase
        for key in ("total_bytes", "total_files", "verified_files"):
            if key in e:
                state[key] = e[key]
        state["copied_bytes"] = e.get("bytes", state["copied_bytes"])
        state["current_file"] = e.get("path", state.get("current_file", ""))
        emit(dict(state))

    success = False
    try:
        emit(dict(state))
        if cancelled(True):
            raise Cancelled("백업 시작 전에 중단했습니다.")
        # Validate BOTH volumes before making the destination writable.
        src_volume, dst_volume = volume(source), volume(target, destination=True)
        src = mounts.mount(source, src_volume, "source")
        if cancelled(True):
            raise Cancelled("마운트 중 중단했습니다.")
        dst = mounts.mount(target, dst_volume, "target")
        if cancelled(True):
            raise Cancelled("마운트 중 중단했습니다.")
        job = backup(src, dst, event, cancelled)
        result = verify(job, cancel=cancelled)
        sync(dst)
        if cancelled(True):
            raise Cancelled("최종 확인 중 중단했습니다.")
        state.update(verified_files=len(result["files"]), copied_bytes=result["bytes"],
                     total_bytes=result["bytes"], current_file="", job=str(job), state="UNMOUNTING")
        emit(dict(state))
        success = True
    except (BackupError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        state.update(state="CANCELLED" if isinstance(exc, Cancelled) else "ERROR", error=str(exc))
    finally:
        try:
            mounts.close()
        except (BackupError, OSError, subprocess.SubprocessError) as exc:
            success = False
            state.update(state="ERROR", error=str(exc))
        if success:
            state.update(state="SAFE_TO_REMOVE", safe_to_remove=True)
        emit(dict(state))
    return state


def display_paths(preferred):
    if preferred != "auto":
        return [preferred]
    found = []
    for entry in Path("/sys/class/graphics").glob("fb[0-9]*"):
        try:
            name = (entry / "name").read_text().strip().lower()
        except OSError:
            name = ""
        found.append((0 if "drmfb" in name or "vc4" in name else 1,
                      str(Path("/dev") / entry.name)))
    return [path for _, path in sorted(found)] or ["/dev/fb0"]


def run(stopped, framebuffer="auto"):
    if os.geteuid() != 0 or not Path("/etc/mebs/appliance").is_file():
        raise BackupError("전용 MEBS 이미지에서만 자동 마운트 모드를 실행할 수 있습니다.")
    from .display import render
    from .framebuffer import Framebuffer
    Path("/run/mebs").mkdir(mode=0o700, exist_ok=True)
    with open("/run/mebs/appliance.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        screen = None
        # Driver probe or HDMI hotplug may finish after init. No copying without a display.
        while screen is None and not stopped():
            for path in display_paths(framebuffer):
                try:
                    screen = Framebuffer(path)
                    print(json.dumps({"display": path}), flush=True)
                    break
                except (OSError, ValueError):
                    pass
            if screen:
                break
            time.sleep(.25)
        if screen is None:
            return
        with screen:
            last = [None, 0.0]

            def emit(state):
                now = time.monotonic()
                changed = state["state"] != last[0]
                if changed or now - last[1] >= .25:
                    screen.show(render(state))
                    last[:] = [state["state"], now]
                if changed:
                    print(json.dumps(state, ensure_ascii=True), flush=True)
                    Path("/run/mebs/status.json").write_text(json.dumps(state, ensure_ascii=True))

            roles = Roles()
            latched = False
            mounts = Mounts()
            emit({"state": "READY"})
            try:
                while not stopped():
                    try:
                        disks = inventory()
                        ids = [d["token"] for d in disks]
                        if not ids and not mounts.mounted:
                            latched = False
                        assigned = roles.observe(ids)
                        if not latched:
                            phase = assigned["state"]
                            if phase == "ROLES_ASSIGNED":
                                latched = True
                                time.sleep(1)  # Allow partition discovery, then revalidate identity.
                                fresh = inventory()
                                if {d["token"] for d in fresh} != set(ids):
                                    raise BackupError("장치 연결이 변경되었습니다. 두 장치를 다시 연결하세요.")
                                lookup = {d["token"]: d for d in fresh}
                                run_job(lookup[assigned["source"]], lookup[assigned["target"]],
                                        emit, stopped, mounts)
                            else:
                                emit({"state": {"WAITING_FOR_TARGET": "READY",
                                                "WAITING_FOR_SOURCE": "WAITING_SOURCE"}.get(phase, phase),
                                      "target_connected": assigned["target"] is not None,
                                      "source_connected": assigned["source"] is not None})
                    except (OSError, BackupError, ValueError, KeyError, subprocess.SubprocessError) as exc:
                        latched = True
                        emit({"state": "ERROR", "error": str(exc), "safe_to_remove": False})
                    time.sleep(.25)
            finally:
                mounts.close()
