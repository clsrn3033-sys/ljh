# 발견 문제 및 처리

## 수정하고 재검증함

- **FAT32 Unicode 이름 손실**: 원본 Pi 커널의 기본 FAT iocharset은 ASCII.
  NLS_UTF8은 있지만 mount 옵션이 없어 한글 이름이 `?`로 보였다.
  `mebs/appliance.py`에서 `utf8=1`을 지정했다. T01/T11 실제 FAT32→ext4
  재시험에서 전체 경로 및 SHA-256 일치. `가.txt`/`나.txt` 충돌 위험도 검사했다.
  원본 파일 바이트 해시만 비교해서는 찾지 못하는 결함이었다.
- **seedrng read-only root 오류**: 원본은 /var/lib/seedrng 생성 실패.
  `/etc/default/seedrng`로 /var/lib/mebs/seedrng를 사용하고 최종 init 시험에서
  `Saving 256 bits of creditable seed for next boot`를 확인했다.
  이미지에 seed를 미리 넣지 않았으며 물리 엔트로피 품질은 별도 검증 대상이다.

## 미해결 제품 요구

| 항목 | 관찰 / 영향 | 후속 작업 |
|---|---|---|
| T02 중복 건너뛰기 | 동일 원본을 새 job으로 전부 복사. 기존 백업 덮어쓰기는 없음 | 원본/기존 manifest 해시 기반 재사용 정책과 변경 파일 회귀 시험 |
| T06 중단 복구 안내 | SIGKILL 뒤 pending 파일은 남지만 앱은 WAITING_SOURCE | pending 검사와 명시적 복구/새 작업 선택; 부분 데이터를 성공 처리하지 않기 |
| T10 빈 카드 | 파일 0개도 안전 분리 완료로 표시 | 원본 스캔 후 명확한 no-files 메시지 |
| T12 승인 후 포맷 | formatter/승인 UI 자체 없음 | 별도 안전 설계·장치 재식별·검증 재확인 후 가상 SD에서만 구현/시험 |
| RTC/날짜 | QEMU 시간이 1970, 날짜 폴더도 1970 | DS3231 실물 구성 또는 신뢰할 시간 설정; 미설정 안내 |
| 파일 종류별 분류 | 현재 원본 트리 그대로 보존, 유형별 분류 없음 | 보존 구조와 충돌하지 않는 분류 요구를 별도 설계 |
| RAM UI | 메모리 사용률 표시 없음 | 읽기 전용 /proc 수집과 표시 검증 |
| 연결 해제 메시지 | 대상 제거 때 일반 /dev/sda OSError 표시 | Storage/SD 구분 오류 문구 개선 |
| 사후 변조 | 명시적 verify는 검출하지만 완료 후 자동 상태 무효화는 없음 | 포맷 구현 전 반드시 실제 복사본 재검증 경계 설계 |
| 실제 GUI/DSI | virt는 headless worker + offscreen render만 검증 | 실제 패널·터치/백라이트·부팅 애니메이션 확인 |

이 항목을 해결했다고 보고하지 않는다. 현재 변경은 두 개의 좁은 OS/마운트 수정이며,
백업 엔진·V1을 대규모로 변경하거나 포맷 기능을 임의로 활성화하지 않았다.

## 시험 도구와 환경 문제

- 첫 console prompt 패턴이 BusyBox 로그인 쉘과 맞지 않아 BLOCKED. 패턴 수정 후 정상 자동 init 시험.
- QMP throttle 계층의 read-only 속성 누락으로 device_add가 거부됨. 계층을 일치시킨 뒤
  T04/T05 실제 hot-unplug, T06 실제 QEMU SIGKILL을 재실행함.
- 디스크 제거 직후 transient ERROR로 재연결 시험이 중단됨. READY까지 기다리도록 수정.
  재시험 T02에서 제품의 실제 중복 복사를 관찰함.
- 시작 직후 status.json 생성 전 조회 traceback은 앱 crash가 아닌 테스트 폴링 경합.
  도구는 이후 BOOTING 상태로 기다리도록 수정함.
- virt에서 mmcblk0p3가 없으므로 OS 설정 mount 실패. 테스트 복사본만 vda3로 변경.
  이를 Pi 이미지의 잘못된 fstab으로 판단해 배포 설정을 바꾸지 않음.
- raspi4b 직접 부팅: 30초 timeout, 커널 로그 없음. 원인 확정 못함.
  virt 성공을 Pi4 부팅 성공으로 대체하지 않음.
- 표식 파일 요구 폐기: 기존 T09의 marker 부재 FAIL은 무효. 사용자 최종 확인대로
  첫 USB 대상 정책을 유지했으며 marker 없는 최종 후보 T01도 실제 PASS.

원본 실패 로그는 `runs/20261019-063433`, `063517`, `063738`에 보존했다.
최종 채택 판정과 각 로그 연결은 BACKUP_TEST_RESULTS.md에 기록했다.
