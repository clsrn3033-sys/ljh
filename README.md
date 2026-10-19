> **현재 개발: Raspberry Pi 4B / MEBS V3**
>
> [V3 개발 및 검증 기록](docs/v3/README.md)을 먼저 읽으세요. V2는 `feature/mebs-v2-pi4b-800x480-20261018`, V1은 `preserve/mebs-v1-github-20261018` 브랜치에 남겨 두었습니다. V3 브랜치에서만 구 `ver 1/` 자료를 삭제했습니다.
> 확정 화면은 800×480 검정·청록색이며, 제작자 표기는 **Produced by 이정헌**입니다. 아래 오래된 단계별 기록보다 V3 기록과 실제 테스트 결과를 우선하세요.

# MEBS Auto Backup System

현재 대상은 Raspberry Pi 4B용 Buildroot 독립형 자동 백업 장치이며,
개발 호스트는 BC250/Bazzite이다. Orange Pi 관련 내용은 이전 구상 기록이다.

GitHub: https://github.com/clsrn3033-sys/ljh

원격 조회 당시 파일·커밋·브랜치가 없는 저장소임을 확인한 뒤 사용자 지시에 따라
새 구현을 시작했다. 호스트 DNS 제한으로 clone을 할 수 없어 동일한 원격 주소를
등록한 로컬 Git 저장소를 초기화했다. 작업 브랜치는 `work/mebs-foundation`이다.
GitHub 원격에는 아직 파일이나 커밋을 업로드하지 않았다.

## 현재 단계

**Raspberry Pi 4용 Buildroot SD 이미지가 로컬에서 생성됐다.**
[sdcard.img](output/pi4-hdmi/images/sdcard.img)는 289MiB이며 micro-HDMI 화면과
전용 자동 백업 서비스를 포함한다. Pi4 실물 부팅과 모니터 출력은 아직 검증 전이다.
[3차 작업 기록](docs/phase3-results.md)에 빌드·QEMU 가상 USB 검증 결과와 SD 기록
방법을 남겼다. 아래 1·2차 설명은 개발 단계별 기록이다.

Pi4 이미지를 이 컴퓨터에서 다시 만들려면:

```bash
cd /var/home/bazzite/ljh
bash scripts/pi4-image.sh vendor/buildroot-2026.08 output/pi4-hdmi
bash scripts/inspect-pi4-image.sh output/pi4-hdmi/images
```

첫 명령은 이 프로젝트의 Buildroot 소스·홈 기반 `patch` 도구와 현재 설치된
Noto Sans CJK 글꼴을 사용한다. 원시 이미지는 `output/pi4-hdmi/images/sdcard.img`다.
SD 카드 기록은 [3차 결과](docs/phase3-results.md)의 장치 확인 절차를 따른다.

구현:

- 명시적으로 선택한 원본·대상 디렉터리 백업. 원본 파일을 수정·삭제하는 코드 없음.
- 폴더 구조, 빈 폴더, 한글 파일명, XML 및 모든 일반 파일의 내용 보존.
- 수정 시각(ns), 일반 POSIX 권한, 읽을 수 있는 확장 속성 복사. 보존 불가 시 실패.
- 복사 중 SHA-256 계산 후 대상 파일을 다시 읽어서 비교. 별도 `verify` 명령 제공.
- JSON 진행률·상태·실패 로그, 취소 및 SIGTERM 처리, 대상 잠금.
- 숨겨진 부분 작업에 복사·검증·fsync 후 덮어쓰기 없는 원자적 이름 변경으로 완료 게시.
- 기존 대상 파일과 이전 백업을 덮어쓰지 않는 작업별 디렉터리.
- `devices`/`watch`: 읽기 전용 USB 디스크 조회와 보수적인 연결 순서 판단.
- 실제 복사·SHA-256 검증 이벤트에 연결된 준비/진행/완료/오류 화면.
- 정상·대상 손상·취소 시험을 직접 실행하고 결과를 재생하는 오프라인 미리보기.
- 데스크톱 없이 Linux framebuffer에 같은 화면을 출력하는 `display-demo` 시험 명령.

남은 구현 또는 검증:

