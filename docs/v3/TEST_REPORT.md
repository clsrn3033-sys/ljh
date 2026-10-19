# MEBS V3 탐색기 기준 시험 결과 — 2026-10-19

이 문서는 성능 모드 추가 전 V3 탐색기 기준 이미지의 시험 기록이다. 이후 생성한 이미지와 성능 모드의 결과는 [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md)를 따른다.

## 판정

이 기준 시험의 로컬 산출물은 `output/pi4-v3-atomic-20261019/MABS_V3_RPi4.img` (311,427,072바이트, SHA-256 `bc16a0331f7a0fbbe4e3acf2e7200d07ee2fb72ee2e75fd0811c0dd79c2e3103`)이다. Buildroot 2026.08 소스에서 BC250 Bazzite 호스트로 직접 빌드했다. ARM64 QEMU `virt`에서 MEBS 자동 실행, 가상 ext4 대상·vfat 원본의 실제 파일 백업·SHA-256 검증, V3 탐색기 작업이 **PASS**했다. 이는 Raspberry Pi 4B 하드웨어 부팅·DSI 터치 성공을 뜻하지 않는다.

| 항목 | 결과 | 근거 |
|---|---|---|
| Python 회귀·V3 단위 시험 | PASS, 151개 | `python3 -m unittest discover -s tests -q`; [출력](host-tests.log) |
| 실제 이미지 빌드 | PASS | `MEBS_V2_BUILD_OUTPUT=... MEBS_V3_BUILD_OUTPUT=... bash scripts/pi4-v3-image.sh`; [빌드 로그](build-atomic.log) |
| 파티션·부트 파일·ARM64 커널·루트fs·설치 모듈 일치 | PASS | `python3 tests/v3/inspect_image.py --output-dir output/pi4-v3-atomic-20261019`; [검사 JSON](image-validation.json) |
| QEMU ARM64 자동 실행·백업·탐색기 | PASS | `python3 tests/v3/qemu_smoke.py --images output/pi4-v3-atomic-20261019/images`; [결과 JSON](qemu-explorer.json), [시리얼](v3-explorer.serial.log), [게스트 화면](qemu-explorer.png) |
| 정상 종료 중인 백업의 재부팅 복구 | PASS | `python3 tests/v2-integration/run.py --images output/pi4-v3-atomic-20261019/images --cases T14`; [결과](qemu-t14-atomic.log) |
| Pi4B 실제 microSD 부팅·5인치 DSI·터치 | HARDWARE NOT TESTED | 보드/패널 미연결. Pi 전용 GPU 부트 단계는 QEMU `virt`가 시험하지 못함 |
| INA226/231·전원·실제 배터리·실제 FX3 파일 | HARDWARE NOT TESTED | 실제 부품/촬영 파일 미제공. 시뮬레이션 수치를 실측으로 취급하지 않음 |
| 수동 SD 포맷 | BLOCKED | V2/V3에 수동 포맷 기능이 구현되어 있지 않음. 원본 자동 포맷은 금지 |

V3 QEMU 시험은 가상 외장 디스크를 먼저 연결하여 `WAITING_SOURCE`(Storage Ready)를 확인한 뒤, 별도 읽기 전용 vfat 원본을 연결했다. 실제 파일 10개의 백업·SHA-256 검증 후 `SAFE_TO_REMOVE`가 되었다. 게스트에서 JPEG를 32×24로 열고 MP4 코덱을 `ffprobe`로 읽고 FFmpeg로 240×180 썸네일을 만들었다. 원본 JPG 한 파일을 `MEBS_FILES/`로 복사할 때 해시를 비교하고, 사용자 작업 영역의 이동·삭제를 실행했다. 기존 백업의 검증 파일 10개는 계속 유효했고, 원본 디스크 이미지와 OS 이미지의 SHA-256은 시험 전후 동일했다. 화면 PNG는 **가상 데이터로 채운 동일한 UI 렌더**이며 실제 DSI 출력을 캡처한 것이 아니다. [미리보기 PNG](explorer-preview.png)도 SIMULATION이다.

