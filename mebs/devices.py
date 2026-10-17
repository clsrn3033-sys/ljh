"""Read-only USB inventory and conservative observation-order role tracking.

Detection does not mount a disk, start a backup, or certify that media is safe.
"""
import json
import subprocess

from .backup import BackupError


def usb_disks():
    result = subprocess.run(
        ["lsblk", "--json", "--paths", "--output", "NAME,TYPE,TRAN,RO,MOUNTPOINTS,FSTYPE,UUID,MAJ:MIN"],
        check=True, capture_output=True, text=True, timeout=5,
    )
    disks = []
    for block in json.loads(result.stdout)["blockdevices"]:
        if block.get("type") == "disk" and block.get("tran") == "usb":
            # Major:minor disambiguates nodes in this observation only. Roles are
            # reset after any disconnect; they are never persisted as identities.
            disks.append({"id": block["maj:min"], "path": block["name"],
                          "fstype": block.get("fstype"),
                          "readonly": block["ro"], "partitions": block.get("children", []),
                          "mountpoints": block.get("mountpoints", [])})
    return disks


class Roles:
    """First distinctly observed insertion is target; second is source.

    One USB disk already connected at startup is the first destination.
    Two already present, simultaneous insertions, >2 disks, or any disconnect
    are ambiguous. Re-arm only after observing zero disks.
    """
    def __init__(self):
        self.previous = None
        self.source = None
        self.target = None
        self.ambiguous = False

    def observe(self, ids):
        ids = list(ids)
        if len(ids) != len(set(ids)):
            raise BackupError("Duplicate device identity in observation")
        current = set(ids)
        if not current:
            self.source = self.target = None
            self.ambiguous = False
        elif self.previous is None:
            if len(current) == 1:
                self.target = next(iter(current))
            else:
                self.ambiguous = True
        elif current != self.previous:
            added = current - self.previous
            removed = self.previous - current
            if removed or len(added) != 1 or len(current) > 2:
                self.ambiguous = True
                self.source = self.target = None
            elif not self.ambiguous:
                inserted = next(iter(added))
                if self.target is None:
                    self.target = inserted
                elif self.source is None:
                    self.source = inserted
        self.previous = current
        return {"state": "AMBIGUOUS" if self.ambiguous else
                "ROLES_ASSIGNED" if self.source else
                "WAITING_FOR_SOURCE" if self.target else "WAITING_FOR_TARGET",
                "source": None if self.ambiguous else self.source,
                "target": None if self.ambiguous else self.target,
                "automatic_backup_enabled": False}
