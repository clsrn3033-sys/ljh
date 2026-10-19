#!/bin/bash
# Reuse the locally built V2 Buildroot toolchain/kernel via a Btrfs CoW copy.
# Never modify V2 outputs or physical media. All new packages build from source.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
base=${MEBS_V2_BUILD_OUTPUT:-$repo/output/pi4-v2-dsi-800x480-20261018}
result=${MEBS_V3_BUILD_OUTPUT:-$repo/output/pi4-v3-800x480-20261019}
buildroot=$repo/vendor/buildroot-2026.08
export PATH="$repo/.local-build/tools/bin:$PATH"
[[ -f "$base/.config" && -d "$base/host" && -f "$base/images/sdcard.img" ]] || {
    echo 'Local V2 Buildroot output is required' >&2; exit 1;
}
[[ "$base" != "$result" && ! -e "$result/MABS_V3_RPi4.img" ]] || {
    echo 'Refusing to overwrite a V3 image or use V2 output' >&2; exit 1;
}
if [[ ! -d "$result" ]]; then
    cp -a --reflink=always -- "$base" "$result"
fi
[[ -f "$result/.mebs-image-build" ]] || { echo 'Unrelated output directory' >&2; exit 1; }
export MEBS_FONT_SOURCE=${MEBS_FONT_SOURCE:-/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Regular.ttc}
export MEBS_FONT_LICENSE=${MEBS_FONT_LICENSE:-/usr/share/licenses/google-noto-sans-cjk-fonts/LICENSE}
test -s "$MEBS_FONT_SOURCE"
test -s "$MEBS_FONT_LICENSE"
config=$buildroot/utils/config
"$config" --file "$result/.config" \
    -e BR2_PACKAGE_MEBS_EXPLORER_V3 \
    -e BR2_PACKAGE_FFMPEG -e BR2_PACKAGE_FFMPEG_FFMPEG \
    -e BR2_PACKAGE_FFMPEG_FFPROBE -e BR2_PACKAGE_FFMPEG_SWSCALE \
    -e BR2_PACKAGE_JPEG \
    -d BR2_PACKAGE_FFMPEG_FFPLAY \
    --set-str BR2_TARGET_ROOTFS_EXT2_SIZE 192M
make -C "$buildroot" O="$result" BR2_EXTERNAL="$repo/buildroot" olddefconfig
grep -qx 'BR2_PACKAGE_MEBS_EXPLORER_V3=y' "$result/.config"
grep -qx 'BR2_PACKAGE_FFMPEG_FFPROBE=y' "$result/.config"
make -C "$buildroot" O="$result" BR2_EXTERNAL="$repo/buildroot" mebs-dirclean
# Pillow was already built without JPEG in V2; enabling the library alone
# would leave its native extension unable to decode the camera JPG files.
make -C "$buildroot" O="$result" BR2_EXTERNAL="$repo/buildroot" python-pillow-dirclean
make -C "$buildroot" O="$result" BR2_EXTERNAL="$repo/buildroot" -j"${MEBS_JOBS:-6}"
test -s "$result/images/sdcard.img"
test -x "$result/target/usr/bin/ffprobe"
test -x "$result/target/usr/bin/ffmpeg"
cp --no-clobber -- "$result/images/sdcard.img" "$result/MABS_V3_RPi4.img"
sha256sum "$result/MABS_V3_RPi4.img"
