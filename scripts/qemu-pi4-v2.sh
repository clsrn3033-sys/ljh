#!/bin/bash
# Boot the Pi4-built ARM64 kernel/rootfs on QEMU virt. This does not emulate Pi firmware/DSI.
# The OS disk is opened with QEMU snapshot mode: the source sdcard.img is never written.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
images=$(realpath -- "${1:-$project_root/output/pi4-v2-dsi-800x480-20261018/images}")
test -s "$images/Image"
test -s "$images/sdcard.img"
case_dir=$(mktemp -d /tmp/mebs-qemu-v2.XXXXXX)
trap 'rm -rf -- "$case_dir"' EXIT
qemu-img create -q -f qcow2 -F raw -b "$images/sdcard.img" "$case_dir/os.qcow2"
args=(
    -M virt -cpu cortex-a72 -m 1024 -smp 2 -nographic -nic none
    -kernel "$images/Image"
    -append 'root=/dev/vda2 rootwait ro console=ttyAMA0,115200 init=/bin/sh loglevel=4'
    -drive "file=$case_dir/os.qcow2,format=qcow2,if=none,id=os"
    -device virtio-blk-device,drive=os
)
if [[ -n ${MEBS_QEMU_QMP_SOCKET:-} ]]; then
    args+=(-qmp "unix:${MEBS_QEMU_QMP_SOCKET},server,nowait")
else
    args+=(-monitor none)
fi
if [[ $# -ge 2 ]]; then
    fixture_dir=$(realpath -- "$2")
    for file in external-ext4.img camera-vfat.img; do test -s "$fixture_dir/$file"; done
    cp -- "$fixture_dir/external-ext4.img" "$case_dir/external-ext4.img"
    args+=(
        -device qemu-xhci,id=xhci
        -drive "file=$case_dir/external-ext4.img,format=raw,if=none,id=external"
        -device usb-storage,bus=xhci.0,drive=external
    )
    if [[ ${MEBS_QEMU_ATTACH_CAMERA:-1} == 1 ]]; then
        cp -- "$fixture_dir/camera-vfat.img" "$case_dir/camera-vfat.img"
        args+=(
            -drive "file=$case_dir/camera-vfat.img,format=raw,if=none,id=camera"
            -device usb-storage,bus=xhci.0,drive=camera
        )
    fi
fi
qemu-system-aarch64 "${args[@]}"
