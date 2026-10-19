"""V3 on-demand media browser. It never mounts or formats a device.

The appliance supplies already validated mountpoints. Source media is strictly
read-only; explicit file operations are confined to MEBS_FILES on the target.
"""
import hashlib
import ctypes
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid
from threading import Event, Lock, Thread, current_thread


IMAGE = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.webp'}
RAW = {'.arw', '.srf', '.sr2', '.dng', '.cr2', '.cr3', '.nef', '.raf', '.rw2', '.orf'}
VIDEO = {'.mp4', '.mov', '.m4v'}
WORKSPACE = 'MEBS_FILES'


class ExplorerError(Exception):
    pass


def media_type(path):
    suffix = Path(path).suffix.lower()
    return ('image' if suffix in IMAGE else 'raw' if suffix in RAW else
            'video' if suffix in VIDEO else 'other')


def _parts(relative):
    path = Path(relative)
    if path.is_absolute() or any(p in ('', '.', '..') for p in path.parts):
        raise ExplorerError('Invalid media path')
    return path.parts


class Browser:
    def __init__(self, source=None, target=None, *, idle=lambda: True, simulation=False):
        self.roots = {}
        self.idle = idle
        for role, path in (('source', source), ('target', target)):
            if path is not None:
                if Path(path).is_symlink():
                    raise ExplorerError('Media root cannot be a link')
                root = Path(path).resolve(strict=True)
                if not root.is_dir():
                    raise ExplorerError('Media root is not a directory')
                self.roots[role] = (root, root.stat().st_dev)
        if not simulation and len(self.roots) == 2 and self.roots['source'][1] == self.roots['target'][1]:
            raise ExplorerError('Source and target must be different filesystems')

    def _path(self, role, relative='.', *, directory=False):
        if role not in self.roots:
            raise ExplorerError('미디어 없음')
        root, device = self.roots[role]
        path = root
        parts = _parts(relative)
        for index, part in enumerate(parts):
            path = path / part
            meta = path.lstat()
            if stat.S_ISLNK(meta.st_mode) or meta.st_dev != device:
                raise ExplorerError('Links and nested filesystems are blocked')
            if index < len(parts) - 1 and not stat.S_ISDIR(meta.st_mode):
                raise ExplorerError('Non-directory path component')
        if directory and not path.is_dir():
            raise ExplorerError('Directory required')
        if path.is_symlink():
            raise ExplorerError('Link blocked')
        return path

    def listdir(self, role, relative='.', sort='name'):
        folder = self._path(role, relative, directory=True)
        if sort not in ('name', 'size', 'mtime'):
            raise ExplorerError('Invalid sort order')
        items = []
        for entry in folder.iterdir():
            try:
                meta = entry.lstat()
            except FileNotFoundError:
                continue
            kind = 'directory' if stat.S_ISDIR(meta.st_mode) else media_type(entry) if stat.S_ISREG(meta.st_mode) else 'blocked'
            items.append(dict(name=entry.name, kind=kind, size=meta.st_size if kind != 'directory' else 0,
                              mtime_ns=meta.st_mtime_ns, blocked=kind == 'blocked' or
                              meta.st_dev != self.roots[role][1]))
        key = {'name': lambda x: x['name'].casefold(), 'size': lambda x: x['size'],
               'mtime': lambda x: x['mtime_ns']}[sort]
        return sorted(items, key=lambda x: (x['kind'] != 'directory', key(x), x['name']))

    def info(self, role, relative):
        path = self._path(role, relative)
        meta = path.stat()
        return dict(name=path.name, kind='directory' if path.is_dir() else media_type(path),
                    size=meta.st_size, mtime_ns=meta.st_mtime_ns, mode=stat.S_IMODE(meta.st_mode))

    def capacity(self, role):
        root = self._path(role, '.', directory=True)
        fs = os.statvfs(root)
        return dict(total=fs.f_blocks * fs.f_frsize, free=fs.f_bavail * fs.f_frsize)

    def probe_video(self, role, relative, *, executable='ffprobe', runner=subprocess.run):
        path = self._path(role, relative)
        if media_type(path) != 'video' or not path.is_file():
            raise ExplorerError('Video file required')
        result = runner([executable, '-v', 'error', '-show_entries',
                         'stream=codec_type,codec_name,profile,width,height,pix_fmt,bits_per_raw_sample,avg_frame_rate,bit_rate',
                         '-of', 'json', '--', str(path)], capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise ExplorerError('ffprobe failed: ' + result.stderr[:160])
        try:
            video = next(s for s in json.loads(result.stdout)['streams'] if s.get('codec_type') == 'video')
        except (ValueError, KeyError, StopIteration) as exc:
            raise ExplorerError('No readable video stream') from exc
        codec = video.get('codec_name', 'unknown')
        pixels = video.get('pix_fmt', 'unknown')
        depth = video.get('bits_per_raw_sample')
        if not depth:
            match = re.search(r'(\d+)(?:le|be)$', pixels)
            depth = int(match.group(1)) if match else (8 if pixels != 'unknown' else None)
        else:
            depth = int(depth)
        # Hardware decode support depends on the Pi kernel, codecs and panel.
        # Only a conservative software path is offered until live validation.
        playable = codec == 'h264' and pixels in ('yuv420p', 'nv12') and int(video.get('width') or 0) <= 1920 and int(video.get('height') or 0) <= 1080
        return dict(codec=codec, profile=video.get('profile'), width=video.get('width'),
                    height=video.get('height'), pix_fmt=pixels, bit_depth=depth,
                    frame_rate=video.get('avg_frame_rate'), bit_rate=video.get('bit_rate'), software_preview=playable,
                    hardware_acceleration='NOT TESTED',
                    reason='' if playable else '이 영상은 현재 미리보기/재생 제한: 정보만 표시')

    def thumbnail(self, role, relative, size=(320, 180), *, ffmpeg='ffmpeg', runner=subprocess.run):
        """Decode one frame only on selection; never alter source media."""
        from io import BytesIO
        from PIL import Image, ImageOps
        path = self._path(role, relative)
        kind = media_type(path)
        if not path.is_file():
            raise ExplorerError('File required')
        if kind == 'image':
            with Image.open(path) as src:
                if src.width * src.height > 100_000_000:
                    raise ExplorerError('Image too large for preview')
                src.thumbnail(size)
                return ImageOps.exif_transpose(src).convert('RGB').copy()
        if kind not in ('video', 'raw'):
            raise ExplorerError('No thumbnail available')
        result = runner([ffmpeg, '-nostdin', '-v', 'error', '-i', str(path), '-frames:v', '1',
                         '-vf', f'scale={size[0]}:{size[1]}:force_original_aspect_ratio=decrease',
                         '-f', 'image2pipe', '-vcodec', 'png', '-'], capture_output=True, timeout=12)
        if result.returncode or len(result.stdout) > 8_000_000:
            raise ExplorerError('미리보기 불가 · 파일 정보만 표시')
        try:
            with Image.open(BytesIO(result.stdout)) as src:
                return src.convert('RGB').copy()
        except OSError as exc:
            raise ExplorerError('미리보기 불가 · 파일 정보만 표시') from exc

    def _mutable(self, relative, confirm):
        if not confirm or not self.idle():
            raise ExplorerError('확인 필요 또는 백업 진행 중')
        parts = _parts(relative)
        allowed = (len(parts) == 2 or len(parts) == 3 and parts[1] == 'Archive')
        if not allowed or parts[0] != WORKSPACE or parts[-1].startswith('.mebs'):
            raise ExplorerError('MEBS_FILES 안의 일반 파일만 수정할 수 있습니다')
        return self._path('target', relative)

    def _workspace_fd(self, create=False):
        root = self._path('target', '.', directory=True)
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            if create:
                try:
                    os.mkdir(WORKSPACE, 0o700, dir_fd=root_fd)
                    os.fsync(root_fd)
                except FileExistsError:
                    pass
            folder_fd = os.open(WORKSPACE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=root_fd)
            if os.fstat(folder_fd).st_dev != os.fstat(root_fd).st_dev:
                os.close(folder_fd)
                raise ExplorerError('Workspace is on another filesystem')
            return folder_fd
        finally:
            os.close(root_fd)

    def copy_from_source(self, relative, *, confirm=False):
        """Copy one regular source file to MEBS_FILES without overwrite."""
        if not confirm or not self.idle():
            raise ExplorerError('확인 필요 또는 백업 진행 중')
        src = self._path('source', relative)
        if not src.is_file() or src.is_symlink():
            raise ExplorerError('Regular file required')
        folder_fd = self._workspace_fd(create=True)
        partial = '.mebs-explorer-partial-' + uuid.uuid4().hex
        expected = hashlib.sha256()
        try:
            source_fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            if not stat.S_ISREG(os.fstat(source_fd).st_mode) or os.fstat(source_fd).st_dev != self.roots['source'][1]:
                os.close(source_fd)
                raise ExplorerError('Source changed before copy')
            source_before = os.fstat(source_fd)
            output_fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                0o600, dir_fd=folder_fd)
            with os.fdopen(source_fd, 'rb') as reader, os.fdopen(output_fd, 'wb') as writer:
                while True:
                    if not self.idle():
                        raise ExplorerError('백업 시작으로 복사 중단')
                    chunk = reader.read(1024 * 1024)
                    if not chunk:
                        break
                    writer.write(chunk)
                    expected.update(chunk)
                writer.flush()
                os.fsync(writer.fileno())
                source_after = os.fstat(reader.fileno())
                from .backup import metadata
                metadata(reader.fileno(), writer.fileno(), source_before)
            if (source_before.st_dev, source_before.st_ino, source_before.st_size, source_before.st_mtime_ns) != (
                    source_after.st_dev, source_after.st_ino, source_after.st_size, source_after.st_mtime_ns):
                raise ExplorerError('원본 파일이 복사 중 변경되었습니다')
            verify_fd = os.open(partial, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=folder_fd)
            with os.fdopen(verify_fd, 'rb') as reader:
                actual = hashlib.file_digest(reader, 'sha256').hexdigest()
            if actual != expected.hexdigest():
                raise ExplorerError('SHA-256 mismatch')
            from .backup import commit
            try:
                commit(folder_fd, partial, src.name)
            except FileExistsError as exc:
                raise ExplorerError('기존 파일을 덮어쓰지 않습니다') from exc
            return dict(path=str(self.roots['target'][0] / WORKSPACE / src.name),
                        sha256=actual, bytes=source_before.st_size)
        except BaseException:
            try:
                os.unlink(partial, dir_fd=folder_fd)
            except FileNotFoundError:
                pass
            raise
        finally:
            os.close(folder_fd)

    def move_target(self, relative, *, confirm=False):
        src = self._mutable(relative, confirm)
        if len(_parts(relative)) != 2:
            raise ExplorerError('Archive files cannot be moved again')
        directory = self._workspace_fd()
        try:
            meta = os.stat(src.name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(meta.st_mode):
                raise ExplorerError('Only regular workspace files can be moved')
            try:
                os.mkdir('Archive', 0o700, dir_fd=directory)
                os.fsync(directory)
            except FileExistsError:
                pass
            archive = os.open('Archive', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=directory)
            try:
                if os.fstat(archive).st_dev != os.fstat(directory).st_dev:
                    raise ExplorerError('Archive is on another filesystem')
                libc = ctypes.CDLL(None, use_errno=True)
                operation = libc.renameat2
                operation.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
                operation.restype = ctypes.c_int
                if operation(directory, os.fsencode(src.name), archive, os.fsencode(src.name), 1):
                    code = ctypes.get_errno()
                    if code == 17:
                        raise ExplorerError('기존 파일을 덮어쓰지 않습니다')
                    raise OSError(code, os.strerror(code))
                os.fsync(directory); os.fsync(archive)
            finally:
                os.close(archive)
        finally:
            os.close(directory)
        return str(src.parent/'Archive'/src.name)

    def delete_target(self, relative, *, confirm=False):
        path = self._mutable(relative, confirm)
        directory = self._workspace_fd()
        try:
            if len(_parts(relative)) == 3:
                archive = os.open('Archive', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  dir_fd=directory)
                os.close(directory)
                directory = archive
            meta = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(meta.st_mode):
                raise ExplorerError('Only regular workspace files can be deleted')
            os.unlink(path.name, dir_fd=directory)
            os.fsync(directory)
        finally:
            os.close(directory)


class ApplianceSession:
    """Mount on touch demand only, after USB roles are known and worker is idle.

    The V2 role tracker and validated mount implementation remain authoritative.
    A held explorer lock prevents the worker starting a new automatic job.
    """
    def __init__(self, control, worker, *, mounts_factory=None, current=None):
        from .appliance import Mounts, inventory
        self.control, self.worker = control, worker
        self.mounts_factory = mounts_factory or (lambda: Mounts('/run/mebs/explorer'))
        self.current = current or inventory
        self.mounts = self.browser = None
        self.tokens = None

    def open(self):
        from .appliance import volume
        with self.control.lock:
            if self.control.worker_active or self.control.shutdown_pending or self.control.explorer_active:
                raise ExplorerError('백업 또는 종료 진행 중')
            state = self.control.state.get('state')
            if state not in ('READY', 'AMBIGUOUS', 'SAFE_TO_REMOVE', 'WAITING_SOURCE'):
                raise ExplorerError('백업 완료 또는 저장장치 대기 후 탐색 가능')
            target, source = self.worker.roles.target, self.worker.roles.source
            if state in ('READY', 'AMBIGUOUS') and not target:
                self.control.explorer_active = True
                self.browser = Browser()
                self.tokens = set()
                return self.browser
            if not target or self.worker.roles.ambiguous:
                raise ExplorerError('장치 연결 순서가 불명확합니다')
            self.control.explorer_active = True
        try:
            disks = {disk['token']: disk for disk in self.current()}
            if target not in disks or (source and source not in disks):
                raise ExplorerError('장치 연결이 변경되었습니다')
            self.mounts = self.mounts_factory()
            source_path = None
            if source:
                source_path = self.mounts.mount(disks[source], volume(disks[source]), 'source')
            target_path = self.mounts.mount(disks[target], volume(disks[target], destination=True), 'target')
            self.browser = Browser(source_path, target_path, idle=lambda: not self.control.worker_active)
            self.tokens = {target} | ({source} if source else set())
            return self.browser
        except BaseException:
            self.close()
            raise

    def refresh(self):
        if self.browser is None:
            return False
        if {disk['token'] for disk in self.current()} != self.tokens:
            self.close()
            raise ExplorerError('저장장치 연결이 변경되었습니다')
        return True

    def close(self):
        from .appliance import sync_filesystem
        if self.mounts:
            if self.browser and 'target' in self.browser.roots:
                sync_filesystem(self.browser.roots['target'][0])
            self.mounts.close()  # if unmount fails, keep the worker blocked
        self.mounts = self.browser = None
        self.tokens = None
        with self.control.lock:
            self.control.explorer_active = False


class VideoPreview:
    """Bounded, silent software preview. Hardware decode is never implied."""
    FRAME_SIZE = (320, 180)

    def __init__(self, path, *, executable='ffmpeg', popen=subprocess.Popen):
        self.path = str(path)
        self.executable, self.popen = executable, popen
        self.frame = None
        self.error = ''
        self.stop_event = Event()
        self.lock = Lock()
        self.process = None
        self.thread = None

    def start(self):
        if self.thread is not None:
            raise ExplorerError('Preview already active')
        command = [self.executable, '-nostdin', '-v', 'error', '-threads', '2',
                   '-i', self.path, '-map', '0:v:0', '-an', '-sn', '-dn', '-t', '30',
                   '-vf', 'fps=10,scale=320:180', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-']
        self.process = self.popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.thread = Thread(target=self._run, name='mebs-video-preview', daemon=True)
        self.thread.start()

    def _run(self):
        size = self.FRAME_SIZE[0] * self.FRAME_SIZE[1] * 3
        try:
            while not self.stop_event.is_set():
                chunks, remaining = [], size
                while remaining and not self.stop_event.is_set():
                    chunk = self.process.stdout.read(remaining)
                    if not chunk:
                        return
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if remaining:
                    return
                with self.lock:
                    self.frame = b''.join(chunks)
        except (OSError, ValueError) as exc:
            self.error = str(exc)
        finally:
            self.stop()

    def image(self):
        from PIL import Image
        with self.lock:
            frame = self.frame
        return Image.frombytes('RGB', self.FRAME_SIZE, frame) if frame else None

    def stop(self):
        self.stop_event.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self.thread and self.thread is not current_thread():
            self.thread.join(timeout=2)
        if self.process and self.process.stdout and not self.process.stdout.closed:
            self.process.stdout.close()
