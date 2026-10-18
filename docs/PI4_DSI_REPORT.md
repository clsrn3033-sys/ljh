# MEBS Raspberry Pi 4B / 800×480 DSI 통합 개발 기록

작성: 2026-10-18. 최신 첨부 원본 로고 적용·하드웨어 변경 설계는 [PI4B_HARDWARE_REV_A.md](PI4B_HARDWARE_REV_A.md)를 우선 참고한다. 최신 로고 오류 대응·8.4V 정보·실물 식별 도구 추가 결과는 [HARDWARE_IDENTIFICATION.md](HARDWARE_IDENTIFICATION.md)를 우선 참고한다. 아래 최초 조사에서 로고 실행 불가로 기록한 부분은 현재 안전한 텍스트 fallback으로 보완됐지만 원본 픽셀 복원은 미완료다. **소프트웨어 모의 테스트용 개발본이며 부팅 이미지 완성본이 아니다.**

## 1. 조사 대상과 보존

실제 GitHub `clsrn3033-sys/ljh`의 다음 소스를 조사했다. 원격 push/게시하지 않았다.

| 대상 | 커밋 |
|---|---|
| main, mebs-pi4-v0.1.0 | `7385423490f6b940c10ff4d8ab303cf442699c77` |
| feature/mebs-480x320-final-ui-20261018 | `8cb5aa521bcabf502c136f52f769b995517bdcc2` |
| feature/mebs-boot-animation | `085e17f044a37d8521c07ab3339b2321acd4617e` |

별도 개발 위치: `/workspace/1/work/ljh-pi4-dsi`, 로컬 브랜치 `feature/pi4-dsi-controls`.
수정 전 main/480/boot 전체 Git 소스를 `/workspace/1/work/baselines/ljh-{main,ui480,boot}.tar`에 보존했고 `manifest.json`에 SHA-256을 기록했다. 기존 `mebs-pi4` 보드 설정은 수정하지 않고 `mebs-pi4-dsi`로 복제했다.

Git에는 실제 과거 Buildroot `sdcard.img`가 없다. README의 289MiB는 **기존 기록**이며 이 환경에서 원본 이미지를 검증하거나 백업했다고 주장하지 않는다. 이 환경에 남아 있는 과거 Debian ARM64 ZIP·이미지, `/workspace/1/original-source`, `/workspace/1/releases`는 변경하지 않았다. Debian 이미지를 이번 Buildroot 이미지로 사용하거나 이름만 바꾸지 않았다.

### 요청과 실제 소스의 차이

- 실제 최신 소스는 Buildroot 2026.08 external tree다. 이전 로컬 Debian 프로젝트와 구분했다.
- 기존 Pi4 설정은 HDMI/VC4 KMS다. 조사한 브랜치에는 SPI LCD overlay/드라이버/실행 설정이 없어 제거할 SPI LCD 설정도 없다. SPI 버스를 끄는 변경은 하지 않았다.
- `backup.py`는 구조/파일/XML/mtime/권한/xattr/SHA-256 보존, ext4 대상, vfat/exfat/ntfs/ext4 원본을 지원한다. 사진·영상·XML별 분류 규칙이나 별도 날짜별 분류기는 발견되지 않았다. 기존 UTC 날짜가 포함된 작업 폴더와 원본 폴더 구조를 유지한다.
- 사용자 최신 지시로 `수정금지.txt`/`.text` 표식 파일을 이용한 장치 구분은 폐기했다. **연결 순서만으로 첫 번째 USB=백업 대상, 두 번째 USB=원본 SD**로 정한다. 표식 파일을 요구·생성·삭제하거나 그 유무로 역할을 바꾸지 않는다. 기존 순서 판별 코드가 이 방식이므로 엔진 변경은 필요하지 않다. SD 포맷 구현은 별도 미완료이며 계속 비활성화한다. 검증 성공만으로 포맷·삭제하지 않는다.
- main/boot의 실제 제작자 표기는 `제49기 보도부 이정헌 / Produced by 이정원`이다. 이를 유지했다. 과거 요청의 다른 문구로 임의 교체하지 않았다.
- boot 브랜치의 `LOGO_MASK`를 원문 그대로 가져와 실행했으나 `ValueError: base85 overflow in hunk starting at byte 1250`가 발생했다. 원본 마스크를 고치거나 새 로고를 만들어 대체하지 않았다. 새 메인 UI는 main의 정상 텍스트 MEBS 로고로 fallback한다. 라이브 splash 어댑터는 오류를 알리고 메인 화면으로 넘어간다. **승인된 원본 로고의 페이드 애니메이션은 현재 실행 불가/미완료**이며 유효 원본 로고 파일이 필요하다. 정상 마스크가 제공되면 기존 frames/렌더러를 800×450로 비율 유지해 800×480에 배치하는 연결부가 준비되어 있다.

