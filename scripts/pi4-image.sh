#!/bin/bash
# Build from source; never writes an SD card or installs host packages.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
buildroot_source=$(realpath -- "${1:-$project_root/vendor/buildroot-2026.08}")
build_output=$(realpath -m -- "${2:-$project_root/output/pi4-mebs}")
export PATH="$project_root/.local-build/tools/bin:$PATH"
export MEBS_FONT_SOURCE=${MEBS_FONT_SOURCE:-/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Regular.ttc}
export MEBS_FONT_LICENSE=${MEBS_FONT_LICENSE:-/usr/share/licenses/google-noto-sans-cjk-fonts/LICENSE}
board="$project_root/buildroot/board/mebs-pi4"
test -f "$buildroot_source/configs/raspberrypi4_64_defconfig"
test -f "$MEBS_FONT_SOURCE"
test -f "$MEBS_FONT_LICENSE"
mkdir -p "$build_output"
if [[ ! -e "$build_output/.config" ]]; then
    make -C "$buildroot_source" O="$build_output" BR2_EXTERNAL="$project_root/buildroot" raspberrypi4_64_defconfig
    config="$buildroot_source/utils/config"
    "$config" --file "$build_output/.config" \
        -d BR2_TOOLCHAIN_EXTERNAL -e BR2_TOOLCHAIN_BUILDROOT \
        -d BR2_KERNEL_HEADERS_AS_KERNEL -e BR2_KERNEL_HEADERS_6_12 \
        -e BR2_TOOLCHAIN_BUILDROOT_GLIBC -e BR2_TOOLCHAIN_BUILDROOT_CXX \
        -e BR2_PACKAGE_MEBS -e BR2_PACKAGE_MEBS_DISPLAY \
        -e BR2_PACKAGE_UTIL_LINUX_MOUNT \
        -e BR2_PACKAGE_RPI_FIRMWARE_INSTALL_DTB_OVERLAYS \
        -d BR2_TARGET_GENERIC_REMOUNT_ROOTFS_RW \
        --set-str BR2_SYSTEM_DHCP "" \
        --set-str BR2_TARGET_GENERIC_HOSTNAME mebs \
        --set-str BR2_TARGET_ROOTFS_EXT2_SIZE 192M \
        --set-str BR2_ROOTFS_OVERLAY "$board/overlay" \
        --set-str BR2_ROOTFS_POST_BUILD_SCRIPT "$board/post-build.sh" \
        --set-str BR2_ROOTFS_POST_IMAGE_SCRIPT "$board/post-image.sh" \
        --set-str BR2_LINUX_KERNEL_CONFIG_FRAGMENT_FILES "$board/linux.fragment" \
        --set-str BR2_PACKAGE_RPI_FIRMWARE_CONFIG_FILE "$board/config.txt" \
        --set-str BR2_PACKAGE_RPI_FIRMWARE_CMDLINE_FILE "$board/cmdline.txt"
    make -C "$buildroot_source" O="$build_output" olddefconfig
    printf '%s\n' "$project_root" > "$build_output/.mebs-image-build"
else
    [[ -f "$build_output/.mebs-image-build" ]] && [[ $(cat "$build_output/.mebs-image-build") == "$project_root" ]] || {
        echo 'Refusing unrelated existing configuration; select a new output directory.' >&2; exit 1;
    }
fi
for required in BR2_TOOLCHAIN_BUILDROOT_GLIBC BR2_TOOLCHAIN_BUILDROOT_CXX BR2_PACKAGE_MEBS BR2_PACKAGE_MEBS_DISPLAY BR2_PACKAGE_UTIL_LINUX_MOUNT; do
    grep -qx "$required=y" "$build_output/.config" || { echo "Missing required configuration: $required" >&2; exit 1; }
done
# A Buildroot local package is copied into build/ once. Refresh that generated
# package copy so an iterative image always contains the current MEBS sources.
if [[ -d "$build_output/build/mebs-0.1.0" ]]; then
    make -C "$buildroot_source" O="$build_output" mebs-dirclean
fi
make -C "$buildroot_source" O="$build_output" -j"${MEBS_JOBS:-6}"
test -s "$build_output/images/sdcard.img"
sha256sum "$build_output/images/sdcard.img"
