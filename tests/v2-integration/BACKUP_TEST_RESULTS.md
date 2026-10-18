# MEBS V2 백업 시험 결과 — 2026-10-19 KST

실제 QEMU ARM64 virt + Buildroot + 자동 시작 runtime800에서 시험했다.
각 행은 독립 가상 디스크/VM이며, 이전 실패/테스트 도구 오류 로그도 보존한다.
최종 채택 결과는 `SELECTED_RESULTS.json`에 원본 run을 명시한다.

**PASS 8 / FAIL 3 / BLOCKED 1 (총 12).** 전체 통과율 66.7%, 실행한 11개 중 72.7%.
기능 전체 완성률 또는 물리 하드웨어 안정성 확률이 아니다.

| 시험 | 실제 실행 | 판정 | 기대 | 관찰 | 증거 |
|---|---|---|---|---|---|
| T01 정상 백업 | 실행 | **PASS** | 파일·폴더 보존, 해시 일치, 정상 분리 | 10개 실제 JPG/MP4/XML/기타 파일 3,307 bytes, 모든 해시·경로·빈 폴더 일치. 기존 대상 파일 보존. | [로그](runs/20261019-064559/logs/T01.serial.log) |
| T02 동일 파일 재백업 | 실행 | **FAIL** | 이미 백업한 동일 파일 건너뛰기 | 두 개의 별도 완료 작업 생성, 3,307 bytes 재복사. 덮어쓰지는 않음. | [로그](runs/20261019-064052/logs/T02.serial.log) |
| T03 실제 파일시스템 용량 부족 | 실행 | **PASS** | 복사 전 차단 | 필요 34,634,752 / 잔여 13,188,096 bytes, 복사 0, ERROR. | [로그](runs/20261019-063738/logs/T03.serial.log) |
| T04 백업 중 가상 외장하드 제거 | 실행 | **PASS** | 오류, 성공/안전 분리 표시 금지 | COPYING 도중 QMP device_del, ERROR, safe_to_remove=false. | [로그](runs/20261019-064052/logs/T04.serial.log) |
| T05 백업 중 가상 SD 제거 | 실행 | **PASS** | 오류, 원본 보호 | COPYING 도중 QMP device_del, ERROR, safe_to_remove=false. | [로그](runs/20261019-064052/logs/T05.serial.log) |
| T06 VM 강제 종료 후 재부팅 | 실행 | **FAIL** | 재부팅 후 미완료 작업 표시 | 실제 QEMU SIGKILL·재부팅. pending 폴더 보존하나 화면은 WAITING_SOURCE; 중단 안내 없음. | [로그](runs/20261019-064052/logs/T06.serial.log) |
| T07 복사본 바이트 변조 | 실행 | **PASS** | 해시 불일치 검출 | 완료된 XML의 실제 1 byte 변경 후 production verify 호출이 해시 불일치 검출. 자동 사후 감시는 아님. | [로그](runs/20261019-063738/logs/T07.serial.log) |
| T08 읽기 전용 대상 | 실행 | **PASS** | 복사 전 차단 | QMP read-only 대상 연결 후 오류, 복사 0. | [로그](runs/20261019-063738/logs/T08.serial.log) |
| T09 지원하지 않는 FAT32 대상 | 실행 | **PASS** | 미지원 대상 거부; 표식 파일은 불필요 | ext4 필요 오류, 복사 0. 기존 표식 없는 장치 거부 기준은 사용자 확인에 따라 폐기. | [로그](runs/20261019-064923/logs/T09.serial.log) |
| T10 빈 SD카드 | 실행 | **FAIL** | 백업할 파일 없음 표시 | 0개 파일을 SAFE_TO_REMOVE로 완료 처리. 전용 메시지 없음. | [로그](runs/20261019-063738/logs/T10.serial.log) |
| T11 한글·중국어·특수문자 이름 | 실행 | **PASS** | 파일명과 바이트 그대로 보존 | 가.txt/나.txt 포함 서로 다른 한글 이름, 중국어·공백·특수문자 경로 모두 보존. | [로그](runs/20261019-063738/logs/T11.serial.log) |
| T12 승인 후 SD 포맷 | 미실행 | **BLOCKED** | 가상 SD에 사용자 승인 후에만 포맷 | 수동 포맷 구현/승인 UI가 없어 미실행. 실제 디스크 및 가상 원본 포맷 안 함. | [로그](runs/20261019-064435/results.json) |

## 명령 및 환경

전체: `python3 tests/v2-integration/run.py --images output/pi4-v2-validated-20261019/images`
개별: 같은 명령에 `--cases T01` 등 추가. 구체적 QEMU 명령은 각 serial 로그 첫 줄.
호스트 Bazzite 43 / BC250 / QEMU 10.1.5, guest Cortex-A72 2 vCPU / RAM 1GiB,
Buildroot 2026.08 ARM64. test fstab만 mmcblk0p3에서 vda3로 바꾼 복사본 사용.
실제 목적/원본 ext4 192MiB / FAT32 64MiB, T03 대상 16MiB,
장애 주입용 추가 32MiB 데이터. 이전 2GiB/512MiB 대형 fixture 시험은 미실행.

T01/T09는 최종 seedrng+UTF8 후보 이미지에서 재실행했다.
나머지는 동일 backup Python 코드와 커널인 UTF8 후보에서 실행했고,
최종 후보에서 전 항목을 다시 실행했다고 주장하지 않는다.
각 run의 environment.json에 이미지 전체 SHA-256 및 원본 보존 결과가 있다.

## 판정 변경 이력

- `063517`: 원본 이미지 T01 Unicode 경로 불일치. 초기에 도구가 AssertionError를
  BLOCKED로 기록했으나 이는 제품 결함으로 FAIL이다. 원본 기록 보존.
- `063738`: T02 재연결 중 일시 ERROR를 도구가 일찍 중단; 재시험 결과 FAIL(중복 복사).
- `063738`: T04~T06 QMP throttle read-only 계층 설정 누락으로 BLOCKED;
  테스트 도구 수정 후 `064052`에서 실제 장애를 주입했다.
- `063738`: T09는 옛 표식 요구 기준으로 FAIL을 기록했으나 표식 없는 대상에서
  실제 백업은 성공했다. 사용자 확인에 따라 그 판정은 제외하고 미지원 FS 거부로 재시험했다.
- T07의 완료 후 상태 JSON은 SAFE_TO_REMOVE 상태로 남아 있다. 명시적 verify 호출만
  시험했으며 완료 후 재마운트/변조에 대한 자동 재검증·UI 경고까지 PASS인 것은 아니다.

모든 완료 시험에서 원본 이미지 전체 해시가 동일했고 원본은 QEMU에서도 read-only였다.
T06은 데이터 보존과 사용자에게 복구 상태를 알리는 요구를 구별해 FAIL로 판정했다.

최종 후보의 표식 없는 정상 백업도 별도로 PASS: `runs/20261019-064559`. 원본 FAT32 SHA-256 유지, 10개 파일 해시·경로·기존 데이터 보존 확인. 현재 T01 채택 결과는 이 실행이다.

최종 도구 수정(초기 상태 파일 대기 및 기본 후보 경로) 후 T09도 `064923`에서 재실행 PASS.
