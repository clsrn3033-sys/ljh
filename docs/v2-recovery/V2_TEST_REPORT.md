# MEBS V2 수정 후 전체 재시험

2026-10-19 KST. Raspberry Pi 4B용 새 IMG와 **별도 QEMU ARM64 virt 테스트 IMG**를 사용했다.
QEMU에는 실제 FAT32 원본·ext4 대상 파일 이미지를 연결했고, Buildroot init에서 MEBS가
자동 실행됐다. 테스트 디스크는 regular file이며 호스트 물리 디스크는 포맷하지 않았다.

## 실행 환경과 명령

BC250 Bazzite Linux, QEMU 10.1.5, guest Cortex-A72 2 vCPU/1GiB RAM.
이미지는 기존 LJH에서 BC250으로 빌드한 Buildroot 2026.08 ARM64 커널·rootfs에
이번 Python 수정만 새 복사본으로 반영했다. QEMU용은 별도 복사본에서 설정 파티션
경로만 `mmcblk0p3`→`vda3`로 조정했다.

```sh
python3 -m unittest discover -s tests -q
python3 tests/v2-integration/run.py \
  --images output/pi4-v2-recovery-v4-20261019/images \
  --prepared-os output/pi4-v2-recovery-qemu-v4-20261019/images/qemu-virt.img
```

호스트 테스트 **124개 PASS**. 이전 118개 결과를 현재 코드 결과로 대신 세지 않았다.
v3 반복 시험에서 강제 종료 후 경고 누락이 발견되어 v4 이미지로 수정했다.
v4 전체 QEMU 통합 시험 결과는 **자동화 T01~T11 11개 PASS, T12 수동 포맷 1개 BLOCKED**다.
별도 T06/T10 재시험에서도 실제 SIGKILL→재부팅 경고→재백업 및 빈 카드 거부가 통과했다.
스크립트 종료 코드 1은 `BLOCKED` 항목이 남아 있어서 발생한다.
원본 실패·도구 오류 로그는 보존했다.

근거: [호스트 결과](../../tests/v2-integration/logs/recovery-v4-host-tests.log),
[v3 경고 누락](../../tests/v2-integration/runs/20261019-072240/results.json),
[v4 복구 재시험](../../tests/v2-integration/runs/20261019-072405/results.json),
[v4 전체 QEMU 결과](../../tests/v2-integration/runs/20261019-072715/results.json),
[v4 이미지 검사](../../tests/v2-integration/logs/recovery-v4-pi-inspection.log).
게스트 상태를 입력으로 한 800×480 UI 캡처:
[완료·안전 분리](../../tests/v2-integration/runs/20261019-072715/screenshots/T01-guest-safe-to-remove.png),
[강제 종료 후 복구 경고](../../tests/v2-integration/runs/20261019-072715/screenshots/T06-guest-recovery-required.png),
[빈 카드 오류](../../tests/v2-integration/runs/20261019-072715/screenshots/T10-guest-empty-source.png).
이는 guest의 offscreen 렌더링이며 DSI 패널 출력 증거는 아니다.

Pi raw IMG: `output/pi4-v2-recovery-v4-20261019/images/sdcard.img`
(`90cf0debeb8e2405224de9ad99c0ba80a23932bbf917d70f22c7936f6db68f27`).
QEMU raw IMG: `output/pi4-v2-recovery-qemu-v4-20261019/images/qemu-virt.img`
(`fa7837e99a9b7d40fd646aa8701672d7d572f5c568363c68ceeed7028b90ab23`).
Pi IMG 압축본: `artifacts/MEBS-V2-recovery-v4-Pi4B-20261019.img.zst`;
[체크섬](../../artifacts/MEBS-V2-recovery-v4-Pi4B-20261019.sha256).
새 Pi 이미지의 부트 파일·파티션·ARM64 magic [검사](../../tests/v2-integration/logs/recovery-v4-pi-inspection.log),
3개 파일시스템 [읽기 전용 검사](../../tests/v2-integration/logs/recovery-v4-filesystems.log)도 통과했다.

## 지시서 T01~T24 판정

`PASS`는 표에 적힌 환경에서 실제 확인한 범위에만 적용한다. 물리 장치 항목은
`HARDWARE NOT TESTED`라고 별도로 표시한다.
아래 표의 ID는 이번 **24개 요구사항 번호**다. 자동화 로그의 `T01~T12`는 별도
시나리오 번호로, 순서대로 정상 백업·중복·용량 부족·대상 분리·원본 분리·SIGKILL·
데이터 변조·읽기 전용 대상·잘못된 파일시스템·빈 SD·유니코드 이름·포맷 미구현이다.

