# MEBS Pi4 DSI 개발본 인계

이 패키지는 소스·모의 화면·테스트 로그입니다. 부팅 이미지가 아닙니다.
먼저 docs/PI4_DSI_REPORT.md와 docs/logs/pi4-dsi-validation.json을 읽으세요.

현재 위치: /workspace/1/work/ljh-pi4-dsi
원본 보존본: /workspace/1/work/baselines
기존 /workspace/ljh 및 /workspace/1/original-source·releases는 수정하지 마세요.

다른 컴퓨터에서는 이 소스 폴더에서:

```sh
python3 scripts/host-tools.py # Debian13 x86_64, APT 서명 검증, 로컬 추출
python3 -m venv .venv
.venv/bin/python -m pip install Pillow==12.3.0
export MEBS_FONT="$PWD/.local-build/sysroot/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m mebs.runtime800 --mock-preview artifacts/ui800
mkdir -p vendor
git clone --depth 1 --branch 2026.08 https://github.com/buildroot/buildroot.git vendor/buildroot-2026.08
git -C vendor/buildroot-2026.08 rev-parse HEAD
# 기대 커밋: 813cbac680a73092e1ebb86da72972c44573145c
scripts/pi4-dsi-image.sh
```

이 환경에서는 pkgconf 다운로드가 프록시403으로 막혔습니다. 다운로드 도메인 목록은 docs/logs/network-domains.txt입니다.
환경 설정 초안의 설치/시작/네트워크 변경은 저장됐지만 requires_publish=true입니다.
설정에서 초안을 게시한 후 실제 빌드 명령을 다시 실행하고 결과를 검증해야 합니다.
패널 모델·터치 컨트롤러·션트저항·BMS는 미확정이며 포맷은 비활성입니다.
사용자 최신 결정: 수정금지.txt/.text 표식 파일로 장치를 구분하지 않습니다. 첫 연결 USB=백업 대상, STORAGE READY 확인 후 두 번째 USB=원본 SD입니다. 동시 연결/모호 상태에서는 모두 분리 후 순서대로 재연결합니다. 표식 파일을 요구·생성·삭제하지 않습니다.
로고 해독 오류는 안전한 임시 텍스트 fallback/외부 PNG 로더로 처리했습니다. 원본 로고 자체의 복원은 미완료입니다. docs/HARDWARE_IDENTIFICATION.md를 참고하세요. 최신 테스트는110개 통과입니다. 사용자8.4V는 완충 전압 정보이며 BMS/션트 사양은 아닙니다.
실제 하드웨어/전원/GPIO/원본 디스크에 자동 테스트하지 마세요. GitHub push/공개 게시하지 않았습니다.

## 최신 첨부·하드웨어 변경 설계

사용자1000065842.jpg 원본을 mebs/assets에 바이트 보존했고, 추출한 실제 MEBS mask로 부팅 화면을 연결했습니다. 임시 텍스트 fallback이 아닌 제공 로고가 기본입니다. scripts/prepare-logo.py와 logo-provenance.json에 출처/변환/해시가 있습니다. 원래 손상 embedded문자열은 그대로 보존했습니다. 최신 tests118개 통과입니다. docs/PI4B_HARDWARE_REV_A.md와 hardware/mebs-pi4b-revA.json·wiring-pi4b.csv를 읽으세요. 패널/터치 모델·션트·BMS·5V 강압기·load-sharing은 여전히 미확정입니다. 8.4V는2S 완충 정보이며 Pi에 직접 연결하지 않습니다. actual hardware.json은 미확정 항목을false/null로 둡니다.

최신 제작자 정정: Produced by 이정헌. 새800×480 메인/설정은 검정·청록색 테마. scripts/preview-journey.py로 부팅→메뉴13개 장면의모의프리뷰를 생성한다. docs/BOOT_MENU_PREVIEW.md와 artifacts/boot-menu-preview를 먼저 참고한다.
