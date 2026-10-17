#!/bin/bash
# Create two disposable FILES for QEMU. Never opens a host block device.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
case_dir=$(mktemp -d /tmp/mebs-qemu-usb.XXXXXX)
truncate -s 128M "$case_dir/external-ext4.img"
mkfs.ext4 -q -F "$case_dir/external-ext4.img"
mkfs.vfat -C "$case_dir/camera-vfat.img" 32768 >/dev/null
mmd -i "$case_dir/camera-vfat.img" ::DCIM
mcopy -i "$case_dir/camera-vfat.img" "$project_root/tests/fixtures/C0001.XML" ::DCIM/C0001.XML
printf '%s\n' "$case_dir"
