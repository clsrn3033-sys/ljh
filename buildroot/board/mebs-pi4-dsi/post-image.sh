#!/bin/sh
set -eu
install -m 0644 "${BR2_EXTERNAL_MEBS_PATH}/board/mebs-pi4-dsi/genimage.cfg" "${BINARIES_DIR}/genimage.cfg"
# Assemble only the Raspberry Pi 4 boot files and the Buildroot rootfs.
temp=$(mktemp -d "${BUILD_DIR}/mebs-genimage.XXXXXX")
trap 'rm -rf -- "$temp"' EXIT
mkdir -p "$temp/root" "$temp/work"
genimage --rootpath "$temp/root" --tmppath "$temp/work" \
    --inputpath "$BINARIES_DIR" --outputpath "$BINARIES_DIR" \
    --config "${BINARIES_DIR}/genimage.cfg"