기존 V2 시나리오 T01–T11, T13은 **초기 V3 이미지**로 각각 PASS했다([기록](qemu-regression.log)). 이 12개 결과를 최종 이미지 전체 회귀 성공으로 바꿔 적지 않는다. 초기 T14는 `/run/mebs/status.json`을 갱신하는 순간 JSON이 비어 보이는 경합으로 BLOCKED였다. V3에서 임시 파일 작성 후 원자적 `os.replace`로 상태를 게시했고, 동시 읽기 단위 시험과 **최종 이미지의 동일한 T14**를 재실행했다. 최종 T14에서 미완료 작업 감지 → 원본 재연결 → 11개 파일 검증 → `SAFE_TO_REMOVE`까지 PASS했다. 시험은 실제 호스트 디스크 포맷 없이 폐기 가능한 가상 이미지에만 접근했다. T12 포맷 시험은 실행하지 않았다.

## 실패 → 수정 → 재시험

1. 첫 ARM64 게스트에서 JPG 미리보기가 실패했다. 원인: V2에서 복사한 Pillow가 JPEG 지원 없이 빌드되어 있었다. `BR2_PACKAGE_JPEG=y`와 Pillow 재빌드를 적용했다. 동일 JPEG를 최종 QEMU 게스트에서 열어 PASS했다. [최초 실패 로그](qemu-explorer-first-failure.log).
2. T14에서 상태 JSON 읽기가 간헐적으로 실패했다. 원인: 런타임이 같은 파일을 직접 잘라 쓰고 있었다. V3에서 원자적 교체로 변경하고 40KB 상태를 반복 갱신하며 동시 읽기 59회 시험, 최종 ARM64 게스트의 종료·복구 T14 모두 PASS했다.
3. QEMU 화면 추출 때 긴 Base64 한 줄과 이전 셸 프롬프트 때문에 테스트 수집기가 결과를 놓쳤다. 게스트 PNG를 512자 줄로 출력하고 명시적 종료 표식을 기다리도록 시험 도구를 수정했다. 최종 QEMU 시험에서 [800×480 게스트 렌더 PNG](qemu-explorer.png)를 생성했다.

## V2와 V3 비교

같은 QEMU `virt` Cortex-A72 2 vCPU/1GiB 구성에서 각 이미지의 **커널 실행부터 자동 MEBS READY·테스트 로그인까지** 3회 측정했다. [원자료](boot-comparison.json)와 [시리얼 로그](v3/boot-1.serial.log)를 보존했다.

| 측정 | V2 | V3 |
|---|---:|---:|
| 평균 준비 시간, 3회 | 8.456초 | 8.153초 |
| MEBS 프로세스 유휴 RSS 평균 | 17,227 KiB | 18,731 KiB |
| 디스크 이미지 크기 | 311,427,072바이트 | 311,427,072바이트 |
| ext4 루트fs 사용 블록(1 KiB) | 73,888 | 94,989 |

세 번의 QEMU 결과로 실물 Pi4 부팅 속도 개선을 주장하지 않는다. **5초 목표는 QEMU에서 달성하지 못했다.** V3 고정 이미지 크기가 같아도 FFmpeg·JPEG 때문에 루트fs 실제 사용량은 약 20.6MiB 증가했다. 탐색기/디코더는 기본 화면에서 열지 않을 때 실행하지 않는다.

## 남은 확인

Pi4B 실물의 ACT/PWR LED, UART, micro-HDMI, DSI 모델/오버레이·터치 입력, 실 USB 연결 순서·자동 마운트, 실제 SD 읽기 오류·분리, 배터리/INA 부품, Sony FX3 XAVC S/HS/S-I 및 RAW 재생성, 장시간 백업·전력/발열을 시험해야 한다. DSI 패널 정보가 없어 이미지에 특정 패널 오버레이를 강제하지 않았다. 현 이미지는 소프트웨어 시험용 로컬 산출물이며 **현장 배포 적합 판정은 보류**한다. 실물 시험 절차는 [설치 안내](INSTALL.md)를 따른다.

V3 브랜치에서만 사용자 요청대로 `ver 1/` 폴더를 제거했다. V1 보존 브랜치, V2 브랜치와 기존 V2 이미지는 그대로 있다. GitHub에는 V3를 게시하지 않았다.
