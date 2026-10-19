# MEBS Pi4B development handoff

V1's former `ver 1/` tree was removed only on the V3 branch at the user's request. Its exact contents remain in `preserve/mebs-v1-github-20261018` and Git history. Read `docs/v3/README.md` and the preserved V2 branch before changing V3. Older requirements/history can contain other boards, resolutions, credits and packaging targets.

- Target: Raspberry Pi 4B ARM64, Buildroot 2026.08 lightweight raw `.img`, 800x480 landscape DSI/capacitive touch. No desktop/X11. Preserve headless backup.
- Approved identity: supplied MEBS logo, black/cyan theme, `제49기 보도부 이정헌 / Produced by 이정헌`. Keep the supplied JPEG byte-for-byte; runtime credits use the corrected name. Do not arbitrarily redesign accepted UI.
- First distinctly observed USB=backup destination, second=source SD; ambiguous order blocks backup until all removed and reconnected in order. Do not use 수정금지.txt/.text marker files.
- Preserve existing engine, original file tree/XML/bytes/metadata/SHA-256 and failure/pending-job recovery boundaries. Target ext4; source vfat/exfat/ntfs/ext4 currently. No automatic source deletion/format; manual formatter is not implemented. Safe removal requires verification+sync+normal unmount.
- Keep UI/sensors/settings separate from backup worker. Active backup shutdown is queued, never immediate. No GPIO battery cutoff, buzzer, vibration, ADS1115 or battery/case-temperature UI.
- Hardware model/DSI touch/shunt/cell/BMS/5V regulator remain unknown. 8.4V is reported 2S full-charge information only. Never feed it directly to Pi 5V. Keep unconfirmed drivers/sensors/thresholds disabled; don't invent specifications or use flags as proof.
- Keep V1/V2 Git branches, original-source/releases and any earlier OS images unchanged. Use separate outputs and temporary/virtual disks for tests; never format physical host/user media. Do not create Git worktrees without user instruction. No host shutdown.
- V3 evidence and commands are in `docs/v3/TEST_REPORT.md` and `docs/v3/README.md`: 151 host tests; a locally built ARM64 Pi4 image and QEMU `virt` software tests exist. QEMU is not Pi4 hardware. DSI/real sensor/5-second hardware boot results do not exist. Preserve TLS/signature/hash verification; don't bypass protection.
- Run appropriate tests after code changes and report real outcomes. A successful configuration/compile/PNG is not proof of Pi4 hardware boot.
- V3 commit locally only; a new GitHub push/publication requires user authorization. Preserve remote work; do not publish secrets or old large images/caches.