## 2. 변경 파일과 설계

원본 `backup.py`, `devices.py`, `appliance.py`, `session.py`, 기존 UI·테스트·Pi4 프로필은 수정하지 않았다.

| 파일 | 추가/변경 내용 |
|---|---|
| `mebs/boot_animation.py` | 기존 boot 브랜치 파일을 변경 없이 보존·가져옴 |
| `mebs/logo_asset.py`, `tests/test_logo_asset.py` | 손상 로고 예외 처리·PNG 로더·fallback 및 실물 식별 테스트6개 |
| `scripts/pi4-hardware-report.py` | 실제 Pi4B의 바인딩된 드라이버/DRM/터치 식별 정보 읽기 전용 수집 |
| `mebs/settings.py` | 검증된 설정, 임시 파일 fsync→원자 교체→디렉터리 fsync, 실패 표시 |
| `mebs/sensors.py` | 명시적 INA226/BH1750 I²C, CPU 온도, 밝기 필터, 추정 SOC/runtime, 배터리 시작 보호 |
| `mebs/rtc.py` | DS3231 BCD/날짜/OSF 검증, 주입 가능한 UTC 복원·명시적 최초 설정 API |
| `mebs/controls.py` | UI 상태·잠금·대기·종료 확인/예약, 동기화/로그/종료 경계, 미래 래치 추상 인터페이스 |
| `mebs/ui800.py` | 기존 색상/메인 렌더러/크레딧을 이용한 800×480 상태/빠른 설정/확인창 |
| `mebs/runtime800.py` | 독립 백업 worker, 별도 센서 thread, 표시/터치 loop, 디스플레이 없이 진행 |
| `mebs/preflight.py` | 원본 실제 크기·대상 할당 단위/가용 공간 사전 표시, 필요/잔여 용량 오류 |
| `mebs/touch.py` | 지정 evdev 절대 좌표, 범위 변환, 0/180도, 접촉 해제 시 제스처, 유실/다중 접촉 취소 |
| `mebs/drm_presenter.c` | libdrm dumb buffer 직접 KMS 출력, 연결된 800×480 mode만 사용, 기존 CRTC 복원 |
| `mebs/outputs.py` | DRM helper 프레임 전달/시간 제한, 기존 fbdev 대안, 명시적 sysfs 백라이트 |
| `buildroot/package/mebs/{Config.in,mebs.mk}` | 선택적 CONTROLS/libdrm 패키징·교차 컴파일 |
| `buildroot/board/mebs-pi4-dsi/` | 기존 프로필 복사 + 센서/입력 인터페이스, 별도 설정 파티션, 신규 런타임 시작 |
| `scripts/pi4-dsi-image.sh` | 기존 출력과 분리한 이미지 빌드, glibc/C++/한글 폰트/해시 검증 유지 |
| `scripts/host-tools.py` | 서명·해시 검증 APT 패키지의 로컬 추출, 호스트 시스템 설치 없음 |
| `tests/test_controls800.py` | 새 컨트롤·센서·RTC·worker·evdev 경계 테스트 29개 (로고/식별6개는 별도 test_logo_asset.py) |
| `docs/logs/`, 이 문서 | 실제 테스트/빌드/성능 결과·미완료 항목 |

백업 worker는 UI를 호출하지 않는다. 제스처/렌더링은 다른 loop에서 처리한다. 원본 `run_job()`이 읽기 전용 원본 mount→복사→독립 SHA 검증→syncfs→정상 unmount를 수행한 뒤에만 `SAFE_TO_REMOVE`가 된다. USB 역할은 첫 단독 관측=대상, 두 번째=원본이다. 동시 연결·둘 다 부팅 전 연결·분리/교체·3개 이상은 모호 상태로 막는다. 두 번째 USB가 실제 SD인지 하드웨어 유형을 판별하는 기능은 아직 없다. 외장 하드를 먼저 연결하고 STORAGE READY를 확인한 뒤 SD를 연결한다. 동시 연결이나 모호 상태에서는 자동 백업을 시작하지 않고 두 장치를 모두 분리한 뒤 같은 순서로 다시 연결하도록 안내한다.

