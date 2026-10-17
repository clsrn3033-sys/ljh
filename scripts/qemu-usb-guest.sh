#!/bin/bash
# Isolated ARM virtual board, disposable file-backed USB devices.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
case_dir=$(realpath -- "${1:?Pass the directory from qemu-usb-fixtures.sh}")
images=$(realpath -- "${2:-$project_root/output/pi4-hdmi/images}")
test -f "$case_dir/camera-vfat.img"
test -f "$case_dir/external-ext4.img"
guest_root=${MEBS_QEMU_ROOT:-/tmp/mebs-qemu-final-root.qcow2}
test -f "$guest_root"
timeout --signal=TERM "${MEBS_QEMU_TIMEOUT:-120}" qemu-system-aarch64 \
    -M virt -cpu cortex-a72 -m 1024 -smp 2 -display none -serial stdio -monitor none \
    -kernel "$images/Image" \
    -append 'root=/dev/vda rootwait ro console=ttyAMA0,115200 init=/bin/sh quiet loglevel=3' \
    -drive file="$guest_root",format=qcow2,if=none,id=root \
    -device virtio-blk-device,drive=root \
    -device qemu-xhci,id=xhci \
    -drive file="$case_dir/external-ext4.img",format=raw,if=none,id=external \
    -device usb-storage,bus=xhci.0,drive=external \
    -drive file="$case_dir/camera-vfat.img",format=raw,if=none,id=camera,readonly=on \
    -device usb-storage,bus=xhci.0,drive=camera
