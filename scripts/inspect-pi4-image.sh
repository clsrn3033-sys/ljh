#!/bin/bash
# Read-only structural check of a locally produced Pi4 SD image.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
input=$(realpath -- "${1:-$project_root/output/pi4-hdmi/images}")
if [[ -f "$input" ]]; then
    images=$(dirname -- "$input")
else
    images=$input
fi
test -s "$images/sdcard.img"
test -s "$images/boot.vfat"
test -s "$images/rootfs.ext4"
file -b "$images/boot.vfat" | grep -q 'FAT (32 bit)'
printf 'BOOT  FAT32 filesystem\n'
for boot_file in config.txt cmdline.txt start4.elf fixup4.dat Image bcm2711-rpi-4-b.dtb; do
    mdir -i "$images/boot.vfat" "::$boot_file" >/dev/null
    printf 'BOOT  %s\n' "$boot_file"
done
mtype -i "$images/boot.vfat" ::config.txt | grep -q '^dtoverlay=vc4-kms-v3d'
mtype -i "$images/boot.vfat" ::cmdline.txt | grep -q 'root=/dev/mmcblk0p2'
for root_file in /etc/mebs/appliance /etc/init.d/S50mebs /usr/bin/mebs \
                 /usr/lib/mebs/mebs/appliance.py /usr/share/fonts/mebs/NotoSansCJK-Regular.ttc; do
    debugfs -R "stat $root_file" "$images/rootfs.ext4" 2>/dev/null | grep -q 'Inode:'
    printf 'ROOT  %s\n' "$root_file"
done
fdisk -l "$images/sdcard.img"
sha256sum "$images/sdcard.img"
