# 3차 작업 기록 — Raspberry Pi 4 micro-HDMI 이미지

사용자 지시 C9: 첫 연결 USB 디스크는 백업 대상 외장 하드, 다음 연결 USB 디스크는
원본 SD카드. Raspberry Pi 4의 micro-HDMI에 MEBS 상태 화면을 표시한다.

Buildroot 공식 2026.08 소스를 로컬에서 빌드했다. 호스트 패키지 변경 없이
GNU patch 2.8도 프로젝트 `.local-build/tools`에 소스로 빌드했다.
첫 설정 실패는 [pi4-build-initial.log](logs/pi4-build-initial.log),
부팅 파티션 32MiB 부족 오류는 [pi4-build.log](logs/pi4-build.log)에 남겼다.
최종 FAT32·1MiB 정렬 이미지 빌드 결과는
[pi4-build-release-fat32.log](logs/pi4-build-release-fat32.log)다.

## 이미지 구성과 동작

- Pi4용 Raspberry Pi 부팅 펌웨어, `bcm2711-rpi-4-b.dtb`, 64비트 Linux 커널,
  Buildroot rootfs, Python/Pillow/한글 글꼴/MEBS 서비스.
- 마이크로 HDMI 출력은 VC4 KMS와 Linux fbdev를 사용하며, `/dev/fb*` 중 DRM
  화면을 우선 선택한다. 데스크톱 환경은 없다.
- 부팅 화면은 `외장 하드를 먼저 연결해 주세요` → `SD카드를 연결해 주세요` →
  백업·SHA-256 확인 → 안전 마운트 해제 후 `분리 가능` 순서다.
- 부팅 때 USB 디스크가 하나뿐이면 이를 첫 외장 하드로 본다. 두 개가 이미 연결되어
  있거나 동시에 새로 감지된 경우, 둘 이상의 파티션, 이미 마운트된 장치는 거부한다.
  장치가 모호하면 두 디스크를 분리한 뒤 다시 시작해야 한다.
- 대상은 기존 **ext4** 외장 하드 한 파티션만 허용한다. 원본은 vfat/exfat/ntfs/ext4
  한 파티션을 읽기 전용으로 마운트한다. 사용자 저장장치 포맷·삭제는 하지 않는다.
  실제 파일시스템별 실물 검증은 별도로 필요하다.
- 원본은 블록 장치와 파일시스템을 읽기 전용으로 지정한다. 대상 flush와 두 장치의
  일반 unmount가 성공해야만 `분리 가능`으로 표시한다. 강제/지연 unmount는 사용하지 않는다.
- rootfs는 읽기 전용으로 부팅하고 임시 상태·로그는 `/run` tmpfs에 둔다.

USB 저장장치 연결에는 Pi의 USB 포트 또는 USB 카드 리더를 사용한다. Pi4가
부팅하는 microSD 카드 자체를 백업 원본으로 자동 선택하지 않는다.
외장 하드가 NTFS/exFAT이면 현재 시험 이미지는 백업을 시작하지 않고 오류를 표시한다.
백업 대상의 지원 형식 확장은 메타데이터 보존 기준과 함께 결정할 예정이다.

## 개발 호스트 검증

- 기존 50개를 포함한 Python 테스트 **63개 통과**:
  [phase3-unit-tests.log](logs/phase3-unit-tests.log).
- ARM64 대상 Python 3.14.7/Pillow 12.0.0을 QEMU 사용자 모드에서 실행해
  한글 READY 화면 PNG 렌더링 성공 (`ARM-render 38114`).
- 같은 ARM64 대상으로 임시 XML 파일의 백업과 별도 SHA-256 검증 성공
  (`ARM-backup VERIFIED clip.XML b'<clip/>'`).
- 정상 작업은 재검증과 flush·unmount 이후에만 분리 가능을 표시하는 단위 시험 통과.
  오류·장치 교체·취소·마운트 해제 실패에서는 분리 가능으로 표시하지 않는다.
- 오프라인 화면 재생은 순서 변경 후 다시 생성했으며 재생 제어 검사 통과.
- QEMU ARM 가상 보드가 최종 Buildroot 커널과 읽기 전용 rootfs로 부팅됨.
- 최종 rootfs의 init으로 부팅했을 때 `S50mebs`가 자동 실행되어 MEBS appliance
  프로세스·잠금·서비스 로그가 생성되는 것을 확인하고 정상 종료함. 가상 보드에는
  framebuffer가 없어 서비스는 화면 장치를 기다리는 상태였다.