- 자동 USB 마운트·백업·안전 분리 코드는 Pi4 이미지에 포함됐고 QEMU ARM 게스트의
  파일 기반 USB 장치로 검증했다. 실제 USB와 Pi4 보드에서는 아직 미검증이다.
- 실제 제공 로고를 적용한 부팅 화면, Orange Pi 이미지, 터치 LCD 입력, GPIO,
  사용자 확인 포맷은 미구현이다. Pi4 이미지는 생성됐으며 QEMU `virt`로 부팅했다.
- Pi4 실물 부팅과 micro-HDMI 출력, 5초 준비 목표의 실측.
- NTFS/exFAT/FAT 호환성, 실제 USB 오류·전원 상실·하드웨어 복구 검증.
- 실제 포터블 모니터 출력, framebuffer의 ARM 실물 동작.

## 화면 바로 보기

이 컴퓨터에서 생성한 [미리보기](preview/index.html)를 브라우저로 열면 된다.
서버나 네트워크 연결 없이 정상 백업·손상 감지·중단 과정을 재생할 수 있다.
[화면 GIF](preview/demo.gif)와 [완료 화면 PNG](preview/complete.png)도 생성되어 있다.

```bash
cd /var/home/bazzite/ljh
xdg-open preview/index.html
```

미리보기를 다시 만들려면 `make preview`를 실행한다. 화면 생성에만 Pillow와
한글 폰트가 필요하며 현재 환경에 설치된 것을 사용했다. 백업 엔진은 계속 표준
라이브러리만 사용한다. 화면은 이번에 만든 초안이며 과거 승인 디자인의 복원이 아니다.
`MEBS` 텍스트는 실제 로고 제공 전 임시 표기다.

미리보기는 임시 샘플 파일로 실행한 결과이며 연결된 USB를 제어하지 않는다.
포터블 모니터 시험 방법과 검증 범위는 [2차 결과](docs/phase2-results.md)에 기록했다.

## BC250에서 빌드 및 실행

Python 3.11 이상과 Linux가 필요하다. 백업 엔진은 pip 의존성이 없으며 USB 조회에는
util-linux의 `lsblk`가 필요하다. `.pyz`는 이 컴퓨터의 소스로 만드는 Python 실행
아카이브이며, OS 이미지나 ARM 네이티브 바이너리는 아니다.

```bash
cd /var/home/bazzite/ljh
make test
make build
python3 dist/mebs.pyz ready
make demo
```

`demo`는 임시 폴더에서 샘플 데이터·XML 복사, 검증, 원본 내용 불변을 확인한다.
실제 디스크를 포맷하거나 마운트하지 않는다.

이미 마운트된 디렉터리에 수동 백업하려면:

```bash
python3 dist/mebs.pyz backup --source /path/to/source --target /path/to/target
python3 dist/mebs.pyz verify /path/to/target/mebs-backup-JOB_ID
python3 dist/mebs.pyz devices
python3 dist/mebs.pyz watch
```

원본과 대상은 반드시 구분하여 지정한다. 디렉터리 모드는 동일한 파일시스템 내
테스트도 허용하며 실제 USB 장치 역할·마운트 상태를 인증하지 않는다.
`VERIFIED`는 내용 검증·flush 완료를 뜻한다. **안전 분리 완료가 아니므로 마운트
해제 전 USB를 뽑지 않는다.** USB 조회는 원격 감시 세션에서 보이는 장치만 보여 준다.
자동 장치 역할은 최신 사용자 지정에 따라 첫 번째로 구분하여 관측된 USB 디스크가
백업을 저장할 대상 외장 하드, 두 번째가 읽기 전용 원본 SD카드다.
감시 시작 전 연결, 동시 감지, 세 번째 장치, 분리는 `AMBIGUOUS`로 처리하고 전체
분리 관측 후 재시작한다. 아직 이 관찰 결과로 복사를 자동 시작하지 않는다.

## 파일 및 손상 보호 범위

완료 작업: `mebs-backup-<시간>-<UUID>/data/`, `manifest.json`.
부분 작업: `.mebs-pending-<시간>-<UUID>/`.
부분 작업은 자동 삭제·재사용·성공 처리를 하지 않는다. SIGKILL 후에도 남는다.
재시도는 새로운 작업을 만들기 때문에 추가 공간을 사용한다.

