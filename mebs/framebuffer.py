"""Optional Linux fbdev output for HDMI tests; never changes display modes.

Reference: https://docs.kernel.org/fb/api.html
Supports packed truecolor 32-bit RGB/BGR only. DRM-only systems need a separate
adapter; unsupported layouts are rejected before mapping or writing memory.
"""
import ctypes as c
import fcntl
import mmap
import os
import stat
import sys


class BitField(c.Structure):
    _fields_ = [(key, c.c_uint32) for key in ("offset", "length", "msb_right")]


class VariableInfo(c.Structure):
    _fields_ = ([(key, c.c_uint32) for key in
                 ("xres", "yres", "xres_virtual", "yres_virtual", "xoffset", "yoffset", "bits_per_pixel", "grayscale")]
                + [(key, BitField) for key in ("red", "green", "blue", "transp")]
                + [(key, c.c_uint32) for key in
                   ("nonstd", "activate", "height", "width", "accel_flags", "pixclock", "left_margin",
                    "right_margin", "upper_margin", "lower_margin", "hsync_len", "vsync_len", "sync",
                    "vmode", "rotate", "colorspace")]
                + [("reserved", c.c_uint32 * 4)])


class FixedInfo(c.Structure):
    _fields_ = [("id", c.c_char * 16), ("smem_start", c.c_ulong), ("smem_len", c.c_uint32),
                ("type", c.c_uint32), ("type_aux", c.c_uint32), ("visual", c.c_uint32),
                ("xpanstep", c.c_uint16), ("ypanstep", c.c_uint16), ("ywrapstep", c.c_uint16),
                ("line_length", c.c_uint32), ("mmio_start", c.c_ulong), ("mmio_len", c.c_uint32),
                ("accel", c.c_uint32), ("capabilities", c.c_uint16), ("reserved", c.c_uint16 * 2)]


def read_info(fd, request, cls):
    data = bytearray(c.sizeof(cls))
    fcntl.ioctl(fd, request, data, True)
    return cls.from_buffer_copy(data)


def pixel_mode(fixed, var):
    if (sys.byteorder != "little" or fixed.type != 0 or fixed.visual != 2
            or var.bits_per_pixel != 32 or var.grayscale or var.nonstd or var.rotate):
        raise ValueError("지원하지 않는 framebuffer 형식입니다. 32-bit truecolor 출력이 필요합니다.")
    channels = (var.red, var.green, var.blue)
    if any(ch.length != 8 or ch.msb_right for ch in channels):
        raise ValueError("지원하지 않는 RGB 비트 배열입니다.")
    if var.transp.length and (var.transp.length != 8 or var.transp.offset != 24 or var.transp.msb_right):
        raise ValueError("지원하지 않는 알파 비트 배열입니다.")
    offsets = tuple(ch.offset for ch in channels)
    if offsets == (16, 8, 0):
        return "BGRA"
    if offsets == (0, 8, 16):
        return "RGBA"
    raise ValueError("지원하지 않는 RGB 순서입니다.")


def geometry(fixed, var):
    if not (0 < var.xres <= 4096 and 0 < var.yres <= 4096):
        raise ValueError("잘못되었거나 너무 큰 화면 크기입니다.")
    if (var.xoffset + var.xres > var.xres_virtual or var.yoffset + var.yres > var.yres_virtual
            or (var.xoffset + var.xres) * 4 > fixed.line_length):
        raise ValueError("framebuffer 화면 범위가 일치하지 않습니다.")
    length = (var.yoffset + var.yres) * fixed.line_length
    if length > fixed.smem_len or length > 256 * 1024 * 1024:
        raise ValueError("framebuffer 메모리 범위를 초과합니다.")
    return length


def blit(buffer, raw, fixed, var):
    row = var.xres * 4
    if len(raw) != row * var.yres:
        raise ValueError("렌더링 크기가 화면과 다릅니다.")
    for y in range(var.yres):
        start = (var.yoffset + y) * fixed.line_length + var.xoffset * 4
        buffer[start:start + row] = raw[y * row:(y + 1) * row]


class Framebuffer:
    def __init__(self, path="/dev/fb0"):
        before = os.stat(path, follow_symlinks=False)
        if not stat.S_ISCHR(before.st_mode) or os.major(before.st_rdev) != 29:
            raise ValueError("Linux framebuffer 문자 장치만 열 수 있습니다.")
        self.fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(self.fd)
            if not stat.S_ISCHR(info.st_mode) or os.major(info.st_rdev) != 29:
                raise ValueError("Linux framebuffer 문자 장치만 열 수 있습니다.")
            self.fixed = read_info(self.fd, 0x4602, FixedInfo)
            self.var = read_info(self.fd, 0x4600, VariableInfo)
            self.mode = pixel_mode(self.fixed, self.var)
            length = geometry(self.fixed, self.var)
            self.memory = mmap.mmap(self.fd, length, flags=mmap.MAP_SHARED,
                                    prot=mmap.PROT_READ | mmap.PROT_WRITE)
        except BaseException:
            os.close(self.fd)
            raise

    def show(self, image):
        from PIL import Image, ImageOps
        size = (self.var.xres, self.var.yres)
        canvas = Image.new("RGBA", size, (0, 0, 0, 255))
        content = ImageOps.contain(image, size)
        canvas.paste(content, ((size[0] - content.width) // 2, (size[1] - content.height) // 2))
        blit(self.memory, canvas.tobytes("raw", self.mode), self.fixed, self.var)

    def close(self):
        self.memory.close()
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
