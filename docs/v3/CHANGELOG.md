# V3 변경 내역

- `mebs/explorer_v3.py`, `mebs/ui_explorer_v3.py`, `mebs/ui_explorer_v3_layout.py`: V2 백업 엔진의 USB 역할·마운트 검증을 재사용한 800×480 터치 탐색기. 사진·영상/RAW 정보·가능한 썸네일, 확인 후 작업 영역 복사·이동·삭제, 원본/기존 백업 보호.
- `mebs/controls.py`, `mebs/runtime800.py`, `mebs/ui800.py`: 파일 화면 진입, 백업/종료 동시 작업 차단, 실제 런타임 렌더, 상태 JSON 원자적 게시.
- `buildroot/package/mebs/Config.in`, `mebs.mk`, `scripts/pi4-v3-image.sh`: FFmpeg/FFprobe, JPEG 지원 Pillow를 포함한 ARM64 Buildroot 소스 빌드. V2 출력·기존 이미지를 건드리지 않는 별도 V3 결과물.
- `tests/test_explorer_v3.py`, `tests/v3/`: 파일 보호·코덱 정책·화면·원자적 상태 단위 시험, QEMU 가상 USB 백업과 게스트 UI 캡처, Pi4 이미지 정적 검사, V2/V3 부팅 비교.
- `docs/v3/`: 사용자 제공 기준 JPG의 원본 바이트와 시뮬레이션/게스트 화면, 시험 로그·코덱 정책·GPIO 할당·실물 검증 절차.
- `mebs/performance.py`, `mebs/performance_validate.py`: Pi4 부팅 1.5GHz 상한과 실행 중 cpufreq 제한을 분리. 온도/펌웨어 저전압·스로틀링 감시, 백업 중 기본 모드, 1.8/2.0GHz 실기 검증 게이트. 예비 CPU 부하 시험만으로 증속하지 않음.
- `scripts/pi4-v3-clock-candidate.sh`: 원본 이미지를 보존한 별도 1.8/2.0GHz 미검증 시험 사본 생성. 실제 보드 검증 전 기본 이미지에 고클럭을 포함하지 않음. 상세 결과는 [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md).
- 사용자 요청에 따라 **V3 브랜치에서만** `ver 1/`을 제거. V1 보존 브랜치와 V2 브랜치·이미지에는 적용하지 않음.

현장 Pi4B·DSI·터치·실제 카메라 미디어·배터리 센서는 아직 시험하지 않았다. 상세 판정은 [TEST_REPORT.md](TEST_REPORT.md)에 있다.
