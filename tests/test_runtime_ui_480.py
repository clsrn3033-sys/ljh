import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mebs.runtime_ui_480 import render, _progress, PHASES, WIDTH, HEIGHT

class RuntimeUITest(unittest.TestCase):
    def test_resolution(self): self.assertEqual(render({}).size, (480, 320))
    def test_rgb(self): self.assertEqual(render({}).mode, "RGB")
    def test_every_state(self):
        for state in PHASES:
            with self.subTest(state=state): self.assertEqual(render({"state":state}).size, (480,320))
    def test_unknown_state_fails_closed(self): self.assertEqual(render({"state":"UNTRUSTED"}).size, (480,320))
    def test_copy_percent_clamped(self):
        self.assertEqual(_progress({"total_bytes":100,"copied_bytes":200},"COPYING"),100)
        self.assertEqual(_progress({"total_bytes":100,"copied_bytes":-2},"COPYING"),0)
    def test_verify_distinct_from_copy(self):
        self.assertEqual(_progress({"total_bytes":100,"copied_bytes":100,"verified_bytes":4},"VERIFYING"),4)
    def test_verified_not_safe(self):
        self.assertNotEqual(PHASES["COMPLETE"], PHASES["SAFE_TO_REMOVE"])
        self.assertEqual(PHASES["COMPLETE"][3],"verified")
        self.assertEqual(PHASES["SAFE_TO_REMOVE"][3],"safe")
    def test_missing_telemetry(self): self.assertEqual(render({"state":"READY"}).size,(480,320))
    def test_bad_telemetry(self):
        self.assertEqual(render({"cpu_temp_c":float('nan'),"ram_percent":object(),"uptime_seconds":-12}).size,(480,320))
    def test_no_write_operations(self):
        import inspect, mebs.runtime_ui_480 as m
        source=inspect.getsource(m)
        for token in ("os.system(","subprocess.","os.remove(","shutil.rmtree(","mkfs", "format_device"):
            self.assertNotIn(token,source)
    def test_stage_count(self): self.assertEqual(len(PHASES["READY"]),4)
    def test_unsupported_input(self):
        with self.assertRaises(TypeError): render(None)

if __name__ == '__main__': unittest.main()