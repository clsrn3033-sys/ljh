from dataclasses import asdict
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mebs.backup import BackupError, Cancelled, verify
from mebs.preview import scenario
from mebs.session import BackupSession


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mebs-session-test-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source, self.target = root / "source", root / "target"
        self.source.mkdir()
        self.target.mkdir()
        (self.source / "clip.xml").write_text('<clip title="원본"/>', encoding="utf-8")

    def session(self, observer=lambda state: None):
        session = BackupSession(observer)
        session.attach_source(self.source)
        session.attach_target(self.target)
        return session

    def test_complete_only_after_final_verification(self):
        events = []
        session = self.session(events.append)
        result = session.run()
        phases = [s["state"] for s in events]
        self.assertLess(phases.index("FINAL_CHECK"), phases.index("COMPLETE"))
        self.assertEqual(result["verified_files"], 1)
        self.assertEqual(result["copied_bytes"], (self.source / "clip.xml").stat().st_size)
        self.assertFalse(result["safe_to_remove"])

    def test_target_without_source_rejected(self):
        with self.assertRaises(BackupError):
            BackupSession().attach_target(self.target)

    def test_run_without_target_rejected(self):
        session = BackupSession()
        session.attach_source(self.source)
        with self.assertRaises(BackupError):
            session.run()

    def test_overlapping_directories_rejected_before_job(self):
        session = BackupSession()
        session.attach_source(self.source)
        with self.assertRaises(BackupError):
            session.attach_target(self.source)
        self.assertEqual(list(self.source.iterdir()), [self.source / "clip.xml"])

    def test_finished_session_cannot_start_second_job(self):
        session = self.session()
        session.run()
        with self.assertRaises(BackupError):
            session.run()

    def test_cancel_before_copy_is_not_complete(self):
        session = self.session()
        session.cancel()
        self.assertEqual(session.run()["state"], "CANCELLED")
        self.assertEqual(list(self.target.glob("mebs-backup-*")), [])

    def test_independent_verification_failure_is_displayed(self):
        def observer(state):
            if state["state"] == "FINAL_CHECK":
                job, = self.target.glob("mebs-backup-*")
                (job / "data" / "clip.xml").write_bytes(b"corruption after commit")
        session = self.session(observer)
        result = session.run()
        self.assertEqual(result["state"], "ERROR")
        self.assertFalse(result["safe_to_remove"])

    def test_verification_can_be_cancelled(self):
        result = self.session().run()
        with self.assertRaises(Cancelled):
            verify(result["job"], cancel=lambda: True)

    def test_all_visual_scenarios_run_real_engine(self):
        expected = {"success": "COMPLETE", "corruption": "ERROR", "cancel": "CANCELLED"}
        for kind, final in expected.items():
            with self.subTest(kind=kind):
                result = scenario(kind)
                self.assertEqual(result["final_state"], final)
                self.assertTrue(result["source_unchanged"])
                self.assertEqual(result["published_jobs"], 1 if kind == "success" else 0)
                self.assertTrue(all(s["demo"] for s in result["states"]))


class BuiltArchiveTests(unittest.TestCase):
    def test_packaged_failure_keeps_nonzero_exit_status(self):
        root = Path(__file__).resolve().parents[1]
        subprocess.run([sys.executable, str(root / "scripts/build.py")], check=True, capture_output=True)
        with tempfile.TemporaryDirectory(prefix="mebs-package-test-") as temp:
            result = subprocess.run([sys.executable, str(root / "dist/mebs.pyz"), "backup",
                                     "--source", temp, "--target", temp], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('"state": "FAILED"', result.stdout)


if __name__ == "__main__":
    unittest.main()
