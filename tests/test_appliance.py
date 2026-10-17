"""Real engine + fake mount boundaries; never mount host/user media."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from mebs.appliance import Mounts, run_job, volume
from mebs.backup import BackupError, verify


def disk(name, fs="ext4", children=None):
    return dict(path="/dev/" + name, id=name, token=name + ":123", fstype=fs,
                readonly=False, mountpoints=[], partitions=children or [])


class VolumeTests(unittest.TestCase):
    def test_destination_first_policy_requires_writable_ext4(self):
        self.assertEqual(volume(disk("sda"), True)["fstype"], "ext4")
        for fs in ("vfat", "exfat", "ntfs", None):
            with self.subTest(fs=fs), self.assertRaises(BackupError):
                volume(disk("sda", fs), True)
        d = disk("sda")
        d["readonly"] = True
        with self.assertRaises(BackupError):
            volume(d, True)

    def test_source_card_filesystems(self):
        for fs in ("vfat", "exfat", "ntfs", "ext4"):
            self.assertEqual(volume(disk("sdb", fs))["fstype"], fs)

    def test_mounted_boot_disk_and_multipartition_rejected(self):
        d = disk("sda")
        d["mountpoints"] = ["/"]
        with self.assertRaises(BackupError):
            volume(d, True)
        part = dict(name="/dev/sda1", type="part", fstype="ext4", **{"maj:min": "8:1"})
        d = disk("sda", children=[part, dict(part)])
        with self.assertRaises(BackupError):
            volume(d, True)
        part["mountpoints"] = ["/media/important"]
        with self.assertRaises(BackupError):
            volume(disk("sda", children=[part]), True)

    def test_one_partition_resolves_correct_node(self):
        part = dict(name="/dev/sdb1", type="part", fstype="exfat", **{"maj:min": "8:17"})
        self.assertEqual(volume(disk("sdb", children=[part])),
                         dict(path="/dev/sdb1", fstype="exfat", id="8:17"))


class FakeMounts:
    def __init__(self, source, target, fail_close=False):
        self.paths = {"source": source, "target": target}
        self.calls = []
        self.fail_close = fail_close

    def mount(self, disk, selected, role):
        self.calls.append(role)
        return self.paths[role]

    def close(self):
        self.calls.append("close")
        if self.fail_close:
            raise BackupError("Unmount failed")


class JobTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mebs-appliance-test-")
        self.addCleanup(temp.cleanup)
        self.source, self.target = Path(temp.name) / "source", Path(temp.name) / "target"
        self.source.mkdir()
        self.target.mkdir()
        (self.source / "camera.xml").write_bytes(b"<metadata>original</metadata>")
        self.sd, self.hdd = disk("sdb", "exfat"), disk("sda")
        self.events = []
        self.mounts = FakeMounts(self.source, self.target)

    def run_job(self, **kwargs):
        return run_job(self.sd, self.hdd, kwargs.pop("emit", self.events.append),
                       kwargs.pop("stopped", lambda: False), self.mounts,
                       kwargs.pop("current", lambda: [self.sd, self.hdd]),
                       kwargs.pop("sync", lambda path: None), **kwargs)

    def test_copy_verify_flush_unmount_then_safe(self):
        result = self.run_job()
        self.assertEqual(result["state"], "SAFE_TO_REMOVE")
        self.assertTrue(result["safe_to_remove"])
        self.assertEqual(self.mounts.calls, ["source", "target", "close"])
        phases = [e["state"] for e in self.events]
        self.assertLess(phases.index("FINAL_CHECK"), phases.index("UNMOUNTING"))
        self.assertLess(phases.index("UNMOUNTING"), phases.index("SAFE_TO_REMOVE"))
        self.assertEqual(verify(result["job"])["files"][0]["path"], "camera.xml")
        self.assertEqual((self.source / "camera.xml").read_bytes(), b"<metadata>original</metadata>")

    def test_unsupported_destination_never_mounted(self):
        self.hdd["fstype"] = "ntfs"
        self.assertEqual(self.run_job()["state"], "ERROR")
        self.assertEqual(self.mounts.calls, ["close"])

    def test_removed_or_replaced_disk_prevents_copy(self):
        replaced = dict(self.sd, token="sdb:999")
        result = self.run_job(current=lambda: [replaced, self.hdd])
        self.assertEqual(result["state"], "ERROR")
        self.assertFalse(result["safe_to_remove"])
        self.assertEqual(self.mounts.calls, ["close"])

    def test_unmount_error_never_safe(self):
        self.mounts.fail_close = True
        result = self.run_job()
        self.assertEqual(result["state"], "ERROR")
        self.assertFalse(result["safe_to_remove"])

    def test_flush_error_never_safe(self):
        def failure(path):
            raise OSError("syncfs failed")
        result = self.run_job(sync=failure)
        self.assertEqual(result["state"], "ERROR")
        self.assertFalse(result["safe_to_remove"])

    def test_cancel_before_mount(self):
        result = self.run_job(stopped=lambda: True)
        self.assertEqual(result["state"], "CANCELLED")
        self.assertEqual(self.mounts.calls, ["close"])

    def test_verification_error_is_not_safe(self):
        def emit(e):
            self.events.append(e)
            if e["state"] == "FINAL_CHECK":
                job, = self.target.glob("mebs-backup-*")
                (job / "data/camera.xml").write_bytes(b"tampered")
        result = self.run_job(emit=emit)
        self.assertEqual(result["state"], "ERROR")
        self.assertFalse(result["safe_to_remove"])


class UnmountTests(unittest.TestCase):
    def test_failed_unmount_stays_tracked_without_force(self):
        with tempfile.TemporaryDirectory() as temp:
            run = mock.Mock(side_effect=subprocess.CalledProcessError(1, "umount"))
            mounts = Mounts(temp, run)
            point = Path(temp) / "target"
            mounts.mounted.append(point)
            with self.assertRaises(BackupError):
                mounts.close()
            self.assertEqual(mounts.mounted, [point])
            run.assert_called_once_with("umount", "--", str(point))