공간 사전 검사는 원본 파일 실제 크기, 대상 파일시스템 할당 단위, 디렉터리와 1MiB 여유를 계산한다. 엔진도 자기 잠금 안에서 다시 검사한다. 파일시스템 메타데이터가 큰 경우 등 실제 ENOSPC는 여전히 발생할 수 있으므로 기존 오류/미완료 작업 보존이 최종 방어다.

`화면 끄기`는 백라이트 경로가 확정되면 밝기 0을 쓰고, 미설정이면 검정 프레임만 표시한다. 검정 프레임을 실제 패널 전원 차단으로 보고하지 않는다. 백업은 계속된다. 첫 터치는 화면만 깨우고 동작을 실행하지 않는다. 잠금 해제는 상단 왼쪽 180×72 영역 2초 이상 길게 누르기다. 잠금 중에도 설정창 전원 확인과 오류 표시는 접근 가능하다. 야간 모드는 밝기 상한 30%다. 센서 미설정/실패 시 자동 밝기는 수동 값으로 fallback한다.

종료는 확인창을 거친다. 백업 중이면 예약만 저장하고 성공 및 안전 분리 flag까지 기다린다. 오류/취소는 예약을 취소한다. 사용자가 오류 후 직접 다시 종료를 확인할 수는 있지만 남은 mount/flush 실패가 있으면 종료하지 않는다. 신규 작업 시작과 종료 경계를 하나의 lock으로 직렬화했다. 로그 fsync와 파일시스템 동기화 전에는 poweroff를 호출하지 않는다. 실제 `/sbin/poweroff`는 전용 이미지의 live 모드에서만 연결하며 테스트에서는 mock만 사용했다. 배터리 전원 차단 GPIO는 없다.

미완료 `.mebs-pending-*` 작업은 그대로 보존하고 별도 새 작업으로 재시도한다. 중단 지점 이어 쓰기는 구현하지 않는다. 기존 작업을 덮어쓰거나 포맷으로 복구하지 않는다.

## 3. 패키지·커널·Device Tree 변경

대상 추가: 선택적 `libdrm`과 의존 `libpthread-stubs`, util-linux `hwclock` 구성요소. 기존 Python3/Pillow/freetype/util-linux 사용. 센서는 Python 표준 라이브러리 fcntl/os로 접근하며 smbus 패키지를 추가하지 않는다. 기존 대상 패키지 삭제 없음. X11, 데스크톱, Mesa/EGL, 소리·부저·진동 사용자 패키지 추가 없음. 기존 VC4가 요구하는 커널 ALSA core 설정은 유지한다.

호스트 전용: cpio/rsync/bc/bison/flex, libdrm-dev/libssl-dev/libelf-dev, Noto CJK와 의존 패키지를 `.local-build/sysroot`로 서명 검증 추출. `.venv`에 Pillow 12.3.0. 호스트 `/usr`에는 설치하지 않았다. 실제 패키지/버전/해시는 `.local-build/packages.json`에 있다.

새 프로필의 fragment 추가: I2C_CHARDEV, INPUT/EVDEV/TOUCHSCREEN, RTC_CLASS/RTC_DRV_DS1307, BACKLIGHT_CLASS_DEVICE, DRM_VIRTIO_GPU. 기존 VC4/KMS/fbdev/스토리지 드라이버를 유지했다. **이는 요청한 설정이며 커널 빌드·최종 .config로 실현 여부를 검증하지 못했다.**

`config.txt`: `dtparam=i2c_arm=on` 추가. VC4 KMS 유지. 특정 DSI panel/touch overlay, DS3231 overlay는 아직 적용하지 않았다. 강제 HDMI video 인자는 새 cmdline에서만 제거했다. 패널을 모르는 상태에서 overlay 이름이나 60Hz timing을 추측하지 않는다. `display_auto_detect=0`은 원래 설정을 유지하며 패널 식별 뒤 재검토한다.

새 genimage 구성은 기존 96MiB boot +192MiB rootfs에 **8MiB 설정 ext4 파티션**을 추가한다. `/dev/mmcblk0p3`만 `/var/lib/mebs`에 mount하도록 fstab에 기록한다. USB를 설정 저장소로 사용하지 않는다. 이 파티션이 mount되지 않으면 live 서비스는 쓰기 위치를 임의 대체하지 않고 시작을 거부한다. 실제 이미지 조립 결과·최종 크기는 아직 없다.

