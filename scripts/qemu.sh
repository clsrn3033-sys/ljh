#!/bin/bash
# Emulation with TCG; does not require /dev/kvm or expose host disks/network.
set -euo pipefail
if [[ $# -ne 1 ]]; then
    echo 'Usage: bash scripts/qemu.sh BUILDROOT_OUTPUT_DIR' >&2
    exit 2
fi
images=$(realpath -- "$1")/images
for file in bzImage rootfs.ext2; do
    if [[ ! -f "$images/$file" ]]; then
        echo "Missing locally built image: $images/$file" >&2
        exit 2
    fi
done
exec qemu-system-x86_64 -machine pc -accel tcg -m 512 -smp 2 -nographic \
    -nic none -snapshot -kernel "$images/bzImage" \
    -drive "file=$images/rootfs.ext2,format=raw,if=virtio" \
    -append 'root=/dev/vda console=ttyS0'
