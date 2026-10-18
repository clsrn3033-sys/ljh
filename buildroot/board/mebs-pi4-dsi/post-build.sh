#!/bin/sh
set -eu
target=$1
# Required Pi 4, USB, filesystem and VC4 drivers are built in. The broad Pi
# defconfig's optional module collection is unnecessary on this appliance.
rm -rf -- "$target/lib/modules"
# The HDMI screen belongs to MEBS, not an overlapping console login prompt.
sed -i '/^tty1::/d' "$target/etc/inittab"
# Logs and mountpoints live in /run (tmpfs); the appliance root remains read-only.
install -d "$target/etc/mebs" "$target/usr/share/fonts/mebs"
sed -i -E 's#^(/dev/root[[:space:]]+/[[:space:]]+)ext2([[:space:]]+)rw,noauto#\1ext4\2ro,noauto#' "$target/etc/fstab"
printf '%s\n' 'MEBS Pi4 appliance image' > "$target/etc/mebs/appliance"
test -n "${MEBS_FONT_SOURCE:-}" || { echo 'MEBS_FONT_SOURCE is required' >&2; exit 1; }
test -n "${MEBS_FONT_LICENSE:-}" || { echo 'MEBS_FONT_LICENSE is required' >&2; exit 1; }
install -m 0644 "$MEBS_FONT_SOURCE" "$target/usr/share/fonts/mebs/NotoSansCJK-Regular.ttc"
install -m 0644 "$MEBS_FONT_LICENSE" "$target/usr/share/fonts/mebs/OFL.txt"

# One OS-owned settings partition, never a removable USB mount target.
install -d "$target/var/lib/mebs"
sed -i '\|/var/lib/mebs|d' "$target/etc/fstab"
printf '%s\n' '/dev/mmcblk0p3 /var/lib/mebs ext4 rw,nosuid,nodev,noexec,noatime 0 0' >> "$target/etc/fstab"