- QEMU USB 시험에서 가상 외장 하드(`/dev/sda`, ext4)와 읽기 전용 카메라 카드
  (`/dev/sdb`, FAT)를 인식했다. 대상/원본을 명시해 실제 `run_job` 경로를 실행한 결과:
  `MOUNTING → SCANNING → COPYING → VERIFYING → FINAL_CHECK → UNMOUNTING → SAFE_TO_REMOVE`.
  최종 결과 `SAFE_TO_REMOVE True`, 양쪽 USB 마운트 지점 비어 있음.
- 호스트에서 대상 ext4 이미지를 읽어 완료 작업의 `manifest.json`과 XML 파일을 확인.
  `DCIM/C0001.XML`의 SHA-256은 원본 시험 파일과 동일한
  `1a7df833e5a511c0f1b4fd0aae14dab1c81374d0bfe7ffdc4ebbcf8f7190c0f2`.
  `e2fsck -fn`도 오류 없이 완료. [QEMU USB 검사 기록](logs/pi4-qemu-usb-validation.log).

화면 렌더링과 첫 백업 샘플은 QEMU **사용자 모드**, USB 마운트·백업 검증은 QEMU
**ARM 가상 보드의 실제 Linux 게스트**에서 실행했다. 게스트에서는 프레임버퍼가
없어 MEBS 자동 화면 서비스의 표시/삽입 순서 연동은 직접 시험하지 못했다.
삽입 순서 상태 머신은 호스트 단위 시험으로 검증했다.
QEMU의 `raspi4b` 기종으로 SD 카드 부팅도 시도했으나, PCIe 등 주변장치 비활성화
경고만 출력되고 직렬 콘솔 부팅을 확인하지 못했다. 이 결과로 Pi4 실물 부팅 성공을
주장하지 않는다. [보드 에뮬레이터 기록](logs/pi4-qemu-board-second-uart.log).

## 최종 이미지 산출물과 실물 시험

최종 원시 SD 이미지: [sdcard.img](../output/pi4-hdmi/images/sdcard.img)

```text
크기: 303,038,464 바이트 (289 MiB)
SHA-256: 61203cb0f621c193dc827c6d1bd0b069327b3905b59a638d80fe514de658629d
파티션 1: FAT32 부팅, 96 MiB, LBA 2048(1 MiB)에서 시작
파티션 2: ext4 읽기 전용 rootfs, 192 MiB
```

[이미지 검사 로그](logs/pi4-image-inspection.log)에서 `config.txt`, `cmdline.txt`,
`start4.elf`, `fixup4.dat`, Pi4 DTB, ARM 커널과 rootfs의 MEBS 서비스·한글 글꼴을
읽기 전용으로 확인했다. 같은 구조 검사는
`bash scripts/inspect-pi4-image.sh output/pi4-hdmi/images`로 재실행할 수 있다.
검사 스크립트는 이미지 디렉터리 또는 `sdcard.img` 파일 경로를 모두 받는다.
동일 디렉터리의 `sdcard.img.sha256`에는 최종 체크섬을 저장했다.

SD 카드에 실제로 기록할 때는 먼저 `lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS`로
**기록할 카드의 `/dev/...` 전체 장치명**을 직접 확인한다. 아래의 `/dev/검증한장치`는
반드시 해당 카드로 바꿔야 한다. 잘못 지정하면 그 장치의 기존 데이터가 덮어써진다.

```bash
sudo dd if=/var/home/bazzite/ljh/output/pi4-hdmi/images/sdcard.img \
  of=/dev/검증한장치 bs=4M status=progress conv=fsync
sync
```

이번 개발 과정에서는 실제 SD 카드에 기록하지 않았다. Raspberry Pi 4 실물/모니터/
실제 USB 디스크가 현재 Codex 실행 환경에 노출되지 않아 그 시험은 진행하지 못했다.
처음 켤 때 micro-HDMI 모니터를 연결하고, USB 외장 하드를 먼저 연결한다. 카메라
SD는 별도 USB 리더로 연결한다. 자동 백업 대상 하드는 현재 ext4가 필요하며
자동 포맷하지 않는다.

외장 하드의 현재 파일시스템, Pi4 RAM 모델, micro-HDMI 모니터 모델 및 실제
자동 백업 결과는 확인 전이다. 5초 준비 목표도 실물 측정 전에는 달성으로 보고하지 않는다.
GitHub에는 업로드하지 않았다.
