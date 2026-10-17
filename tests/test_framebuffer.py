import tempfile
import unittest

from mebs.framebuffer import BitField, FixedInfo, Framebuffer, VariableInfo, blit, geometry, pixel_mode


class FramebufferTests(unittest.TestCase):
    def setUp(self):
        self.fixed = FixedInfo(type=0, visual=2, line_length=16, smem_len=64)
        self.var = VariableInfo(xres=2, yres=2, xres_virtual=4, yres_virtual=4,
                                xoffset=1, yoffset=1, bits_per_pixel=32,
                                red=BitField(16, 8, 0), green=BitField(8, 8, 0), blue=BitField(0, 8, 0))

    def test_bgra_layout(self):
        self.assertEqual(pixel_mode(self.fixed, self.var), "BGRA")

    def test_rgba_layout(self):
        self.var.red.offset, self.var.blue.offset = 0, 16
        self.assertEqual(pixel_mode(self.fixed, self.var), "RGBA")

    def test_unsupported_pixel_layout_rejected(self):
        self.var.bits_per_pixel = 16
        with self.assertRaises(ValueError):
            pixel_mode(self.fixed, self.var)

    def test_memory_bounds_checked(self):
        self.fixed.smem_len = 16
        with self.assertRaises(ValueError):
            geometry(self.fixed, self.var)

    def test_stride_checked(self):
        self.fixed.line_length = 8
        with self.assertRaises(ValueError):
            geometry(self.fixed, self.var)

    def test_padding_and_offsets_are_preserved(self):
        buffer = bytearray([255] * 64)
        raw = bytes(range(16))
        self.assertEqual(geometry(self.fixed, self.var), 48)
        blit(buffer, raw, self.fixed, self.var)
        self.assertEqual(buffer[20:28], raw[:8])
        self.assertEqual(buffer[36:44], raw[8:])
        self.assertEqual(buffer[28:36], bytes([255] * 8))
        self.assertEqual(buffer[:20], bytes([255] * 20))

    def test_regular_files_are_not_framebuffer_devices(self):
        with tempfile.NamedTemporaryFile() as temp:
            with self.assertRaises(ValueError):
                Framebuffer(temp.name)


if __name__ == "__main__":
    unittest.main()