## 4. 실행·빌드

개발 폴더에서:

```sh
python3 scripts/host-tools.py
python3 -m venv .venv
.venv/bin/python -m pip install Pillow==12.3.0
export MEBS_FONT="$PWD/.local-build/sysroot/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m mebs.runtime800 --mock-preview artifacts/ui800
```

`artifacts/ui800/{main,settings,shutdown}.png`는 **모의 데이터**이며 실제 DSI 캡처가 아니다. 미리보기 명령은 mount·I²C·시계 변경·종료를 실행하지 않는다.

```sh
# Buildroot 소스는 2026.08 태그 checkout, commit 813cbac680a73092e1ebb86da72972c44573145c
scripts/pi4-dsi-image.sh
# 별도 경로: output/pi4-dsi-800x480/images/sdcard.img
```

스크립트는 SD카드를 쓰거나 기존 이미지를 덮어쓰지 않는다. 이 경로의 완성 이미지는 아직 없다. 2026.08 소스를 새로 구할 경우 공식 GitHub buildroot/buildroot의 해당 태그/커밋을 확인한다. 해시 검증 옵션은 비활성화하지 않는다.

실제 전용 이미지에서만 `/usr/bin/python3 -m mebs.runtime800 --config /etc/mebs/hardware.json` 또는 `--headless`. PYTHONPATH=/usr/lib/mebs, MEBS_FONT=/usr/share/fonts/mebs/NotoSansCJK-Regular.ttc. init 스크립트가 이를 설정한다. 일반 PC에서 live 모드를 실행하지 않는다. `hardware.json`은 현재 출력/입력/센서를 명시적으로 미설정 상태로 둔다. 패널 확인 뒤 DRM card, evdev touch, 실제 sysfs backlight 경로를 지정해야 한다. 원하는 mode가 없으면 KMS helper가 실패하고 백업 worker는 headless로 계속 진행한다.

## 5. 사용자 제공 하드웨어 사양과 미확정 항목

| 구성 | 확인/동작 조건 |
|---|---|
| DSI LCD | 5인치/800×480/약60Hz/정전식/DSI 전원/플러그앤플레이 설명. **모델·패널·터치 컨트롤러 미확정**. Raspberry Pi OS 드라이버 포함을 Buildroot 자동 지원으로 해석하지 않음 |
| INA226 | A0/A1 조합으로 0x40~0x4F 주소 가능. 기본 예정 0x40. 실제 보드 션트 값/정격/전류 방향 미확정. ID 확인 후 bus/shunt 레지스터를 읽음. 션트 미확정이면 전류/SOC/runtime은 `--` |
| BH1750 | 예정 0x23(대체0x5C), 실물 ADDR/풀업 확인 필요. 연속 고해상도 후 최대180ms 대기, 로그 조도 곡선 +2초 필터 +10%/s 변화 제한 |
| DS3231 | 예정0x68. 커널 RTC 드라이버와 hwclock 경로 사용, 직접 I²C 어댑터는 별도 테스트/최초설정 API. 커널과 사용자 코드로 같은 주소를 동시에 점유하지 않음 |
| 충전 모듈 | 보라색, 기본2S/선택3S, Type-C QC2/3, boost15W, 기본약1.4~1.5A, I=90000/RISET, 4.2V/cell(2S8.4V), 2S에서 BM 중간점 balancing. 사용자가 제공한 판매 사양이며 실측 아님 |
| 배터리/BMS | 실제 셀·용량·방전 한계/BMS 차단전압/부하 전류 미확정. 충전 모듈 보호 목록을 별도 BMS의 방전 보호로 간주하지 않음. 보호 임계값/OCV/capacity는 null |
| NTC | **100K B4100은 충전 모듈 NTC 보호 단자 전용**. 제조사 배선/허용 온도 곡선 확인 필요. GPIO/ADC에 연결하지 않음 |

센서 배선: 물리1=3.3V, 물리3=GPIO2/SDA, 물리5=GPIO3/SCL, 물리6=GND. 3.3V 호환/풀업 전압/주소 중복을 실측해야 한다. DSI 터치가 별도 I²C 주소를 사용할 수 있으므로 센서 주소와 함께 확인한다. 소프트웨어는 활성 센서 간 중복 주소를 거부하고 I2C_SLAVE_FORCE를 사용하지 않는다. 미확정 하드웨어에는 자동 bus scan을 하지 않는다.

