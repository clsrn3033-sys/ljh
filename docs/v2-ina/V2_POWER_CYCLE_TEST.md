# MEBS V2 전원 켜기·백업·종료 시험 — 2026-10-19

## 범위와 판정

Raspberry Pi 4B용 **새 이미지 복사본**을 만들고, 호스트 미리보기와 QEMU ARM64 `virt`를 나누어 시험했다. 실제 Pi 4B, DSI 터치, GPIO 전원 버튼, 물리 USB/SD 또는 전원 회로는 연결하지 않았다. QEMU 성공은 Pi 4B 하드웨어 부팅 성공을 뜻하지 않는다.

| 항목 | 판정 | 실제로 확인한 내용 |
|---|---|---|
| 호스트 전원 켜기 화면 | PASS · SIMULATION | 기존 로고/문구를 사용한 0→100% 부팅 화면과 `BACKUP READY` 프레임 |
| 호스트 버튼→복사→예약 종료 | PASS · 실제 임시 파일 복사 | JPG·MP4·XML 3개를 복사하고 SHA-256 일치; 복사 중 종료 버튼은 예약만 함 |
| 검증 실패·동기화 실패 | PASS · 호스트 오류 주입 | 미검증 작업은 예약 종료 취소; 동기화 오류면 전원 종료 호출 금지 |
| 화면 고장 | PASS · 호스트 오류 주입 | 페이드아웃 출력 오류가 있어도 이미 동기화한 OS 종료 호출은 진행 |
| 호스트 MEBS 로고 페이드아웃 | PASS · SIMULATION | 안전 분리·두 번의 동기화 이후 9프레임으로 검은 화면까지 전환 |
| QEMU T01 자동 부팅·USB 백업 | PASS · ARM64 `virt` | 10개 파일/폴더 및 기존 대상 파일 보존, SHA-256, `SAFE_TO_REMOVE`; READY까지 약 7.40초 |
| QEMU T13 정상 OS 종료·재부팅 | PASS · ARM64 `virt` | 같은 가상 OS에서 10개 파일 검증 후 `Power down`, 재부팅 후 USB 없이 `READY`; 첫 부팅 약 7.35초, 재부팅 약 7.52초 |
| Pi 4B 실물 화면·터치·전원 버튼 | HARDWARE NOT TESTED | 장비/패널/전원 회로 미연결. QEMU에는 터치 장치가 없어 버튼→페이드는 호스트 테스트로만 검증 |
| 5초 이내 실물 부팅 | HARDWARE NOT TESTED | QEMU 관측값도 목표 5초를 넘음. 실물 성능 추정에 사용하지 않음 |
| 수동 SD 포맷 T12 | BLOCKED | V2 수동 포맷 승인 UI/기능 미구현. 실제 매체 포맷 없음 |

## 발견한 문제와 수정

1. 종료 버튼 이후 화면이 곧바로 꺼질 수 있었고 로고 페이드아웃도 없었다. 종료 예약 중 화면 타임아웃을 막고, 백업 완료·정상 마운트 해제·메타데이터 동기화 이후에만 기존 MEBS 로고를 페이드아웃하도록 했다. 헤드리스 백업 동작은 그대로다.
2. 화면 출력 실패가 종료를 막을 가능성을 없앴다. 출력 오류는 기록하고 OS 종료 명령을 계속 호출한다. 반대로 동기화 실패나 백업 실패는 OS 종료를 막는다.
3. QEMU 테스트 도구가 선택하지 않은 포맷 T12를 항상 결과에 추가해 T01/T13 자체가 PASS여도 프로세스 종료 코드를 1로 만들었다. 선택한 ID만 실행/판정하도록 수정했다. 수정 전 T13 결과는 PASS/종료 코드 1, 수정 후 T13 결과는 PASS/종료 코드 0이다. 기본 전체 실행에서는 미구현 T12를 계속 BLOCKED로 기록한다.
4. 이미지 정적 검사에서 일반 `mdir`의 8.3 열 표시를 긴 파일명 목록으로 잘못 해석한 첫 검사 스크립트가 부팅 파일 4개를 누락으로 보고했다. `mdir -b`로 다시 검사해 `start4.elf`, `fixup4.dat`, `config.txt`, `cmdline.txt`, `Image`, Pi 4B DTB 모두 확인했다. 이미지 결함은 아니었다.
5. 첫 QEMU 실행은 샌드박스가 QMP Unix 소켓 생성을 막아 부팅 전 BLOCKED였다. 허용된 로컬 실행 환경에서 같은 가상 이미지로 다시 시험해 T01/T13 PASS를 확인했다.

