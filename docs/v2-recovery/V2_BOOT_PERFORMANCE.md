# V2 부팅 시간 측정

2026-10-19 KST. [v4 이미지 실제 20회 결과](../../tests/v2-integration/boot-runs/20261019-073645/summary.json).
같은 QEMU COW 시스템 디스크를 20회 부팅·정상 종료하며 기존 설정 파티션을 유지했다.

| 항목 | 실제 값 |
|---|---:|
| ARM64 virt 부팅 성공 | 20/20 |
| QEMU 시작→MEBS READY 최단 | 7.266초 |
| 중앙값 | 7.416초 |
| 최장 | 7.629초 |
| guest PID1 | BusyBox `init` 확인 |
| OS 설정 파티션 | 20회 모두 마운트 확인 |
| Raspberry Pi 4B cold boot | **HARDWARE NOT TESTED** |

측정은 QEMU 프로세스 시작부터 시리얼 콘솔 로그인·`status.json` 폴링으로
`READY`를 확인하기까지의 호스트 wall clock이다. GUI 첫 프레임/DSI 출력 시각이
아니며 실제 Pi 전원 인가→`BACKUP READY` 5초 목표의 통과 증거가 아니다.

[첫 실행 콘솔](../../tests/v2-integration/boot-runs/20261019-073645/boot-01.serial.log)에서
ARM64 kernel 6.12.61-v8 시작, syslog/klog/network/crond 순서, Buildroot 로그인,
PID1 `init`, 설정 파티션, 앱 READY를 확인했다. 이 init 콘솔 출력에는 각 서비스의
시작·종료 시각이 없어 **단계별 초 단위 소요 시간은 측정하지 못했다.**
실기기에서 firmware/EEPROM 시작점, 커널/장치 초기화, S50mebs, 첫 화면 시각을
같은 시계로 기록해야 5초 목표를 판단할 수 있다.

재실행:

```sh
python3 tests/v2-integration/boot_repeat.py \
  --images output/pi4-v2-recovery-v4-20261019/images \
  --prepared-os output/pi4-v2-recovery-qemu-v4-20261019/images/qemu-virt.img --count 20
```

실행별 시간과 개별 콘솔은
[`boot-runs/20261019-073645`](../../tests/v2-integration/boot-runs/20261019-073645)에 남겼다.