**추가 GPIO 없음.** NTC/ADS1115/부저/진동/전원 차단 핀은 없다. FuturePowerLatch는 NotImplementedError만 반환한다.

배터리 가드는 임계값이 둘 다 설정되어 있을 때만 활성이다. 측정 누락/차단 전압 이하에서는 신규 작업을 막고, 이미 실행 중인 복사를 즉시 끊거나 배터리 전원을 차단하지 않는다. 기본 null 상태는 **보호 미구성**이며 배터리 보호가 보장되지 않는다. 테스트의 7.1/6.8V 값은 가상 값이며 실기기 권장값이 아니다. 실제 BMS보다 충분히 앞서 종료할 수 있는 여유 전력·시간을 실측해 정해야 한다.

RTC 실기기 최초 설정은 정확한 UTC 시스템 시간을 먼저 지정한 뒤, 확인된 RTC 장치에 `hwclock --systohc --utc --rtc /dev/rtcN`을 명시 실행한다. 부팅 복원은 hardware.json의 ds3231 enabled/device 설정과 DT 확인 후에만 활성화한다. 통합 UI의 시각 편집기나 네트워크 NTP 서비스는 아직 추가하지 않았다.

## 6. 테스트 결과

환경: Debian13 x86_64 호스트, Python3.12/Pillow12.3.0. **QEMU/실물 Pi4가 아닌 호스트 테스트**다.

- 기존 75 + 신규43 = **118 tests, OK**. `docs/logs/pi4-dsi-tests.log`.
- 기존 엔진/메타데이터/무결성/원본 보호/프로세스 SIGTERM·SIGKILL/동시성 테스트 유지.
- `drm_presenter.c`: x86_64 gcc `-Wall -Wextra -Werror` 컴파일 성공. 연결된 DRM 장치가 없어 scanout 시험 미실시. 이 바이너리는 ARM64 대상 산출물이 아니다.
- UI PNG를 생성하고 육안으로 한국어·800×480·버튼/확인창 배치를 확인했다. evdev 실제 장치·DSI 출력은 미실시.

| 요구 테스트 | 실시 결과와 범위 |
|---|---|
| 1 800×480 렌더링 | 모의 state PNG + 크기/RGB 확인 통과 |
| 2 설정 열기/닫기 | swipe 상태 전환 테스트 통과 |
| 3 터치 버튼 | 제스처/확인 취소·잠금·evdev 좌표/유실/다중 접촉 모의 통과 |
| 4 밝기 | slider/영속 저장/야간 상한/필터 테스트 통과. 물리 backlight 미실시 |
| 5 온도/배터리 | 모의 표시와 INA 변환 테스트 통과. 실측 미실시 |
| 6 백업 중 설정 | 실제 임시 파일 복사 worker를 진행하며 UI 상태 조작, 복사/검증 완료 통과 |
| 7 백업 중 종료 예약 | 복사 중 poweroff 미호출, 예약 대기 통과 |
| 8 완료 후 종료 | SAFE flag/worker 경계→sync→log→sync→mock poweroff 순서 통과. OS 실종료 미실시 |
| 9 SD 분리 | copy 중 source inventory 제거→ERROR, 원본 보존 통과 |
| 10 외장 분리 | copy 중 target inventory 제거→ERROR 통과 |
| 11 용량 부족 | 기존 엔진 statvfs 부족 검사와 실제 크기 사전 계산/필요·잔여 오류 통과 |
| 12 검증 실패 | 기존 실제 백업 변조→ERROR/unsafe 테스트 통과. formatter 자체 없음 |
| 13 전원 차단 복구 | 기존 child SIGKILL 및 새 미완료 보존/별도 재시도 통과. 실제 전원 차단 내구성 미실시 |
| 14 RTC 복원 | DS3231 BCD/OSF/UTC setter 모의 통과. 커널 hwclock/실제 RTC 미실시 |
| 15 센서 미연결 | I²C open/CPU 경로 오류 주입→unknown/오류 표시 통과 |

x86 호스트 렌더링만 60회씩 측정: 메인 중앙값9.394ms, 설정15.084ms. `ui800-render-benchmark.json`. 프레임 전송/scanout/input 지연은 제외되어 **실제 60FPS 달성 근거가 아니다**. 기본 렌더 목표30fps, 설정상1~60 허용이며 실기기 측정 뒤 조정한다. 단일 KMS dumb scanout 버퍼라 tear-free를 보장하지 않는다.

