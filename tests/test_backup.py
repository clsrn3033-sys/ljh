import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from mebs.backup import BackupError, Cancelled, backup, verify


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mebs-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.src, self.dst = self.base / "source", self.base / "target"
        self.src.mkdir()
        self.dst.mkdir()
        (self.src / "clip.bin").write_bytes(bytes(range(256)) * 8192)

    def completed(self):
        return list(self.dst.glob("mebs-backup-*"))

    def test_copy_preserves_tree_xml_empty_files_and_metadata(self):
        folder = self.src / "카메라"
        folder.mkdir()
        (folder / "empty-dir").mkdir()
        xml = folder / "clip.xml"
        xml.write_text('<clip name="테스트" />', encoding="utf-8")
        xml.chmod(0o640)
        os.utime(xml, ns=(1700000000123456789, 1700000000123456789))
        (folder / "empty").touch()
        os.setxattr(xml, "user.mebs-test", b"xml metadata")
        before = {p.relative_to(self.src): p.read_bytes() for p in self.src.rglob("*") if p.is_file()}
        events = []
        job = backup(self.src, self.dst, events.append)
        manifest = verify(job)
        self.assertEqual(len(manifest["files"]), 3)
        for rel, raw in before.items():
            self.assertEqual((self.src / rel).read_bytes(), raw)
            self.assertEqual((job / "data" / rel).read_bytes(), raw)
        copied = job / "data" / "카메라" / "clip.xml"
        self.assertEqual(copied.stat().st_mtime_ns, xml.stat().st_mtime_ns)
        self.assertEqual(copied.stat().st_mode & 0o777, 0o640)
        self.assertEqual(os.getxattr(copied, "user.mebs-test"), b"xml metadata")
        self.assertTrue((job / "data" / "카메라" / "empty-dir").is_dir())
        self.assertEqual(events[-1]["state"], "VERIFIED")

    def test_existing_target_files_and_earlier_jobs_not_overwritten(self):
        (self.dst / "clip.bin").write_bytes(b"original target")
        first = backup(self.src, self.dst)
        second = backup(self.src, self.dst)
        self.assertNotEqual(first, second)
        self.assertEqual((self.dst / "clip.bin").read_bytes(), b"original target")
        verify(first)
        verify(second)

    def test_empty_source(self):
        (self.src / "clip.bin").unlink()
        self.assertEqual(verify(backup(self.src, self.dst))["files"], [])

    def test_same_directory(self):
        with self.assertRaises(BackupError):
            backup(self.src, self.src)

    def test_nested_target(self):
        target = self.src / "target"
        target.mkdir()
        with self.assertRaises(BackupError):
            backup(self.src, target)

    def test_nested_source(self):
        source = self.dst / "source"
        source.mkdir()
        with self.assertRaises(BackupError):
            backup(source, self.dst)

    def test_symlink_root_alias_overlap(self):
        alias = self.base / "alias"
        alias.symlink_to(self.src)
        with self.assertRaises(BackupError):
            backup(alias, self.src)

    def test_symlink_source_rejected(self):
        (self.src / "outside").symlink_to("/etc/passwd")
        with self.assertRaises(BackupError):
            backup(self.src, self.dst)
        self.assertEqual(self.completed(), [])

    def test_fifo_rejected_without_hanging(self):
        os.mkfifo(self.src / "pipe")
        with self.assertRaises(BackupError):
            backup(self.src, self.dst)

    def test_busy_destination_rejected(self):
        with (self.dst / ".mebs.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(BackupError, "busy"):
                backup(self.src, self.dst)

    def test_destination_lock_symlink_rejected(self):
        victim = self.base / "victim"
        victim.write_bytes(b"untouched")
        (self.dst / ".mebs.lock").symlink_to(victim)
        with self.assertRaises(OSError):
            backup(self.src, self.dst)
        self.assertEqual(victim.read_bytes(), b"untouched")

    def test_space_check(self):
        space = mock.Mock(f_frsize=4096, f_bavail=0)
        with mock.patch("mebs.backup.os.fstatvfs", return_value=space):
            with self.assertRaisesRegex(BackupError, "free space"):
                backup(self.src, self.dst)
        self.assertEqual(self.completed(), [])

    def test_copy_enospc_does_not_commit(self):
        # JSON uses buffered file IO; os.write here is the data-copy boundary.
        with mock.patch("mebs.backup.os.write", side_effect=OSError(errno.ENOSPC, "full")):
            with self.assertRaises(OSError):
                backup(self.src, self.dst)
        self.assertEqual(self.completed(), [])
        pending, = self.dst.glob(".mebs-pending-*")
        self.assertTrue((pending / "failure.json").is_file())

    def test_partial_writes_handled(self):
        original = os.write
        with mock.patch("mebs.backup.os.write", side_effect=lambda fd, data: original(fd, data[:65536])):
            job = backup(self.src, self.dst)
        verify(job)

    def test_hash_mismatch_does_not_commit(self):
        with mock.patch("mebs.backup.digest", return_value="0" * 64):
            with self.assertRaisesRegex(BackupError, "SHA-256 mismatch"):
                backup(self.src, self.dst)
        self.assertEqual(self.completed(), [])

    def test_cancellation_leaves_partial_job_and_source(self):
        stop = False

        def emit(event):
            nonlocal stop
            if event["state"] == "COPYING":
                stop = True

        before = (self.src / "clip.bin").read_bytes()
        with self.assertRaises(Cancelled):
            backup(self.src, self.dst, emit, lambda: stop)
        self.assertEqual(self.completed(), [])
        self.assertEqual((self.src / "clip.bin").read_bytes(), before)
        pending, = self.dst.glob(".mebs-pending-*")
        with self.assertRaises(BackupError):
            verify(pending)

    def test_source_change_during_copy_fails(self):
        def emit(event):
            if event["state"] == "VERIFYING":
                (self.src / "clip.bin").write_bytes(b"changed")

        with self.assertRaisesRegex(BackupError, "changed"):
            backup(self.src, self.dst, emit)
        self.assertEqual(self.completed(), [])

    def test_source_file_added_during_backup_fails(self):
        def emit(event):
            if event["state"] == "VERIFYING":
                (self.src / "new-file").touch()

        with self.assertRaisesRegex(BackupError, "tree changed"):
            backup(self.src, self.dst, emit)

    def test_corrupt_copied_data_is_detected_before_commit(self):
        def emit(event):
            if event["state"] == "VERIFYING":
                pending, = self.dst.glob(".mebs-pending-*")
                (pending / "data" / "clip.bin").write_bytes(b"corrupt")

        with self.assertRaisesRegex(BackupError, "SHA-256 mismatch"):
            backup(self.src, self.dst, emit)
        self.assertEqual(self.completed(), [])

    def test_later_corruption_detected_by_verify(self):
        job = backup(self.src, self.dst)
        (job / "data" / "clip.bin").write_bytes(b"bad")
        with self.assertRaises(BackupError):
            verify(job)

    def test_extra_file_detected_by_verify(self):
        job = backup(self.src, self.dst)
        (job / "data" / "unexpected").touch()
        with self.assertRaisesRegex(BackupError, "file list"):
            verify(job)

    def test_manifest_traversal_rejected(self):
        job = backup(self.src, self.dst)
        path = job / "manifest.json"
        data = json.loads(path.read_text())
        data["files"][0]["path"] = "../outside"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(BackupError, "Unsafe"):
            verify(job)

    def test_destination_data_symlink_rejected_by_verify(self):
        job = backup(self.src, self.dst)
        path = job / "data" / "clip.bin"
        path.unlink()
        path.symlink_to(self.src / "clip.bin")
        with self.assertRaises(OSError):
            verify(job)

    def test_cli_failure_has_nonzero_exit_and_failed_event(self):
        result = subprocess.run([sys.executable, "-m", "mebs", "backup", "--source", str(self.src),
                                 "--target", str(self.src)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["state"], "FAILED")


if __name__ == "__main__":
    unittest.main()
