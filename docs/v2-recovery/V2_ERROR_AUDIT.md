# MEBS V2 오류·미검증 전수 조사 — 2026-10-19

기준: `feature/mebs-v2-pi4b-800x480-20261018`의 `f48d89d`, 로컬 IMG 및
[직전 ARM64 재시험](../../tests/v2-integration/ARM64_RETEST_20261019.md).
V1 폴더와 원본 이미지는 변경하지 않았다. 이번 지시서의 표식 파일 요구는 사용자가
다시 확인한 **첫 USB 대상·두 번째 USB 원본, 표식 없음** 정책으로 정리했다.
아래 표는 **수정 착수 시점**의 조사 결과다. 수정 후 판정은 별도 시험 보고서를 따른다.

| 조사 대상 | 확인한 사실 | 분류 |
|---|---|---|
| 빨간 PWR LED·화면 없음 | 사용자가 과거 실기기에서 관찰. 이 세션에는 Pi 전압/ACT/시리얼 로그 없음 | HARDWARE NOT TESTED; 원인 미확정 |
| balenaEtcher 기록 오류 | 과거 경험. 원본 및 새 IMG는 MBR·부트 FAT32·ext4 검사 통과; Etcher 실행·실제 카드 기록은 미실시 | NOT REPRODUCED |
| `parallel0 console` 정지 | 과거 QEMU 현상. 현재 `virt`는 `ttyAMA0`로 실제 Buildroot init 부팅; 직접 `raspi4b`는 로그 없이 timeout | virt 문제 NOT REPRODUCED, Pi 모델 BLOCKED |
| 데모와 OS 이미지 혼동 | `ver 1` 프리뷰 및 과거 zip은 데모/참조. 현재 `sdcard.img`에는 Pi 펌웨어, ARM64 Image, ext4 root, S50mebs 존재 | 구분 완료 |
| USB 순서·자동 복사 | 실제 QEMU FAT32/ext4 hotplug에서 동작. 두 장치 동시 삽입은 AMBIGUOUS 차단 | 가상 PASS, 실물 HARDWARE NOT TESTED |
| SD 삽입 이벤트 | QMP 장치 추가·제거 인식. Pi USB 카드리더·실제 SD 커넥터 미검증 | 가상 PASS, 실물 HARDWARE NOT TESTED |
| SHA-256 | 실제 바이트 변조는 verifier가 감지. 정상 복사 후 경로·해시 일치. 완료 후 자동 변조 감시는 없음 | 가상 PASS / 기능 제한 |
| 중복 복사 | 같은 카드 재연결 시 두 번째 작업 생성·재복사 | 수정 대상 |
| 강제 종료 복구 | `.mebs-pending-*` 잔존하지만 재부팅 화면은 WAITING_SOURCE | 수정 대상 |
| 빈 카드 | 0개 파일을 SAFE_TO_REMOVE 처리 | 수정 대상 |
| GUI 값 | 기존 화면은 guest 상태로 렌더 가능하지만 CPU/배터리 센서는 미연결; RAM 상태 없음 | 수정 대상 / 하드웨어 미검증 |
| DSI 터치 | 패널 모델·컨트롤러·케이블·백라이트 미확정. framebuffer fallback만 구성 | HARDWARE NOT TESTED |
| INA226·DS3231 | 코드와 가짜 버스 단위 시험 존재. hardware.json에서 비활성화 | HARDWARE NOT TESTED |
| 5V 3A·전원 강하 | 실제 컨버터·BMS·부하 전압 계측자료 없음 | HARDWARE NOT TESTED |
| 자동 종료 | OS 안전 종료 대기 코드와 호스트 시험 존재. GPIO 물리 전원 차단 없음 | 호스트만 검증 / HARDWARE NOT TESTED |
| 5초 부팅 | 이전 QEMU start→READY 약 7~9초. Pi 전원 인가→화면 READY 실측 없음 | HARDWARE NOT TESTED |
| 포맷 | 실제 formatter 및 물리 버튼/터치 최종 승인이 아직 없음 | BLOCKED, 자동 포맷 없음 |

근거: [이전 12개 결과 JSON](../../tests/v2-integration/runs/20261019-065227/results.json),
[Buildroot 이미지 검사](../../tests/v2-integration/logs/recovery-pi-image-inspection.log),
[QEMU direct Pi 이전 로그](../../tests/v2-integration/logs/raspi4b-20261019-070016.log).
이번 수정 후의 채택 판정은 [V2_TEST_REPORT.md](V2_TEST_REPORT.md)에 기록한다.