## 이미지와 증거

- Pi 4B 원시 이미지: `output/pi4-v2-power-cycle-v5-20261019/images/sdcard.img` (311,427,072 bytes), SHA-256 `f7dbd01092af7f82ad02030b25d3910530db11a00f0b3e226fb9ccf4687732a6`.
- 압축본: 같은 디렉터리의 `sdcard.img.zst`, SHA-256 `d709011c4a60edd438492b3099811bf08a572d5e155683bc63aa00b40a6d6cd9`. `zstd -t` 및 압축 해제 스트림의 원본 SHA 일치를 확인했다.
- 이미지에는 FAT32 부팅, ext4 루트, ext4 설정 파티션 총 3개가 있다. `runtime800.py`, `controls.py`, `boot_animation.py`가 현재 소스와 바이트 단위로 일치했다. `rootfs.ext2`의 `e2fsck -fn` 통과.
- 기존에 로컬 빌드한 Buildroot 커널/펌웨어를 재사용하고 변경된 Python 소스를 새 이미지에 주입했다. **이번 변경에서 커널 전체를 다시 빌드하지 않았다.** 이전 이미지와 `ver 1/`은 보존했다.
- QEMU 전용 이미지: `output/pi4-v2-power-cycle-v5-qemu-20261019/images/qemu-virt.img`. 이는 설정 파티션의 장치명만 QEMU용으로 바꾼 별도 복사본이다.
- 동작 미리보기: [전원 켜기→실제 임시 파일 백업→종료→재시작 GIF](power-cycle-preview/power-cycle.gif), [종료 페이드 첫 화면](power-cycle-preview/screenshots/10-SHUTDOWN_FADE.png), [페이드 완료 검은 화면](power-cycle-preview/screenshots/11-POWER_OFF.png). GIF의 부팅/버튼/재시작 화면은 호스트 시뮬레이션이고 파일 복사·해시는 실제로 수행했다.
- 실행 증거: [호스트 139개 테스트](power-cycle-preview/host-tests.log), [실제 임시 파일 해시 및 단계](power-cycle-preview/result.json), [QEMU T01](power-cycle-preview/qemu-T01-result.log), [QEMU T13](power-cycle-preview/qemu-T13-result.log), [T13 종료 시리얼 로그](power-cycle-preview/qemu-T13-shutdown.serial.log), [이미지 정적 검사](power-cycle-preview/image-validation.json).

## 재실행 명령

```sh
python3 -m unittest discover -s tests -q
python3 tests/v2-integration/power_cycle_preview.py docs/v2-ina/power-cycle-preview
python3 tests/v2-integration/run.py \
  --images output/pi4-v2-power-cycle-v5-20261019/images \
  --prepared-os output/pi4-v2-power-cycle-v5-qemu-20261019/images/qemu-virt.img \
  --cases T01,T13
zstd -t output/pi4-v2-power-cycle-v5-20261019/images/sdcard.img.zst
```

QEMU 명령은 호스트에서 로컬 QMP Unix 소켓 생성이 허용돼야 한다. 모든 가상 저장장치는 임시 파일이며 실제 호스트 디스크를 마운트하거나 포맷하지 않는다. Raspberry Pi 4B 실물에는 이미지 기록/기동·HDMI 또는 DSI 화면·터치·USB 식별 순서·물리 전원/저전압을 별도로 검증해야 한다. 이 검증 전에는 실기기 배포 가능으로 판정하지 않는다.
