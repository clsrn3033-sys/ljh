# MEBS V2 실제 가상 디스크 시험

V1 문서와 원본 이미지는 보존한다. 테스트는 QEMU ARM64 `virt`에서 기존
Buildroot 커널·rootfs·BusyBox init·S50mebs·runtime800을 실행한다. Raspberry
Pi 4B 하드웨어/EEPROM 부팅 성공을 의미하지 않는다.

## 실행

현재 Bazzite에 설치된 Python(Pillow, pexpect), QEMU, mtools, dosfstools,
e2fsprogs, util-linux, ffmpeg를 사용한다. 시스템 패키지를 설치하지 않는다.

```sh
cd /var/home/bazzite/ljh
python3 tests/v2-integration/run.py --images output/pi4-v2-validated-20261019/images
# 하나만 재시험
python3 tests/v2-integration/run.py --images output/pi4-v2-validated-20261019/images --cases T01
# 실제 raspi4b 보드 모델의 30초 제한 시험
python3 tests/v2-integration/probe_raspi4.py --images output/pi4-v2-validated-20261019/images
```

QMP Unix 소켓을 허용하는 로컬 터미널에서 실행한다. Codex 제한 샌드박스가
소켓 bind를 차단하면 도구의 승인된 실행 권한을 사용한다. sudo나 host mount,
loop 장치, 실제 /dev/sdX에 대한 명령은 필요하지 않다.

각 실행은 `runs/<시간>/results.json`, `environment.json`, `logs/`,
`screenshots/`에 증거를 남긴다. 스크립트 종료값 1은 FAIL/BLOCKED 항목 존재를
뜻한다. T12는 수동 포맷 기능이 없어 BLOCKED이며 실제 포맷 버튼 시험을
수행했다고 기록하지 않는다.

## 이미지와 격리

- 입력 raw 이미지의 SHA-256을 시작·종료 시 비교한다.
- `/tmp/mebs-v2-suite-*` 안에만 가상 디스크를 만든다. 테스트 종료 시 해당
  실행에서 생성한 임시 디렉터리를 정리한다.
- rootfs의 `/etc/fstab`에서 설정 파티션 이름만 `mmcblk0p3` → `vda3`로
  바꾸는 **테스트용 복사본**을 만든다. 원본 및 배포 이미지의 Pi 경로는 유지한다.
- kernel cmdline은 `root=/dev/vda2 ... console=ttyAMA0`이다. `init=/bin/sh`를
  사용하지 않는다. 서비스는 정상 init 경로로 자동 실행된다.
- 외장 타깃은 ext4, 카메라 원본은 FAT32 regular image file이다. 원본은
  QEMU 블록 계층에서도 read-only로 연결하고 전체 이미지 해시를 비교한다.
- 실제 JPG/MP4/XML, 기타/빈 파일, 동일 내용·동일 이름의 다른 폴더 파일,
  한글/중국어/공백/특수문자 이름, 빈 폴더를 생성한다. 동영상은 ffmpeg로 만든다.
- T04/T05는 QMP USB 장치 제거, T06은 해당 테스트 QEMU PID에 SIGKILL을
  보내고 다시 부팅한다. 실제 전기적 USB 장애나 배터리 차단을 재현하지는 않는다.
- T07은 guest의 복사본 한 바이트를 변경하고 실제 `mebs.backup.verify`를
  호출한다. 백업 종료 후 자동 변조 감시 기능의 시험은 아니다.

## 수정 이미지 재생성

```sh
python3 tests/v2-integration/build_fixed_image.py \
  output/pi4-v2-dsi-800x480-20261018/images \
  output/pi4-v2-utf8-reproduced/images
```

새 출력 디렉터리만 허용한다. 기존 로컬 Buildroot 빌드의 커널/펌웨어를
재사용하고 Python 소스 `mebs/appliance.py`와 `/etc/default/seedrng` 설정을 새 ext4 및 raw IMG에 반영한다.
이는 전체 커널 재컴파일이 아니다. 수정 파일 해시와 기반 이미지 해시는
`V2_FIX_PROVENANCE.json`에 기록된다. 새 이미지는 실물 검증 전 후보본이다.

## UI 화면 증거

T01 완료 후 VM 안에서 `mebs.ui800.render`를 실행해 실제 서비스 상태 JSON을
렌더링하고 PNG를 추출한다. 별도 가상 상태값이나 가짜 배터리 수치를 주입하지
않는다. 이것은 guest의 offscreen 렌더링 증거이며 DSI framebuffer 출력이나
실제 터치 이벤트 증거는 아니다.

사용자 최종 확인: `수정금지.txt`는 필요하지 않다. 첫 USB가 대상, 두 번째 USB가 원본이다. 현재 재실행 fixture는 표식 파일 없이 생성한다. T09는 표식 부재가 아니라 지원하지 않는 FAT32 대상의 거부를 검사한다. 실제 대상 파일시스템은 ext4만 지원한다.
