"""Read-only sizing telemetry. Engine rechecks allocation under its own lock."""
import os
import stat
from .backup import CHUNK, DIR_FLAGS, BackupError, inventory


def capacity(source, target):
    src = os.open(source, DIR_FLAGS)
    try:
        dst = os.open(target, DIR_FLAGS)
    except BaseException:
        os.close(src)
        raise
    try:
        entries = inventory(src)
        files = [s for s in entries.values() if stat.S_ISREG(s.st_mode)]
        fs = os.fstatvfs(dst)
        needed = sum(((s.st_size + fs.f_frsize-1)//fs.f_frsize)*fs.f_frsize for s in files) + len(entries)*fs.f_frsize + CHUNK
        return dict(total_bytes=sum(s.st_size for s in files), total_files=len(files),
                    needed_bytes=needed, free_bytes=fs.f_bavail*fs.f_frsize)
    finally:
        os.close(src)
        os.close(dst)


def require_space(values):
    if values['needed_bytes'] > values['free_bytes']:
        raise BackupError(f"공간 부족: 필요 {values['needed_bytes']} bytes / 잔여 {values['free_bytes']} bytes. 포맷하지 않습니다.")
