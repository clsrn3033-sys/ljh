# MEBS V2 Raspberry Pi 4B image

This image is built locally from the existing LJH repository and Buildroot
2026.08. The GitHub V1 baseline is preserved at
`preserve/mebs-v1-github-20261018`; V2 work is on
`feature/mebs-v2-pi4b-800x480-20261018`. No host disk is formatted by the
build or validation commands below.

## Build

On the Bazzite host, with the vendored Buildroot source and cached package
sources present:

```sh
bash scripts/pi4-dsi-image.sh vendor/buildroot-2026.08 output/pi4-v2-dsi-800x480-20261018
bash scripts/inspect-pi4-v2-image.sh output/pi4-v2-dsi-800x480-20261018/images
```

The output is `output/pi4-v2-dsi-800x480-20261018/images/sdcard.img`.
The build script also prints the SHA-256 checksum. Write it to a *confirmed,
disposable* microSD card only after checking its device path. The image is a
raw disk image with Raspberry Pi firmware, an ARM64 kernel, a read-only
Buildroot root partition, and a separate OS-owned settings partition.

## V2 behavior and limits

- The 800×480 black/cyan UI and boot logo retain the approved V1 design.
  The checked GitHub V1 artwork credits `제49기 보도부 이정헌` and
  `Produced by 이정헌`; V2 has not silently changed those names.
  The optional preview is generated with `PYTHONPATH=. python3
  scripts/preview-journey.py --output artifacts/v2-boot-menu-preview`.
- V2 has a persistent manual-brightness control, night mode, touch lock,
  screen off, safe-removal indication, and a safe-shutdown queue. Physical
  backlight control remains inactive until the panel's sysfs backlight path
  is known; the slider must not be presented as verified hardware dimming.
  V1 settings are read and migrated without the removed automatic-brightness
  preference.
- BH1750 and automatic brightness have been removed. INA226 and DS3231 remain
  opt-in until their real wiring is confirmed. The charger NTC is a hardware
  feature, not a Raspberry Pi GPIO sensor.
- The 5-inch 800×480 MIPI DSI panel and touch controller model are unknown.
  No panel-specific overlay or touch input path is guessed. A generic
  framebuffer path is enabled as a fallback for compatible HDMI output;
  actual DSI display, touch, backlight, and 60 Hz must be tested on the Pi.
- The V1 policy is retained pending explicit resolution of contradictory V2
  handoff items: the target does not require `수정금지.txt`, and SD formatting is
  disabled. This prevents any unapproved destructive behavior in the image.
- QEMU `virt` can exercise ARM64 Linux and file-backed storage but does not
  reproduce Raspberry Pi firmware, DSI, touchscreen, GPIO, or USB power.
  `bash scripts/qemu-pi4-v2.sh output/pi4-v2-dsi-800x480-20261018/images`
  boots the same kernel and raw image through a temporary qcow2 overlay and a shell;
  typing `poweroff -f` or closing QEMU ends the session. An optional second
  argument accepts the disposable directory created by
  `bash scripts/qemu-usb-fixtures.sh` to attach two virtual USB disks.

## Validation record

- Buildroot 2026.08 build: **PASS**, produced the ARM64 Pi 4B image locally.
- Host suite: **PASS**, `python3 -m unittest discover -s tests -q` — 118 tests.
- Image structure: **PASS**, `scripts/inspect-pi4-v2-image.sh` found the Pi 4
  firmware, `Image`, BCM2711 DTB, partitions, application, and V2 profile.
- Filesystems: **PASS**, read-only `fsck.fat -n` and `e2fsck -fn` on boot,
  root, and settings filesystems.
- QEMU ARM64 `virt`: **PASS** for kernel/userspace boot, headless `READY`,
  conservative `AMBIGUOUS` when both removable disks appear together, and the
  sequential target-then-source backup flow. One XML fixture was copied and
  SHA-256 matched; the virtual camera image remained unchanged and the app
  reported `SAFE_TO_REMOVE`.
- Repeated QEMU runs: scheduled at 30-minute intervals through 06:00 KST on
  2026-10-19. The final count is recorded in `TEST_RESULTS_V2.md` when the
  schedule ends; do not interpret the run currently in progress as complete.
- Physical Pi 4B boot, DSI/touch/backlight, GPIO, power behavior, and the
  five-second cold-boot target: **NOT TESTED**. QEMU `virt` cannot establish
  those hardware results.

Detailed run logs are under `TEST_LOGS/`. The test harness and scheduling
issues found during setup are documented in `TEST_FAILURES_V2.md`.
