# V3 Pi4B 성능 모드 — 구현 및 검증 기록

대상은 Raspberry Pi 4B ARM64 Buildroot 이미지다. 기존 V1/V2와 이전 V3 이미지는 변경하지 않았다. **현 단계에서 1.8/2.0GHz 실물 안정성은 HARDWARE NOT TESTED이며 기본 이미지에서는 활성화되지 않는다.** `arm_freq=1500`, `arm_boost=0`을 기본 부팅 FAT 설정에 넣고 `over_voltage`·`force_turbo`는 넣지 않았다. Pi4B 리비전에 따라 펌웨어 기본 클럭이 1.5GHz 또는 1.8GHz일 수 있으므로 기본 부팅값을 명시했다. [Raspberry Pi 공식 config.txt 설명](https://www.raspberrypi.com/documentation/computers/config_txt.html).

## 구현

- **부팅 설정:** `buildroot/board/mebs-pi4-dsi/config.txt`의 1.5GHz는 펌웨어 부팅 상한이다. `scripts/pi4-v3-clock-candidate.sh`는 기존 `.img`를 CoW 복사해 새 **UNVALIDATED TEST** 이미지의 FAT `config.txt`만 1.8 또는 2.0GHz로 바꾼다. 원본 이미지는 그대로 두며 실제 장비에서 확인하기 전에는 배포용으로 사용하지 않는다. 2.0GHz를 실행 중 cpufreq 쓰기만으로 새로 만들어낼 수 없으며, 부팅 펌웨어가 노출한 주파수 범위 안에서만 제한을 바꾼다.
- **실행 중 제어:** `mebs/performance.py`는 Linux [cpufreq policy sysfs](https://docs.kernel.org/admin-guide/pm/cpufreq.html)의 `scaling_max_freq`를 사용한다. 기본·백업 중·탐색기 종료 시 1,500,000kHz 이하로 제한한다. 탐색기/영상 목표는 각각 1,800,000/2,000,000kHz다. CPU가 75°C 이상이면 증속을 해제하고 80°C 이상이면 기본 상한을 강제한다. 70°C 이하에서 30초 회복 후에만 다시 증속을 고려한다. 저전압/스로틀링의 현재 또는 부팅 이후 이력 비트가 한 번이라도 보이면 해당 세션의 증속을 잠근다. 외부에서 cpufreq 상한을 더 낮추면 그 상한을 다시 올리지 않는다.
- **상태 입력:** 실제 CPU 온도는 기존 thermal/hwmon 읽기를 사용한다. 전원 상태는 Raspberry Pi의 `/dev/vcio` 펌웨어 mailbox에 `get_throttled`를 질의한다. 비트 0~3과 16~19를 검사한다. 장치가 없거나 답이 잘못되면 증속을 금지한다. [Raspberry Pi 공식 비트 정의](https://www.raspberrypi.com/documentation/computers/os.html#get_throttled), [Raspberry Pi vcgencmd 구현](https://github.com/raspberrypi/utils/blob/master/vcgencmd/vcgencmd.c).
- **검증 기록:** `/var/lib/mebs/performance-validation.json`의 같은 Pi 시리얼, 최소 30분, 75°C 미만, 저전압/스로틀링 0, `full_system_verified=true`와 해당 클럭 기록이 모두 있어야 증속된다. 기록만으로 안정성이 증명되지는 않으므로 실제 전원·USB 부하·탐색기/영상·백업과 반복 부팅 결과를 확인한 뒤에만 승인해야 한다. `mebs.performance_validate`의 30분 CPU 부하 시험은 **예비 시험**이며 `performance-cpu-test.json`에 `CPU_ONLY_PASS`를 쓴다. 이것만으로 증속은 열리지 않는다.
- **상태 보고:** `/run/mebs/status.json`의 `performance`에는 모드, 실제 적용한 sysfs 상한, 차단 이유, 온도와 펌웨어 마스크가 나타난다. cpufreq가 없으면 `UNAVAILABLE`로 표시한다. 배터리 SIMULATION 값은 이 제어에 사용하지 않는다.

## 현재 시험

| 시험 | 판정 | 증거 |
|---|---|---|
| 호스트의 가상 cpufreq: 기본 → 탐색기 → 영상 → 백업/닫기 | PASS | `python3 -m unittest discover -s tests -p test_performance_v3.py -v`; 전체 **159개 PASS** [로그](performance-host-tests.log) |
| 75/80°C, 냉각 대기, 저전압/스로틀링 현재·이력, 센서 누락, 외부 상한 | PASS (SIMULATION TESTED) | 임시 디렉터리 sysfs 모형, 실제 호스트 CPU 주파수 변경 없음 |
| Buildroot Pi4B 커널 cpufreq·thermal·vcio 구성 | CONFIGURED | [커널 설정](performance-kernel-config.log): `CONFIG_CPU_FREQ=y`, `CONFIG_ARM_RASPBERRYPI_CPUFREQ=y`, `CONFIG_BCM2711_THERMAL=y`, `CONFIG_BCM_VCIO=y`. 하드웨어 동작은 미확인 |
| 기본 이미지 1.5GHz, 1.8/2.0GHz 별도 후보 FAT 설정 | PASS (정적 검사) | 세 이미지의 [부팅 설정과 해시](performance-clock-images.txt). 두 후보의 실제 부팅은 미실시 |
| QEMU `virt`에서 cpufreq/VideoCore 부재 시 증속 금지 | PASS (가상 환경) | [최종 ARM64 게스트 결과](performance-qemu-final/qemu-explorer.json): `mode=UNAVAILABLE`, 기존 자동 백업·탐색기 PASS. Pi4 하드웨어 클럭·전력 제어 시험은 아님 |
| 최종 이미지 백업 중 종료 → 미완료 감지 → 검증 재시도 | PASS (가상 환경) | `python3 tests/v2-integration/run.py --images output/pi4-v3-performance-lock-20261019/images --cases T14`; [최종 로그](performance-final-t14.log), 원본 디스크 이미지 불변 |
| 실물 Pi4B 1.8/2.0GHz 온도·5V 입력·USB 부하·백업·영상·반복 부팅 | HARDWARE NOT TESTED | 보드와 전원/패널/센서가 현재 개발 호스트에 없음 |

**최종 기본 이미지**는 `output/pi4-v3-performance-lock-20261019/MABS_V3_RPi4.img`, 311,427,072바이트, SHA-256 `d847f948b632bc973c0c028ce7d5e5db244f8e5edd8c7969ebc29dc695c35287`이다. [빌드 로그](performance-lock-build.log)와 [파티션·부팅 파일·ARM64 코드 일치 검사](performance-final-validation.json)를 보존했다. 자동 백업·탐색기 [최종 QEMU 결과](performance-qemu-final/qemu-explorer.json), 백업 중 종료·복구 [최종 T14 결과](performance-final-t14.log)는 PASS다. 일반 V3 탐색기 기준 시험은 [TEST_REPORT.md](TEST_REPORT.md)에 있다.

두 시험용 후보도 기본 이미지의 **별도 사본**으로 생성했다. 1.8GHz 후보 `output/pi4-v3-performance-final-1800MHz-UNVALIDATED.img`의 SHA-256은 `6c6da2bb000eaabdaa57878749a827c7651f782a93a86d12b98ceea744290efa`, 2.0GHz 후보 `output/pi4-v3-performance-final-2000MHz-UNVALIDATED.img`는 `81bad37dd9515e3c5d427ec5b5ab64f51c629c8d3ab303305846bfe5ecd42fbb`이다. **두 후보 모두 실물 부팅·안정성 미검증이며 배포용이 아니다.**

## 실물 검증 순서

1. [기존 설치 안내](INSTALL.md)에 따라 1.5GHz 기본 이미지를 **별도 microSD**에 기록하고 Pi4B 보드 리비전, 안정적인 5V 공급, ACT LED/UART, DSI, USB 저장장치의 실제 연결 상태를 확인한다. 주파수 정책·온도·`get_throttled` 응답을 기록한다. 응답이 없으면 고클럭 시험을 중단한다.
2. 호스트에서 기존 기본 이미지의 별도 사본을 만든다: `scripts/pi4-v3-clock-candidate.sh 1800 output/pi4-v3-performance-lock-20261019/MABS_V3_RPi4.img output/pi4-v3-1800MHz-UNVALIDATED-20261019.img`. 2.0GHz는 별도 `2000` 후보로 만든다. **후보 이미지는 미검증**이며 실패 시 기본 이미지 카드로 즉시 되돌린다. EEPROM은 수정하지 않는다. 실제 microSD 기록은 테스트 카드에 한해 사용자가 장치명을 확인한 뒤 수행한다.
3. 후보 이미지로 부팅한 실제 Pi에서 MEBS 서비스를 안전하게 중지한 뒤 `PYTHONPATH=/usr/lib/mebs python3 -m mebs.performance_validate --mhz 1800`을 실행한다(기본 30분). 이 시험은 CPU·온도·실제 주파수·펌웨어 저전압/스로틀링을 기록하고 완료/실패 시 상한을 1.5GHz로 복귀시킨다. **CPU_ONLY_PASS는 아직 사용 승인 아님.**
4. 같은 공급기·케이스·DSI·USB 조합에서 탐색기, 지원되는 실제 H.264 영상 재생, 가상/폐기 가능한 SD의 장시간 SHA-256 백업을 각각 부하 상태로 시험한다. 5V 입력/전류/온도/`get_throttled`와 재부팅 안정성, 실제 복사 해시를 기록한다. 오류·75°C 이상·저전압/스로틀링이 있으면 해당 클럭은 불합격이다. 2.0GHz도 별도로 같은 전 과정을 반복한다.
5. 위 자료를 검토해 합격한 **그 보드의** 클럭만 승인 기록에 반영한다. 전원·냉각·케이스 또는 보드가 바뀌면 다시 시험한다. 실물 자료가 없는 현재는 승인 기록을 만들지 않는다.

`scaling_max_freq`는 제한값일 뿐 실제 순간 클럭이나 안정성을 보증하지 않는다. 현 단계의 미검증 1.8/2.0GHz는 기본 활성화되어 있지 않다.