## 7. 빌드 실패·해결 절차·최종 상태

`docs/logs/pi4-dsi-build.log`: Buildroot defconfig/olddefconfig 생성 및 호스트 의존성 점검 뒤 **host-pkgconf-2.3.0 다운로드 실패**, make exit2.

```
https://distfiles.ariadne.space/pkgconf/pkgconf-2.3.0.tar.xz
https://sources.buildroot.net/pkgconf/pkgconf-2.3.0.tar.xz
Proxy tunneling failed: Forbidden
```

TLS나 소스 해시를 끄지 않았다. 소스 빌드가 이 단계에서 멈춰 커널/target rootfs/genimage는 미실시다. **새 sdcard.img 없음, 이미지 크기 변화 미측정, QEMU 부팅 미실시, 전원 투입→READY 5초 미측정**. 기존 README의 부팅 기록을 이번 결과로 인용하지 않는다.

`docs/logs/buildroot-package-info.json`은 현재 구성의79개 패키지 정보이며 필요한 공식 다운로드 도메인을 추출했다. 환경 설정 초안에는 다음을 저장했다: 재현 설치 스크립트, 새 작업 위치/검증 시작 지침, 기존 허용 도메인을 유지한 추가 Buildroot source 도메인. 도구 결과는 `status=saved`, **requires_publish=true**다. 초안 저장만으로 실행 중 네트워크가 바뀐 것은 아니다.

환경 설정에서 저장된 초안을 검토·게시해 source 다운로드 도메인을 적용한 후, 위 빌드 명령을 다시 실행해야 한다. 최소 현재 차단 대상 `distfiles.ariadne.space`, `sources.buildroot.net`; 의존성별 전체 목록은 `docs/logs/network-domains.txt`. 다음 다운로드가 실패하면 해당 로그/서명/해시를 확인하고 정상 경로로 허용 설정을 보완한다. 프록시 우회·검증 비활성화는 하지 않는다.

이미지 생성 후에도 실제 ARM64 커널/rootfs QEMU smoke→가상USB 원본/대상→검증/분리/종료를 다시 시험해야 한다. Pi4 실제 DSI/터치·I²C·부팅속도는 QEMU 성공과 별도로 실기기에서 시험한다.

## 8. 실기기 승인 전 남은 작업

1. 정확한 패널 모델/보드 revision/터치 컨트롤러·지원 overlay와 timing 확인. 패널이 없는 상태와 연결된 상태 모두 headless/GUI 시험.
2. 원본 정상 로고 자산 확보·해독 오류 해결, 실제 boot fade/진행/READY 의미 검증.
3. 사진/영상/XML 분류·포맷 구현 위치 확인. 현재 구현에 없으므로 보존 완료라고 보고할 수 없다. 표식 파일 정책은 사용자 지시로 폐기했으므로 더 이상 확인 대기 항목이 아니다. 포맷을 추가한다면 검증/장치 identity/원래 fs/수동 선택/길게 누름/추가 확인을 별도 설계·가상디스크 시험해야 한다.
4. INA226 션트저항/전력정격/전류 방향, 실제 셀·BMS·용량·OCV 보정/저전압 및 종료 여유 측정. 3.3V와 주소 충돌 실측.
5. DS3231 DT/rtcN·OSF·최초 설정·재부팅 복원 및 터치/백라이트 sysfs 확인.
6. 소스 다운로드 제한 해제 후 실제 이미지 빌드·새 크기/해시/QEMU/정상 종료·설정 파티션 mount/영속성 확인.
7. Pi4 실제 전원 투입→READY 측정(목표5초), CPU/RAM/열/장시간 복사/DSI FPS·입력 지연/실제 전원 차단 복구 검증.

파일 내보내기: 소스·설정·모의 화면·테스트 로그는 `/workspace/1/MEBS-Pi4-DSI-source-test.zip`으로 별도 묶는다. **부팅 이미지가 아니다.** 이 환경에는 실제 첨부 업로드 도구가 없어 HTTPS 다운로드 URL을 생성하지 않았다. GitHub 업로드도 하지 않았다. 파일 경로를 다운로드가 보장되는 공개 URL이라고 보고하지 않는다.
