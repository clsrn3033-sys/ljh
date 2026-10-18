"""Explicit evdev touchscreen, one contact at a time; no mouse/keyboard grabbing."""
import fcntl
import os
import select
import struct
import time

EVENT = struct.Struct('@llHHi')
ABS_X, ABS_Y, ABS_MT_POSITION_X, ABS_MT_POSITION_Y = 0, 1, 53, 54


def scale(value, low, high, pixels):
    if high <= low:
        raise ValueError('invalid touch axis range')
    return max(0, min(pixels-1, round((value-low)*(pixels-1)/(high-low))))


class Touch:
    def __init__(self, path, callback, rotation=0):
        if rotation not in (0, 180):
            raise ValueError('only landscape rotations 0/180 supported')
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        self.callback, self.rotation = callback, rotation
        self.buffer = b''
        self.x = self.y = None
        self.down = False
        self.start = None
        self.dropped = False
        try:
            self.ranges = {}
            for axis in (ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_X, ABS_Y):
                buf = bytearray(24)
                try:
                    fcntl.ioctl(self.fd, 0x80184540 + axis, buf)
                    info = struct.unpack('6i', buf)
                    if info[2] > info[1]:
                        self.ranges[axis] = (info[1], info[2])
                except OSError:
                    pass
            if not ((53 in self.ranges and 54 in self.ranges) or (0 in self.ranges and 1 in self.ranges)):
                raise ValueError('not an absolute touchscreen')
            self.axes = (53, 54) if 53 in self.ranges and 54 in self.ranges else (0, 1)
            self.slot = 0
        except BaseException:
            self.close()
            raise

    def event(self, typ, code, value):
        if typ == 0 and code == 3:  # SYN_DROPPED: discard gesture until release
            self.dropped = True
            self.start = None
        if typ == 3 and code == 47:
            self.slot = value
        if typ == 3 and code == 57 and self.slot > 0 and value >= 0:
            self.dropped = True
            self.start = None
        if typ == 3 and code == 57 and self.slot == 0:
            self.down = value >= 0
        if typ == 1 and code == 330:
            self.down = value != 0
        if typ == 3 and self.slot == 0 and code in self.axes:
            i = self.axes.index(code)
            value = scale(value, *self.ranges[code], (800, 480)[i])
            if self.rotation == 180:
                value = (799, 479)[i] - value
            if i == 0:
                self.x = value
            else:
                self.y = value
        if typ == 0 and code == 0:
            if self.dropped:
                if not self.down:
                    self.dropped = False
                return
            if self.down and self.start is None and self.x is not None and self.y is not None:
                self.start = ((self.x, self.y), time.monotonic())
            elif not self.down and self.start is not None:
                start, when = self.start
                self.start = None
                self.callback(start, (self.x, self.y), time.monotonic()-when)

    def poll(self):
        if not select.select([self.fd], [], [], 0)[0]:
            return
        chunk = os.read(self.fd, EVENT.size * 32)
        if not chunk:
            raise OSError('touchscreen disconnected')
        self.buffer += chunk
        while len(self.buffer) >= EVENT.size:
            _, _, typ, code, value = EVENT.unpack(self.buffer[:EVENT.size])
            self.buffer = self.buffer[EVENT.size:]
            self.event(typ, code, value)

    def close(self):
        os.close(self.fd)
