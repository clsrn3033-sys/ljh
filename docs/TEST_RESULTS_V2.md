# MEBS V2 validation results

Test date: 2026-10-19 (Asia/Seoul). Tests used the locally built image from
`output/pi4-v2-dsi-800x480-20261018/images`; no host or physical disk was
formatted.

| Check | Result | Evidence |
|---|---|---|
| Host unit suite | PASS, 118 tests | `docs/logs/v2-host-tests.log` |
| Pi 4B image build | PASS | `docs/logs/v2-pi4-build.log` |
| ARM64 image / Pi firmware / partition inspection | PASS | `scripts/inspect-pi4-v2-image.sh` |
| Boot FAT32 and root/settings ext4 integrity checks (read-only) | PASS | `fsck.fat -n`, `e2fsck -fn` |
| QEMU ARM64 `virt` boot and no-media READY | PASS | `TEST_LOGS/v2-qemu-e2e-01-20261019-021051.log` and scheduled logs |
| Target then camera-source hotplug backup | PASS | Scheduled run 1 log below |
| Source/target SHA-256 match | PASS | `5c81656654ab670796a06d1c1d14bf3f7ddbdddb47316d01ee27c05056a459fa` |
| Virtual source preserved | PASS | `source_unchanged=true`; source is attached read-only |
| Actual Pi 4B, DSI/touch/GPIO, cold boot under 5s | NOT TESTED | Requires physical hardware |

Scheduled repeat command:

```sh
python3 scripts/test-pi4-v2-qemu.py --repeat-until 06:00 --interval-minutes 30 --log-dir TEST_LOGS
```

The schedule was restarted with the corrected wall-clock interval calculation
at 02:13 KST. Scheduled run 1 passed at 02:13:54, reached `SAFE_TO_REMOVE`,
verified one XML file, and left the virtual source image unchanged. All eight scheduled runs completed successfully (02:13 through 05:43 KST);
the final records are in `TEST_LOGS/v2-qemu-repeat-summary.log`.
The pre-fix rapid runs are retained as diagnostic logs and excluded from the
30-minute scheduled count.

Image artifacts:

- Raw: `output/pi4-v2-dsi-800x480-20261018/images/sdcard.img`
- Compressed: `artifacts/MEBS-V2-Pi4B-20261019.img.zst` (36.4 MiB)
- SHA-256 values: `artifacts/MEBS-V2-Pi4B-20261019.sha256`

The QEMU test is a functional Linux/file-backed-storage check, not a Pi 4
hardware emulation. The GUI storyboard is a software preview, not a captured
QEMU framebuffer or proof of the real DSI panel.

## Expanded full-init integration tests

See [the V2 integration report](../tests/v2-integration/TEST_REPORT.md).
It supersedes the limited XML-only smoke results for deployment decisions.
The original image has a confirmed FAT32 Unicode filename defect. A new
source/config-patched candidate is available; original images remain intact.
Passing the earlier eight smoke runs does not establish full V2 compliance.
