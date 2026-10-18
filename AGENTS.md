# MEBS Pi4B development handoff

Read `ver 1/README.md`, its decisions and handoff instructions first. They are the latest user-approved baseline. Older requirements/history can contain other boards, resolutions, credits and packaging targets.

- Target: Raspberry Pi 4B ARM64, Buildroot 2026.08 lightweight raw `.img`, 800x480 landscape DSI/capacitive touch. No desktop/X11. Preserve headless backup.
- Approved identity: supplied MEBS logo, black/cyan theme, `제49기 보도부 이정헌 / Produced by 이정헌`. Keep the supplied JPEG byte-for-byte; runtime credits use the corrected name. Do not arbitrarily redesign accepted UI.
- First distinctly observed USB=backup destination, second=source SD; ambiguous order blocks backup until all removed and reconnected in order. Do not use 수정금지.txt/.text marker files.
- Preserve existing engine, original file tree/XML/bytes/metadata/SHA-256 and failure/pending-job recovery boundaries. Target ext4; source vfat/exfat/ntfs/ext4 currently. No automatic source deletion/format; manual formatter is not implemented. Safe removal requires verification+sync+normal unmount.
- Keep UI/sensors/settings separate from backup worker. Active backup shutdown is queued, never immediate. No GPIO battery cutoff, buzzer, vibration, ADS1115 or battery/case-temperature UI.
- Hardware model/DSI touch/shunt/cell/BMS/5V regulator remain unknown. 8.4V is reported 2S full-charge information only. Never feed it directly to Pi 5V. Keep unconfirmed drivers/sensors/thresholds disabled; don't invent specifications or use flags as proof.
- Keep original-source/releases and any earlier OS images unchanged. Use separate outputs and temporary/virtual disks for tests; never format physical host/user media. Do not create Git worktrees without user instruction. No host shutdown.
- Verified baseline: 118 host software tests; UI is simulated. No new Pi4B image, QEMU boot, DSI/real sensor/5-second boot result exists. Buildroot download blocked by proxy CONNECT403 at host-pkgconf. Recheck actual access after a meaningful network change. Preserve TLS/signature/hash verification; don't bypass protection.
- Reproduce commands in `ver 1/04_인계서.md`. Run appropriate tests after code changes and report real outcomes. A successful configuration/compile/PNG is not a bootable image.
- This handoff's GitHub commit/push is explicitly authorized by the user. Use existing repository, ordinary commits/non-force push, preserve remote work. Do not publish secrets or old large images/caches. Future external publication requires relevant user authorization.
