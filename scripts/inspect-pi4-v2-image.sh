#!/bin/bash
# Read-only checks of a locally built MEBS V2 Pi4 image; never opens host disks.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
images=$(realpath -- "${1:-$project_root/output/pi4-v2-dsi-800x480-20261018/images}")
bash "$project_root/scripts/inspect-pi4-image.sh" "$images"
for name in mebs-settings.ext4 boot.vfat rootfs.ext4 Image sdcard.img; do
    test -s "$images/$name" || { echo "Missing $name" >&2; exit 1; }
done
python3 - "$images" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

images = Path(sys.argv[1])
kernel = images / 'Image'
with kernel.open('rb') as source:
    source.seek(0x38)
    assert source.read(4) == b'ARMd', 'kernel is not an ARM64 Image'
parts = json.loads(subprocess.check_output(['sfdisk', '--json', str(images / 'sdcard.img')]))['partitiontable']['partitions']
assert len(parts) == 3, f'expected boot, root and settings partitions, found {len(parts)}'
assert [part['type'].lower() for part in parts] == ['c', '83', '83']
assert all(part['size'] > 0 for part in parts)
print('PARTITIONS  boot FAT32 / root ext4 / settings ext4')
print('KERNEL      ARM64 Image magic')
PY
debugfs -R 'cat /etc/fstab' "$images/rootfs.ext4" 2>/dev/null | grep -q '/dev/mmcblk0p3 /var/lib/mebs ext4'
debugfs -R 'stat /usr/lib/mebs/mebs/assets/mebs-logo-mask.png' "$images/rootfs.ext4" 2>/dev/null | grep -q 'Inode:'
debugfs -R 'stat /etc/mebs/hardware.json' "$images/rootfs.ext4" 2>/dev/null | grep -q 'Inode:'
echo 'ROOT        settings mount, V2 hardware profile and logo present'
