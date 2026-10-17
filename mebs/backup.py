"""Linux directory backup with anchored descriptors and a durable commit boundary.

No mounting, formatting, source deletion, overwrite, or shutdown commands live here.
"""

import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from contextlib import contextmanager
from datetime import datetime, timezone
import uuid


class BackupError(Exception):
    pass


class Cancelled(BackupError):
    pass


DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
CHUNK = 1024 * 1024


def signature(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


@contextmanager
def directory(root, parts=()):
    fd = os.dup(root)
    try:
        for part in parts:
            new = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = new
        yield fd
    finally:
        os.close(fd)


def inventory(root):
    """Reject links, special files, and nested filesystems instead of omitting data."""
    entries = {}
    device = os.fstat(root).st_dev

    def walk(fd, parts):
        entries[parts] = os.fstat(fd)
        with os.scandir(fd) as scan:
            names = sorted(e.name for e in scan)
        for name in names:
            path = parts + (name,)
            s = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if s.st_dev != device:
                raise BackupError(f"Nested filesystem: {'/'.join(path)}")
            if stat.S_ISDIR(s.st_mode):
                with directory(fd, (name,)) as child:
                    if signature(os.fstat(child)) != signature(s):
                        raise BackupError("Source directory changed during scan")
                    walk(child, path)
            elif stat.S_ISREG(s.st_mode):
                entries[path] = s
            else:
                raise BackupError(f"Unsupported link or special file: {'/'.join(path)}")

    walk(root, ())
    return entries


def check_cancel(cancel):
    if cancel():
        raise Cancelled("Backup cancelled; partial job retained, never reported as success")


def digest(fd, cancel=lambda: False):
    os.lseek(fd, 0, os.SEEK_SET)
    h = hashlib.sha256()
    while True:
        check_cancel(cancel)
        chunk = os.read(fd, CHUNK)
        if not chunk:
            return h.hexdigest()
        h.update(chunk)


def metadata(source, target, snapshot):
    # Strict preservation: unsupported attributes fail the job rather than vanish.
    attributes = {}
    for name in os.listxattr(source):
        value = os.getxattr(source, name)
        attributes[name] = value
        os.setxattr(target, name, value)
    os.fchmod(target, stat.S_IMODE(snapshot.st_mode) & 0o777)
    os.utime(target, ns=(snapshot.st_atime_ns, snapshot.st_mtime_ns))
    actual = os.fstat(target)
    if actual.st_mtime_ns != snapshot.st_mtime_ns:
        raise BackupError("Destination cannot preserve nanosecond modification time")
    if stat.S_IMODE(actual.st_mode) != (stat.S_IMODE(snapshot.st_mode) & 0o777):
        raise BackupError("Destination cannot preserve POSIX permission bits")
    for name, value in attributes.items():
        if os.getxattr(target, name) != value:
            raise BackupError(f"Extended attribute mismatch: {name}")
    os.fsync(target)


def write_json(fd, name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode()
    out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                  0o600, dir_fd=fd)
    try:
        with os.fdopen(out, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(out)
    finally:
        os.close(out)
    os.fsync(fd)


def commit(root, pending, final):
    # Linux RENAME_NOREPLACE prevents replacement even if another process races us.
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                       ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(root, os.fsencode(pending), root, os.fsencode(final), 1):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    os.fsync(root)


def backup(source, target, emit=lambda event: None, cancel=lambda: False):
    source = Path(source).resolve(strict=True)
    target = Path(target).resolve(strict=True)
    if source == target or source in target.parents or target in source.parents:
        raise BackupError("Source and target must be distinct, non-nested directories")
    source_fd = os.open(source, DIR_FLAGS)
    try:
        target_fd = os.open(target, DIR_FLAGS)
        try:
            return _backup(source_fd, target_fd, target, emit, cancel)
        finally:
            os.close(target_fd)
    finally:
        os.close(source_fd)


def _backup(source, target, target_path, emit, cancel):
    lock = os.open(".mebs.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                   0o600, dir_fd=target)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode) or os.fstat(lock).st_nlink != 1:
            raise BackupError("Unsafe destination lock file")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BackupError("Destination is busy with another backup") from exc
        check_cancel(cancel)
        emit({"state": "SCANNING"})
        entries = inventory(source)
        target_stat = os.fstat(target)
        if any((s.st_dev, s.st_ino) == (target_stat.st_dev, target_stat.st_ino)
               for s in entries.values()):
            raise BackupError("Destination aliases a directory in the source tree")
        files = [(p, s) for p, s in entries.items() if stat.S_ISREG(s.st_mode)]
        total = sum(s.st_size for _, s in files)
        emit({"state": "SCANNED", "total_bytes": total, "total_files": len(files)})
        fs = os.fstatvfs(target)
        # Conservative per-file allocation estimate plus room for journal/manifest.
        needed = sum(((s.st_size + fs.f_frsize - 1) // fs.f_frsize) * fs.f_frsize
                     for _, s in files) + len(entries) * fs.f_frsize + CHUNK
        if fs.f_bavail * fs.f_frsize < needed:
            raise BackupError("Insufficient free space on destination")
        identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex
        pending, final = ".mebs-pending-" + identifier, "mebs-backup-" + identifier
        os.mkdir(pending, 0o700, dir_fd=target)
        os.fsync(target)
        with directory(target, (pending,)) as job:
            write_json(job, "job.json", {"version": 1, "state": "IN_PROGRESS"})
            try:
                os.mkdir("data", 0o700, dir_fd=job)
                with directory(job, ("data",)) as data:
                    for parts, s in entries.items():
                        check_cancel(cancel)
                        if parts and stat.S_ISDIR(s.st_mode):
                            with directory(data, parts[:-1]) as parent:
                                os.mkdir(parts[-1], 0o700, dir_fd=parent)
                    records = []
                    copied = 0
                    for parts, snapshot in files:
                        check_cancel(cancel)
                        with directory(source, parts[:-1]) as sp, directory(data, parts[:-1]) as dp:
                            src = os.open(parts[-1], FILE_FLAGS, dir_fd=sp)
                            try:
                                if signature(os.fstat(src)) != signature(snapshot):
                                    raise BackupError("Source file changed before copy")
                                dst = os.open(parts[-1], os.O_RDWR | os.O_CREAT | os.O_EXCL
                                              | os.O_NOFOLLOW, 0o600, dir_fd=dp)
                                try:
                                    expected = hashlib.sha256()
                                    while True:
                                        check_cancel(cancel)
                                        chunk = os.read(src, CHUNK)
                                        if not chunk:
                                            break
                                        expected.update(chunk)
                                        view = memoryview(chunk)
                                        while view:
                                            written = os.write(dst, view)
                                            if written == 0:
                                                raise OSError(errno.EIO, "Zero-length write")
                                            view = view[written:]
                                        copied += len(chunk)
                                        emit({"state": "COPYING", "path": "/".join(parts),
                                              "bytes": copied, "total_bytes": total})
                                    os.fsync(dst)
                                    emit({"state": "VERIFYING", "path": "/".join(parts)})
                                    actual = digest(dst, cancel)
                                    if actual != expected.hexdigest():
                                        raise BackupError(f"SHA-256 mismatch: {'/'.join(parts)}")
                                    if signature(os.fstat(src)) != signature(snapshot):
                                        raise BackupError("Source file changed during copy")
                                    metadata(src, dst, snapshot)
                                    records.append({"path": "/".join(parts), "size": snapshot.st_size,
                                                    "sha256": actual})
                                    emit({"state": "FILE_VERIFIED", "path": "/".join(parts),
                                          "verified_files": len(records), "total_files": len(files)})
                                finally:
                                    os.close(dst)
                            finally:
                                os.close(src)
                    # Apply directory timestamps after all children have been created.
                    for parts, snapshot in reversed(list(entries.items())):
                        if stat.S_ISDIR(snapshot.st_mode):
                            with directory(source, parts) as src, directory(data, parts) as dst:
                                metadata(src, dst, snapshot)
                    again = inventory(source)
                    if {p: signature(s) for p, s in entries.items()} != {p: signature(s) for p, s in again.items()}:
                        raise BackupError("Source tree changed during backup")
                check_cancel(cancel)
                write_json(job, "manifest.json", {"version": 1, "state": "VERIFIED",
                           "algorithm": "sha256", "files": records, "bytes": total,
                           "directories": ["/".join(p) for p, s in entries.items()
                                           if p and stat.S_ISDIR(s.st_mode)]})
                commit(target, pending, final)
            except BaseException as exc:
                try:
                    write_json(job, "failure.json", {"state": "FAILED", "error": str(exc)})
                except OSError:
                    pass  # Device may have disappeared: pending name still signals incompletion.
                raise
        result = target_path / final
        emit({"state": "VERIFIED", "job": str(result), "bytes": total,
              "files": len(files), "message": "Flush complete; unmount still required before unplugging"})
        return result
    finally:
        os.close(lock)


def verify(job_path, cancel=lambda: False):
    check_cancel(cancel)
    job_path = Path(job_path).resolve(strict=True)
    if not job_path.name.startswith("mebs-backup-"):
        raise BackupError("Only committed backup jobs may be verified")
    fd = os.open(job_path, DIR_FLAGS)
    try:
        try:
            os.stat("failure.json", dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise BackupError("Job has a failure marker")
        manifest_fd = os.open("manifest.json", FILE_FLAGS, dir_fd=fd)
        with os.fdopen(manifest_fd) as stream:
            manifest = json.load(stream)
        if (manifest.get("version"), manifest.get("state"), manifest.get("algorithm")) != (1, "VERIFIED", "sha256"):
            raise BackupError("Invalid or incomplete manifest")
        with directory(fd, ("data",)) as data:
            seen = set()
            for item in manifest["files"]:
                check_cancel(cancel)
                parts = tuple(item["path"].split("/"))
                if any(p in ("", ".", "..") for p in parts) or parts in seen:
                    raise BackupError("Unsafe or duplicate manifest path")
                seen.add(parts)
                with directory(data, parts[:-1]) as parent:
                    file = os.open(parts[-1], FILE_FLAGS, dir_fd=parent)
                    try:
                        s = os.fstat(file)
                        if not stat.S_ISREG(s.st_mode) or s.st_size != item["size"] or digest(file, cancel) != item["sha256"]:
                            raise BackupError(f"Verification failed: {item['path']}")
                    finally:
                        os.close(file)
            actual = inventory(data)
            if {p for p, s in actual.items() if stat.S_ISREG(s.st_mode)} != seen:
                raise BackupError("Backup file list does not match manifest")
            if {"/".join(p) for p, s in actual.items() if p and stat.S_ISDIR(s.st_mode)} != set(manifest["directories"]):
                raise BackupError("Backup directory list does not match manifest")
        check_cancel(cancel)
        return manifest
    finally:
        os.close(fd)
