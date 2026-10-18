"""Explicit KMS card, fallback DRM fbdev. Panel/backlight are never inferred."""
from pathlib import Path
import os
import select
import time
import subprocess


class DRM:
    def __init__(self, card, binary='/usr/bin/mebs-drm'):
        self.process = subprocess.Popen([binary, card], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        ready = select.select([self.process.stdout], [], [], 3)[0]
        if not ready or self.process.stdout.readline() != b'READY 800 480\n':
            self.close()
            raise OSError('DRM 800x480 output unavailable')
        os.set_blocking(self.process.stdin.fileno(), False)

    def show(self, image):
        if image.size != (800, 480):
            raise ValueError('expected 800x480')
        # 24-bit RGB colour in 32-bit XRGB scanout, little endian BGRX.
        raw = memoryview(image.convert('RGB').tobytes('raw', 'BGRX'))
        deadline = time.monotonic() + .5
        while raw:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [self.process.stdin], [], remaining)[1]:
                raise OSError('DRM presenter frame timeout')
            try:
                count = os.write(self.process.stdin.fileno(), raw)
                raw = raw[count:]
            except BlockingIOError:
                continue

    def close(self):
        if self.process.stdin:
            try:
                self.process.stdin.close()
            except BrokenPipeError:
                pass
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()  # display helper only; never a backup process
                self.process.wait()
        self.process.stdout.close()


def open_output(config):
    if config.get('drm_card'):
        return DRM(config['drm_card'])
    if config.get('framebuffer'):
        from .framebuffer import Framebuffer
        return Framebuffer(config['framebuffer'])
    raise OSError('Display controller unconfirmed; headless mode remains active')


def apply_backlight(directory, percent):
    if not directory:
        return False  # black frame only; never claim physical backlight is off
    path = Path(directory)
    if path.parent != Path('/sys/class/backlight'):
        raise ValueError('explicit sysfs backlight directory required')
    maximum = int((path/'max_brightness').read_text())
    (path/'brightness').write_text(str(max(0, min(maximum, round(maximum * percent / 100)))))
    return True
