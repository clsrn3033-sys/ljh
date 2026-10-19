# MEBS V3 — Raspberry Pi 4B Buildroot 탐색기

현재 작업 브랜치: `feature/mebs-v3-explorer-20261019`. V2 브랜치 `feature/mebs-v2-pi4b-800x480-20261018`와 V1 보존 브랜치 `preserve/mebs-v1-github-20261018`는 변경하지 않는다. 사용자 요청으로 V3 브랜치에서만 `ver 1/` 자료를 제거했다. 기존 V2 `output/` 이미지는 유지한다.

## 확정된 기준

- Raspberry Pi 4B ARM64, Buildroot 2026.08, 데스크톱/X11 없이 800×480 가로 DSI 터치 UI. 최종 패널 모델 및 실기기 동작은 미검증.
- 검정·청록 MEBS 디자인, `제49기 보도부 이정헌 / Produced by 이정헌` 표기. 사용자 제공 [탐색기 기준 이미지](reference-explorer.jpg)의 SHA-256은 `5cb5ddb2df07752267dd254e0eda60092cf773f5266c69f09087fff8c1a66f67`이다. 기존 부팅 로고 JPEG는 수정하지 않았다.
- 표식 파일 없이 첫 번째로 구분해 관측한 USB가 ext4 백업 대상, 두 번째가 원본 SD다. 동시 연결 등 모호한 순서는 자동 백업을 막는다.
- V2 자동 백업·SHA-256 검증·미완료 작업 복구·원본 읽기 전용 보호를 유지한다. V2에는 수동 SD 포맷이 없었고, V3에서도 자동/수동 포맷을 추가하지 않았다.

## V3 기능과 범위

탐색기는 상단 `파일` 터치로 필요할 때만 열리며, 백업 작업 중에는 열리지 않는다. 탐색 중에는 새 백업 시작과 안전 종료 완료를 잠시 막는다. 닫기/안전 분리 시 동기화와 정상 마운트 해제를 수행한다. 파일 목록·용량·이름/날짜/크기 정렬, 이미지 썸네일, FFprobe 영상 정보, FFmpeg 영상·RAW 한 프레임 썸네일(해독 가능한 형식에 한함)을 지원한다. RAW 미리보기 실패 시 파일 정보만 표시한다. 영상 미리보기는 확인된 H.264 8비트 4:2:0, 최대 1080p의 **30초 무음 소프트웨어 미리보기**로 제한했다. Pi4 하드웨어 가속과 FX3 실제 촬영 파일은 미검증이다.

원본 SD는 읽기 전용이다. 수동 복사는 원본의 일반 파일 한 개를 외장 저장장치의 `MEBS_FILES/`에 SHA-256 검증 후 덮어쓰기 없이 저장한다. 이름이 같으면 중단한다. 이동은 `MEBS_FILES`의 일반 파일을 `MEBS_FILES/Archive`로 보내며, 삭제는 이 사용자 작업 영역의 일반 파일에만 허용된다. 각 변경에는 UI 확인이 필요하다. 기존 `mebs-backup-*` 기록과 원본 SD는 탐색기에서 수정할 수 없다. 폴더 전체 복사, 임의 경로 이동 및 휴지통 복원은 아직 제공하지 않는다.

[800×480 실제 렌더 미리보기](explorer-preview.png)는 가상 디렉터리 데이터로 만든 **SIMULATION** 화면이다. 실제 Pi4 DSI 화면으로 확인한 결과가 아니다.

현재 최종 로컬 기본 이미지: `output/pi4-v3-performance-lock-20261019/MABS_V3_RPi4.img`, SHA-256 `d847f948b632bc973c0c028ce7d5e5db244f8e5edd8c7969ebc29dc695c35287`. 기본 부팅 상한은 1.5GHz다. [성능 모드·실물 검증 안내](PERFORMANCE_REPORT.md)를 참조한다. [QEMU 게스트에서 실행한 UI 캡처](performance-qemu-final/qemu-explorer.png)는 가상 값으로 렌더한 화면이다. Pi4 실물 부팅·DSI 터치는 미검증이다.

## 로컬 실행

```bash
cd /var/home/bazzite/ljh
python3 -m unittest discover -s tests -q
python3 tests/v3/create_preview.py
# 기존 로컬 V2 Buildroot 출력·소스와 사용자 홈 GNU patch 도구 사용
bash scripts/pi4-v3-image.sh  # 새 출력 경로가 필요하면 MEBS_V3_BUILD_OUTPUT 지정
```

빌드 스크립트는 새 출력 경로에 V2 로컬 빌드 출력의 CoW 복사본을 만들고 V3 소스를 재빌드한다. 기본 경로는 `output/pi4-v3-800x480-20261019`이며 이미 결과 파일이 있으면 덮어쓰지 않는다. 기본 이미지 파일명은 `MABS_V3_RPi4.img`다. FFmpeg는 Buildroot가 공식 소스와 SHA-256 검증을 통해 직접 빌드한다. 출력 경로를 바꾸려면 `MEBS_V3_BUILD_OUTPUT`을 사용한다.

```bash
python3 tests/v3/inspect_image.py
python3 tests/v3/qemu_smoke.py --images output/pi4-v3-performance-lock-20261019/images
python3 tests/v3/compare_boot.py --v3 output/pi4-v3-performance-lock-20261019/images
```

QEMU `virt`는 Pi4 보드/DSI/USB 전원/터치를 완전히 에뮬레이션하지 않는다. 위 명령은 가상 USB 이미지 및 ARM64 소프트웨어 시험이다. 상세 결과는 [V3 시험 보고서](TEST_REPORT.md), 코덱 정책은 [코덱 보고서](CODEC_REPORT.md), 실물 설치 준비는 [설치 안내](INSTALL.md)를 참조한다.
