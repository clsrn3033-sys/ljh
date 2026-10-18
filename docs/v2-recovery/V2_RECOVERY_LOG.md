# V2 복구 작업·명령 기록

2026-10-19, BC250 Bazzite. 사용자 데이터 저장장치·실제 SD·EEPROM·GPIO 전원에는
쓰기 명령을 실행하지 않았다. V1과 기존 커밋/이미지를 보존했다.

| 단계 | 원인과 수행 내용 | 증거 |
|---|---|---|
| 기준 확보 | `git status`, `git log`, V1 결정사항, Pi IMG 구조와 기존 12개 실패 기록 확인 | `V2_ERROR_AUDIT.md` |
| 중복 복사 | 완료된 job을 다시 사용하지 않던 엔진에 **기존 job의 SHA-256·경로·폴더·메타데이터를 재검증한 뒤에만** 재사용하는 경계 추가. 불일치면 새 job 생성; 기존 백업 덮어쓰기 없음 | `mebs/backup.py`, 새 단위·QEMU 시험 |
| 빈 카드 | 스캔 후 파일 0개면 미완료·비성공 메시지 표시, 새 job 생성 전 중단 | `mebs/backup.py` |
| 중단 작업 | 대상 외장하드만 연결했을 때 ext4 `ro,noload`로 잠깐 검사해 pending 개수 표시. 재연결한 원본으로 새 작업을 시작하며 중단된 폴더는 보존 | `mebs/appliance.py`, `runtime800.py`, QEMU SIGKILL 재시험 |
| 중단 작업 재발견 | v3 반복 시험에서 강제 종료로 손상된 pending inode의 `is_dir()` 검사가 거짓을 반환해 경고가 누락됐다. ext4 `ro,noload`에서는 디렉터리 내용을 열지 않고 **pending 이름 자체**로 경고한다. v4에서 SIGKILL→재부팅→경고→재백업을 재시험했다 | `runs/20261019-072240`, `runs/20261019-072405` |
| RAM/N/A | `/proc/meminfo`의 MemTotal/MemAvailable로 실제 사용률 계산. 값이 없으면 N/A. CPU/배터리도 미연결 시 N/A | `mebs/sensors.py`, `ui800.py` |
| 용량 재사용 | 저장 공간 부족이면 새 복사는 막되 검증된 동일 job의 재사용은 허용. 엔진 단계에서 필요·잔여 수치 표시 | `mebs/runtime800.py`, `backup.py` |
| 이미지 조립 오류 | 새 이미지 편집 도구가 이미 있는 `/etc/default`에 `mkdir`을 재시도해 시험용 rootfs가 fsck 실패. 기존 디렉터리를 재생성하지 않도록 수정 후 **새 경로**에 재조립·fsck | `tests/v2-integration/logs/recovery-image-build.log`, `recovery-v3-image-build.log` |
| 별도 이미지 | Pi image는 mmcblk 경로 유지. QEMU image는 **복사본의** fstab만 vda3로 조정. 물리 디스크 마운트 없음 | image provenance JSON |
| 회귀 재시험 | v4의 FAT32 원본·ext4 대상 실제 이미지로 자동화 11개 PASS, 포맷 1개 BLOCKED; 같은 QEMU 디스크 20회 부팅 20/20 READY | `runs/20261019-072715/results.json`, `boot-runs/20261019-073645/summary.json` |

실패한 첫 조립 디렉터리 `output/pi4-v2-recovery-20261019`와 수정 도중 만들어진
두 중간 이미지는 삭제하지 않고 `DO_NOT_USE_THIS_IMAGE.txt`로 표시했다.
v3 역시 반복 시험에서 복구 경고가 누락돼 보존하되 사용하지 않는다.
최종 판정 대상은 `output/pi4-v2-recovery-v4-20261019/images/sdcard.img` 하나다.
기반 IMG SHA-256은 `27104982a1c9d5a6931d6ce4c3f301f53041e261365e43a5c759eece261f94ec`,
v4 raw IMG SHA-256은 `90cf0debeb8e2405224de9ad99c0ba80a23932bbf917d70f22c7936f6db68f27`이다.
이미지 파일 자체와 [조립 출처](../../output/pi4-v2-recovery-v4-20261019/images/V2_FIX_PROVENANCE.json)에 두 해시를 기록했다.

재현 명령:

```sh
python3 -m unittest discover -s tests -q
python3 tests/v2-integration/build_fixed_image.py \
  output/pi4-v2-validated-20261019/images output/pi4-v2-recovery-v4-20261019/images
python3 tests/v2-integration/build_qemu_image.py \
  output/pi4-v2-recovery-v4-20261019/images \
  output/pi4-v2-recovery-qemu-v4-20261019/images/qemu-virt.img
python3 tests/v2-integration/run.py \
  --images output/pi4-v2-recovery-v4-20261019/images \
  --prepared-os output/pi4-v2-recovery-qemu-v4-20261019/images/qemu-virt.img
```

이미지 조립은 이미 **BC250에서 소스로 빌드한 Buildroot 2026.08 커널·펌웨어·rootfs**의
새 복사본에 Python/config를 반영했다. 이번 수정에서 커널/toolchain을 전면 재컴파일하지
않았고, 새 이미지를 Pi4B 실물 부팅 성공으로 판정하지 않는다.
시험 실패는 지우지 않고 새 실행의 로그와 판정을 병기한다.
