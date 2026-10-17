"""Read-only runtime UI renderer regression checks. No storage access."""
import unittest
from io import BytesIO
from PIL import Image
from mebs.runtime_ui import render, png, copy_progress


class RuntimeUITests(unittest.TestCase):
    def test_all_operational_phases_render(self):
        phases = ("READY", "WAITING_SOURCE", "CONNECTED", "MOUNTING",
                  "SCANNING", "COPYING", "VERIFYING", "FINAL_CHECK",
                  "UNMOUNTING", "COMPLETE", "SAFE_TO_REMOVE",
                  "ERROR", "CANCELLED", "AMBIGUOUS")
        for phase in phases:
            with self.subTest(phase=phase):
                frame = render({"state": phase, "demo": True}, size=(640, 360))
                self.assertEqual(frame.size, (640, 360))
                self.assertEqual(frame.mode, "RGB")

    def test_png_export(self):
        output = png({"state": "READY"})
        self.assertEqual(Image.open(BytesIO(output)).size, (1280, 720))

    def test_unsafe_complete_does_not_claim_eject(self):
        waiting = render({"state": "COMPLETE", "safe_to_remove": False})
        safe = render({"state": "SAFE_TO_REMOVE", "safe_to_remove": True})
        self.assertNotEqual(waiting.tobytes(), safe.tobytes())

    def test_copy_progress_not_inferred_from_empty_total(self):
        self.assertIsNone(copy_progress({"state": "COPYING", "total_bytes": 0, "copied_bytes": 0}))

    def test_copy_progress_range(self):
        self.assertEqual(copy_progress({"state": "COPYING", "total_bytes": 100, "copied_bytes": 50}), 50)

    def test_does_not_mutate_event(self):
        state = {"state": "COPYING", "source_connected": True, "target_connected": True,
                 "total_bytes": 1000, "copied_bytes": 250}
        before = state.copy()
        render(state, size=(320, 180))
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
