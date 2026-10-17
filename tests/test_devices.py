import unittest
from unittest import mock

from mebs.backup import BackupError
from mebs.devices import Roles, usb_disks


class RoleTests(unittest.TestCase):
    def test_distinct_insertion_order(self):
        roles = Roles()
        self.assertEqual(roles.observe([])["state"], "WAITING_FOR_TARGET")
        self.assertEqual(roles.observe(["8:0"])["target"], "8:0")
        result = roles.observe(["8:16", "8:0"])
        self.assertEqual(result["target"], "8:0")
        self.assertEqual(result["source"], "8:16")
        self.assertFalse(result["automatic_backup_enabled"])

    def test_single_initial_disk_is_the_first_destination(self):
        roles = Roles()
        self.assertEqual(roles.observe(["a"])["target"], "a")
        result = roles.observe(["a", "b"])
        self.assertEqual((result["target"], result["source"]), ("a", "b"))

    def test_two_initial_disks_remain_ambiguous(self):
        roles = Roles()
        self.assertEqual(roles.observe(["a", "b"])["state"], "AMBIGUOUS")

    def test_simultaneous_insertions_ambiguous(self):
        roles = Roles()
        roles.observe([])
        self.assertEqual(roles.observe(["a", "b"])["state"], "AMBIGUOUS")

    def test_removal_clears_roles_until_empty(self):
        roles = Roles()
        for ids in ([], ["a"], ["a", "b"]):
            roles.observe(ids)
        self.assertIsNone(roles.observe(["b"])["source"])
        self.assertEqual(roles.observe(["b", "a"])["state"], "AMBIGUOUS")
        roles.observe([])
        self.assertEqual(roles.observe(["c"])["target"], "c")

    def test_third_device_ambiguous(self):
        roles = Roles()
        for ids in ([], ["a"], ["a", "b"]):
            roles.observe(ids)
        self.assertEqual(roles.observe(["a", "b", "c"])["state"], "AMBIGUOUS")

    def test_duplicate_identity_rejected(self):
        with self.assertRaises(BackupError):
            Roles().observe(["a", "a"])

    def test_inventory_excludes_internal_disks(self):
        output = '{"blockdevices":[{"type":"disk","tran":"sata","name":"/dev/sda"},' \
                 '{"type":"disk","tran":"usb","name":"/dev/sdb","maj:min":"8:16",' \
                 '"ro":false,"children":[]}]}'
        with mock.patch("mebs.devices.subprocess.run", return_value=mock.Mock(stdout=output)):
            devices = usb_disks()
        self.assertEqual([d["path"] for d in devices], ["/dev/sdb"])


if __name__ == "__main__":
    unittest.main()
