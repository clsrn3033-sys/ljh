# V2 INA/GPIO 변경 내역

- `mebs/ina.py`: INA226 ID 검사, INA231 명시적 모델 확인, 레지스터 측정·계산·보정, 가상 레지스터 버스.
- `mebs/gpio_virtual.py`: Pi4B 40핀 매핑, 설계 할당 검증, 가상 I²C 주소/충돌 검사.
- `mebs/sensors.py`, `mebs/hardware_profile.py`: 공통 측정 구조, 모델·전압/션트/보호 활성화 검증.
- `mebs/runtime800.py`, `mebs/controls.py`, `mebs/ui800.py`: 1초 텔레메트리, REAL/SIMULATION 표시, N/A, V/A/W, 저전압 및 stale 측정 중단 경로.
- `buildroot/board/mebs-pi4-dsi/overlay/etc/mebs/hardware.json`: 기본 REAL + 센서 비활성 및 설계 정보.
- `tests/test_v2_ina_gpio.py`, `tests/test_controls800.py`: 레지스터·핀맵·배터리 보호·실제 임시 파일 복사 회귀.
- `tests/v2-integration/build_fixed_image.py`, `tests/v2-ina/*`: 새 Pi 이미지에 파일 통합, 증거 기반 자동 보고.
- 기존 V1 디렉터리, 기존 빌드 이미지, UI 로고 파일은 수정하지 않았습니다. RTC/GPS 기능도 추가하지 않았습니다.
