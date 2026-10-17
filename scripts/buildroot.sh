#!/bin/bash
# Operates only on caller-supplied Buildroot sources and output directory.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ $# -ne 3 ]]; then
    echo "Usage: bash scripts/buildroot.sh BUILDROOT_SOURCE OUTPUT_DIR {qemu_x86_64_defconfig|raspberrypi4_64_defconfig}" >&2
    exit 2
fi
buildroot_source=$(realpath -- "$1")
build_output=$(realpath -m -- "$2")
board_config=$3
case "$board_config" in
    qemu_x86_64_defconfig|raspberrypi4_64_defconfig) ;;
    *) echo 'Unsupported board: Orange Pi support requires a verified BSP first.' >&2; exit 2 ;;
esac
if [[ ! -f "$buildroot_source/Makefile" || ! -f "$buildroot_source/configs/$board_config" ]]; then
    echo 'Expected an existing Buildroot source checkout with the requested board configuration.' >&2
    exit 2
fi
if [[ -e "$build_output/.config" ]]; then
    echo 'Refusing to replace an existing output configuration; choose a new OUTPUT_DIR.' >&2
    exit 2
fi
mkdir -p -- "$build_output"
make -C "$buildroot_source" O="$build_output" BR2_EXTERNAL="$project_root/buildroot" "$board_config"
"$buildroot_source/utils/config" --file "$build_output/.config" -e BR2_PACKAGE_MEBS
# Use a locally built toolchain instead of downloading a finished external one.
"$buildroot_source/utils/config" --file "$build_output/.config" -d BR2_TOOLCHAIN_EXTERNAL -e BR2_TOOLCHAIN_BUILDROOT
make -C "$buildroot_source" O="$build_output" olddefconfig
if ! grep -qx 'BR2_PACKAGE_MEBS=y' "$build_output/.config"; then
    echo 'MEBS dependencies were not satisfied by the chosen board configuration.' >&2
    exit 1
fi
make -C "$buildroot_source" O="$build_output" -j"${MEBS_JOBS:-4}"
