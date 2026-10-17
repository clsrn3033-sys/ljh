# MEBS 480×320 Runtime UI — isolated handoff

This is a **new, non-destructive renderer**, not a replacement of existing `mebs/runtime_ui.py` or the main branch. The authoritative prior baseline is the Library artifact `MEBS_UI_480x320_v4_Source_Preview.zip` (`mebs/runtime_ui_480.py`, preview GIF/PNG, README, 7 reported passing tests). The original ZIP bytes could not be materialized in this automation environment, so **this code has not been bytewise compared with v4 and is not a claim of faithful v4 reproduction**. Do not discard or overwrite the v4 ZIP.

## Contract

`from mebs.runtime_ui_480 import render` then `img = render(snapshot)` produces an RGB 480×320 Pillow image. Snapshot is a read-only dictionary; fields: `state`, `total_bytes`, `copied_bytes`, `verified_bytes`, `cpu_temp_c`, `ram_percent`, `uptime_seconds`, `detail`. Missing telemetry displays `--`. Only backup service events can move state to `COMPLETE` (VERIFIED) or `SAFE_TO_REMOVE` (after successful unmount/eject). Renderer never mounts, copies, deletes, formats, or ejects. No back button.

State progression: `READY` → `WAITING_SOURCE` → `CONNECTED` → `COPYING` → `VERIFYING` → `COMPLETE` → `UNMOUNTING` → `SAFE_TO_REMOVE`. Errors and cancellation are separate. `COMPLETE` means verified **but still unsafe to remove**. The service must be authoritative; never infer safe-to-remove from 100% copy progress.

## Preview & tests

```
python -m unittest discover -s tests -v
python -m mebs.runtime_ui_480 --state COPYING --output preview/copying.png
```

Requires Pillow and a Korean font for proper text display. GIF/PNG previews are synthetic; no hardware was accessed. SPI ILI9488 480×320 panel wiring, driver, RGB565 conversion, byte order, framebuffer, Pi4 Buildroot integration, boot-time and real backup event telemetry remain **unverified**.

## Codex handoff (order matters)

1. On BC250 Bazzite inspect `/var/home/bazzite/ljh`: `git status --porcelain=v1 -uall`, `git branch -avv`, `git log -5 --oneline --all`; preserve uncommitted and interrupted work. Finish pre-existing tasks first; do not reset/clean/force-push.
2. Fetch the new remote feature branch, compare with v4 ZIP and any newer local work. Merge/cherry-pick only after review; do not overwrite existing main or local UI.
3. Connect CPU temperature from valid `/sys/class/thermal/...` sensor and RAM/uptime from `/proc/meminfo`, `/proc/uptime`, read-only. Validate CPU thermal zone mapping on Pi4 and show N/A when absent.
4. Connect real backup copy/verify/eject events. `COMPLETE` must not imply `SAFE_TO_REMOVE`. Never auto-delete or auto-format source SD.
5. Check **actual purchased** 4-inch ILI9488 module's pinout, SPI mode, logic voltage, bus frequency, RGB565/18-bit conversion, frame ordering and rotation; 480×320 landscape is fixed.
6. Build Pi4B Buildroot image, run QEMU unit/event tests, then hardware test when available. Record what remains unverified. Do not claim BC250 Codex was remotely started by this handoff.