심볼릭 링크, FIFO, 장치 파일, 중첩 파일시스템은 조용히 누락시키지 않고 거부한다.
원본 내용/목록/수정 정보가 작업 중 바뀌면 실패한다. 이 검사는 원본 스냅샷을
대체하지 않으므로 제품에서는 원본을 읽기 전용으로 마운트할 계획이다. 현재
원본을 읽을 때 호스트 마운트 정책에 따라 atime은 바뀔 수 있다.

소유자·그룹·하드링크 관계·sparse 배치·setuid/setgid/sticky 비트는 현재 보존하지
않는다. XML은 파싱·수정 없이 원본 바이트를 복사한다. POSIX 메타데이터를 엄격하게
요구하므로 exFAT/FAT 같은 대상은 실패할 수 있다. 지원 정책 확정 전 완화하지 않는다.
manifest의 SHA-256은 서명/악의적 변경 방어 기능이 아니다. 신뢰 가능한 저장장치
환경을 전제로 하며 저장장치가 flush를 정직하게 이행하는지도 실물 검증이 필요하다.
갑작스러운 전원 상실의 무손상 보장은 전원 유지 회로/파일시스템과 함께 검증한다.

## Buildroot 통합

[공식 Buildroot 매뉴얼](https://buildroot.org/downloads/manual/manual.html)의
BR2_EXTERNAL 구조를 사용한다. `buildroot/`는 Buildroot 전체 소스가 아닌 MEBS 외부
패키지 트리다. Buildroot 2026.08의 Python·util-linux 설정 및 QEMU/Pi4 defconfig를
읽어 구성했다. 아래는 **1차 단계 당시**의 QEMU/Pi4 빌드 진입점이다.
최신 Pi4 이미지 빌드와 시험은 앞 절과 3차 결과를 따른다.

네트워크 접근 가능한 일반 터미널에서 Buildroot 소스를 확보한다. 완성된 OS 이미지
또는 외부 크로스 툴체인을 내려받는 대신 이 스크립트는 로컬 툴체인 빌드를 선택한다.
라즈베리파이 부팅에 필요한 벤더 펌웨어는 upstream 보드 설정에서 제공한다.

```bash
bash scripts/check-host.sh
mkdir -p vendor
git clone --branch 2026.08 --depth 1 https://github.com/buildroot/buildroot.git vendor/buildroot
bash scripts/buildroot.sh "$PWD/vendor/buildroot" "$PWD/output/qemu" qemu_x86_64_defconfig
bash scripts/qemu.sh "$PWD/output/qemu"
```

QEMU 스크립트는 TCG를 사용하며 호스트 디스크·네트워크를 연결하지 않고 게스트
루트 디스크 변경은 snapshot으로 버린다. 게스트에서 `mebs ready`, `mebs backup`,
`mebs verify`를 검증한다. TCG 속도로 보드 5초 부팅을 판단하지 않는다.

Pi4 후보 이미지 구성:

```bash
bash scripts/buildroot.sh "$PWD/vendor/buildroot" "$PWD/output/pi4" raspberrypi4_64_defconfig
```

Pi4 최종 이미지는 `scripts/pi4-image.sh`로 만들며 자동 시작 서비스와 읽기 전용
rootfs가 포함된다. 안전한 SD 카드 기록 절차와 실제 검증 범위는
[3차 결과](docs/phase3-results.md)에 있다. Orange Pi 3B V1.1의 검증된 BSP가
확인될 때까지 다른 Orange Pi 모델의 설정을 대용하지 않는다.

Bazzite 호스트 패키지는 설치하지 않았다. 필요한 `patch`는 프로젝트의 홈 기반
빌드 도구로 마련했다. 자세한 요구사항과 결과는
[REQUIREMENTS.md](REQUIREMENTS.md), [DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md),
[1차 결과](docs/test-results.md), [2차 결과](docs/phase2-results.md),
[3차 결과](docs/phase3-results.md)를 참고한다.