| ID | 결과 | 실제 확인한 범위 / 남은 제한 |
|---|---|---|
| T01 정상 부팅 | PASS (QEMU) | Buildroot PID1 init→S50mebs→READY. Pi 펌웨어 부팅은 HARDWARE NOT TESTED |
| T02 저장장치 없이 | PASS (QEMU) | 디스크 없이 READY, 무한 대기 없음 |
| T03 외장 스토리지 | PASS (QEMU) | 첫 USB 후 WAITING_SOURCE 및 STORAGE READY 표시. 표식 없음 |
| T04 SD 연결 | PASS (QEMU) | 두 번째 USB 원본 역할·SD READY 상태 |
| T05 정상 백업 | PASS (QEMU) | 실제 JPG/MP4/XML 등 10개 경로·SHA-256, 빈 폴더, 기존 대상 데이터 보존 |
| T06 동일 파일 재백업 | PASS (QEMU) | 검증된 동일 job 1개만 유지, 재복사 0바이트. 일부 파일만 변경된 카드의 파일별 재사용은 아직 미구현 |
| T07 공간 부족 | PASS (QEMU) | 필요/잔여 경고, 복사 전 차단, 자동 포맷 없음 |
| T08 SD 분리 | PASS (QEMU) | 실제 QMP 분리, ERROR, 안전 분리 표시 없음 |
| T09 외장 하드 분리 | PASS (QEMU) | 실제 QMP 분리, ERROR, 원본 보존 |
| T10 전원 차단 | PASS (QEMU) | QEMU PID SIGKILL→재부팅→미완료 경고→SD 재연결→새 작업 해시 검증. 실제 전원 차단은 HARDWARE NOT TESTED |
| T11 SHA-256 불일치 | PASS (명시적 검증) | 복사본 한 바이트 변조 후 production verifier가 검출. 완료 후 자동 상시 감시는 미구현 |
| T12 잘못된 저장장치 | PASS (QEMU) | 읽기 전용/FAT32 대상은 첫 USB 시점부터 거부 |
| T13 파일명 충돌 | PASS (QEMU 범위) | 다른 폴더의 동일 이름 및 대상 기존 파일 보존. 모든 파일시스템 조합은 미검증 |
| T14 완료 후 포맷 요청 | BLOCKED | 수동 formatter·승인 UI·대상 FS별 도구 없음. 포맷 미실행 |
| T15 실패 후 포맷 요청 | BLOCKED | 포맷 경로 자체 없음. 실패 후 버튼 입력·재확인 동작은 미검증 |
| T16 CPU 온도 표시 | NOT TESTED | QEMU에 Pi 열 센서 없음; 미연결 시 N/A. 실제 센서는 HARDWARE NOT TESTED |
| T17 배터리 미연결 표시 | PASS (guest UI) | 비활성 INA226의 임의 값 없이 N/A 렌더. 실제 INA226은 HARDWARE NOT TESTED |
| T18 터치 조작 | NOT TESTED | evdev 로직 호스트 시험만; DSI 패널/터치는 HARDWARE NOT TESTED |
| T19 안전 제거 | PASS (QEMU) | 검증→syncfs→정상 unmount 후 SAFE_TO_REMOVE. 실제 USB 물리 제거는 HARDWARE NOT TESTED |
| T20 안전 종료 | NOT TESTED (실기기) | 호스트 단위로 종료 예약 로직 시험. 실제 UI→OS 전원 종료 전체 경로는 HARDWARE NOT TESTED |
| T21 20회 부팅 | PASS (QEMU) | v4 동일 COW 디스크 재부팅 20/20 READY, 중앙값 7.416초. 실제 Pi cold boot는 HARDWARE NOT TESTED |
| T22 장시간 백업 | NOT TESTED | 수십 MB 장애 시험만 수행. 누수·과열은 HARDWARE NOT TESTED |
| T23 RTC 전원 차단 | NOT TESTED | DS3231 비활성·실물 없음; HARDWARE NOT TESTED |
| T24 저전압 | NOT TESTED | 실제 전압/INA226 미연결·보호 임계값 미확정; HARDWARE NOT TESTED |

## 남은 실패·제약

- 소프트웨어 핵심 T01~T11은 가상 디스크에서 통과했다. **실기기 정상 동작을 뜻하지 않는다.**
- T14/T15 포맷은 미완성. 현 Pi rootfs에는 원래 형식을 유지할 `mkfs.vfat`,
  `mkfs.ext4`, `mkfs.exfat` 도구가 없다. 안전 승인·재식별·사용자 입력 경계를
  설계하고 폐기용 가상 SD로 먼저 검증해야 한다. 외장하드와 시스템 디스크는 대상이 아니다.
- 일부 변경된 카드의 파일별 중복 재사용, 사진/영상/XML별 별도 분류, RTC가 없는
  상태의 1970 날짜 폴더, 완료 후 자동 재검증은 미구현이다. 원본 폴더 구조 보존은 유지.
- 현재 이미지의 로고 자산은 기존 흰색 `MEBS` 문자 마스크다. 과거 언급된 사자 로고
  파일은 이 저장소에서 확인되지 않아 임의로 새 로고로 교체하지 않았다.
- Pi4B 빨간 LED, 5V 부하 전압, EEPROM, ACT LED, UART, DSI/터치/백라이트,
  INA226, DS3231, 실제 USB 전원 안정성은 모두 **HARDWARE NOT TESTED**.
- QEMU `virt`의 부팅은 Pi4B 펌웨어 부팅 성공 증거가 아니다.
  동일 최종 이미지의 `raspi4b` 모델 30초 시험은 커널 로그 없이 timeout되어
  [BLOCKED](../../tests/v2-integration/logs/recovery-v4-direct-raspi4b-probe.log)로 기록했다.

**실기기 배포 판정: 아직 보류.** Pi4B cold boot·micro-HDMI/DSI 출력·USB 전원 안정성·
폐기 가능한 실물 매체 시험이 없고, 수동 포맷 경로도 미완성이다. 이미지는
보존 가능한 실기기 부팅 진단용 후보로만 취급한다.

다음 조치: 실물 Pi의 전원·ACT LED·UART 기록과 DSI 패널/전원부 모델 확보,
포맷 안전 설계와 실제 카드 시험, 날짜 기준 확인, 부분 변경 백업 정책 확정.
