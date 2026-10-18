# MEBS V2 test failures and follow-up

This log distinguishes test harness/setup failures from product behavior.

| Finding | Type | Resolution / status |
|---|---|---|
| First test inspected service status before the asynchronous init completed | Harness timing | Increased readiness wait and retained diagnostic output; rerun passed. |
| Test tried mounting verification media under read-only `/mnt` | Harness | Changed mountpoint to writable runtime path `/run/verify`; rerun passed. |
| Restricted process could not bind QEMU's QMP Unix socket | Environment | Re-ran the explicitly requested QEMU test with the needed permission; passed. |
| Repeat scheduler treated monotonic uptime as epoch time, causing rapid repeats | Harness defect | Replaced epoch conversion with a captured timezone-aware wall-clock start; corrected schedule restarted at 02:13 KST. Rapid pre-fix runs are not counted as scheduled repetitions. |
| Test image clock was near Unix epoch; backup folder timestamp contained 1970 | QEMU environment / product follow-up | QEMU `virt` run has no configured real-time source in this test. Verify time policy on Pi 4 and determine whether optional DS3231 or another trusted clock source is required before field use. No date naming policy was inferred or changed. |

No data-loss or hash-mismatch failure occurred in completed successful QEMU
backup runs. Hardware failures are not ruled out by these virtual tests.

## Improvements to schedule

- Add broader fixtures and rerun the requested exception cases (capacity,
  disconnect, write/read errors, collisions, interrupted copy, tampering).
- Set a deterministic emulated RTC time in the QEMU harness so timestamp tests
  are reproducible and do not use 1970.
- Confirm exact DSI/touch panel, backlight control path, and real RTC/power
  wiring before enabling hardware-specific support.
- Confirm the user decision for target identification and any post-verify
  formatting policy. Formatting remains disabled for safety.
