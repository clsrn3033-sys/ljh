# V2 Raspberry Pi 4B 이미지 빌드 결과

- 상태: **PASS** (파일 생성·정적 검사), 실제 Pi 4B 부팅은 **HARDWARE NOT TESTED**.
- Raspberry Pi IMG: `/var/home/bazzite/ljh/output/pi4-v2-ina-v1-20261019/images/sdcard.img`; 311427072 bytes; SHA-256 `5be3d88e1106d4631cb3af74fbd7a4e30d9b69fe0cb62605c579ab0d5cf76081`.
- 다운로드/전송용 zstd 파일: `/var/home/bazzite/ljh/output/pi4-v2-ina-v1-20261019/images/sdcard.img.zst`; SHA-256 `6cecd30329cf72ff50bb2c1ace2d00c0cde78100b7eb13d064d709d3aa255d2f`. 복원 시 `zstd -d -c sdcard.img.zst > sdcard.img`.
- QEMU virt IMG: `/var/home/bazzite/ljh/output/pi4-v2-ina-qemu-v1-20261019/images/qemu-virt.img`; SHA-256 `3215d7926f3a340de4afdfca2bf5c319a48e04adbd4bdc333c1e9297332a4cdd`. 이 이미지는 fstab의 OS 설정 파티션 이름만 vda3으로 적응한 별도 테스트용입니다.
- 생성 방식: BC250에서 기존 Buildroot 소스로 로컬 빌드된 커널/펌웨어/루트FS를 기반으로 **새 파일로 복사**하고 V2 Python 드라이버, UI/런타임, hardware.json, GPIO JSON을 주입했습니다. 이번 단계에 커널을 다시 컴파일한 것은 아닙니다. 원래 이미지 SHA는 provenance JSON에 남아 있습니다.
- I²C: `dtparam=i2c_arm=on`, 커널 `CONFIG_I2C_BCM2835=y`, `CONFIG_I2C_CHARDEV=y`. 40핀의 GPIO2/3 설계 대응. 실제 `/dev/i2c-1` 생성은 실기기에서 확인해야 합니다.
- 정적 확인: FAT의 `config.txt`, `cmdline.txt`, `start4.elf`, `fixup4.dat`, `Image`, bcm2711-rpi-4-b.dtb; 루트FS의 MEBS init 서비스/드라이버/설정; e2fsck. 로그 `tests/v2-ina/logs/image-inspection.log`, `rootfs-fsck.log`.

|번호|형식 코드|시작 섹터|섹터 수|
|---:|---|---:|---:|
|1|c|2048|196608|
|2|83|198656|393216|
|3|83|591872|16384|

- QEMU ARM64 virt 기능 테스트: **T01:PASS, T02:PASS, T03:PASS, T04:PASS, T05:PASS, T06:PASS, T07:PASS, T08:PASS, T09:PASS, T10:PASS, T11:PASS, T12:BLOCKED**. QEMU virt 성공은 Raspberry Pi 4B 실물 부팅 성공을 뜻하지 않습니다.
- QEMU 부팅 시간 관측: **7.17~7.64초**. 5초 실물 부팅 목표는 달성 여부를 판정하지 않았습니다.
- 로그: `tests/v2-ina/logs/image-build.log`, `qemu-image-build.log`, `qemu-T*.log`.
- 명령: `python3 tests/v2-integration/build_fixed_image.py output/pi4-v2-recovery-v4-20261019/images output/pi4-v2-ina-v1-20261019/images` (새 출력 경로만 사용).
