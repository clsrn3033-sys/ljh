# V2 INA226/INA231 드라이버 결과 (초기 이미지 기록)

최신 CPU/배터리 화면 및 6.3~8.4V 전압 추정 퍼센트는 `V2_TELEMETRY_UPDATE.md`를 참조하십시오.

- 출발 브랜치: `feature/mebs-v2-pi4b-800x480-20261018`, 출발 커밋 `4fc04cb`.
- 구현: `mebs/ina.py`, `mebs/sensors.py`, `mebs/runtime800.py`, `mebs/hardware_profile.py`.
- 모델 식별: INA226은 0xFE/0xFF의 TI/2260 계열 값을 검사합니다. INA231은 데이터시트에 고유 ID 레지스터가 없어 모듈 모델을 독립적으로 확인하고 `model_confirmed`를 설정해야 합니다. I²C ACK만으로 모델을 확정하지 않습니다.
- 레지스터: shunt 01h(부호 있는 2.5µV/LSB), bus 02h(1.25mV/LSB), calibration 05h(명시적으로 활성화할 때만 기록). 전류는 확인된 션트값을 통한 shunt 전압/저항으로 계산하며 전력은 V×A로 계산합니다. 실물 션트, 극성, 3.3V 풀업 검증 전에는 활성화하지 않습니다.
- 데이터: 전압·전류·전력, UTC와 monotonic 타임스탬프, 모델, `REAL`/`SIMULATION` 출처. 끊김/짧은 읽기/범위 초과/오래된 가상값은 N/A 또는 오류로 처리합니다.
- 이 초기 이미지의 기본값은 REAL 모드, 센서 비활성, N/A였습니다. 최신 화면은 실측 SOC가 아닌 전압 기준 `~%`를 표시합니다.
- 테스트: 집중 센서/GPIO 단위 테스트 **PASS** (7개); 전체 호스트 회귀 **PASS** (132개). 로그 `tests/v2-ina/logs/ina-gpio-tests.log`, `host-tests.log`.
- 실제 INA226/INA231 측정: **HARDWARE NOT TESTED**. 실제 배터리/충전 회로 연결 및 전압 계측 전 사용 불가.

근거: [TI INA226 데이터시트](https://www.ti.com/lit/ds/symlink/ina226.pdf), [TI INA231 데이터시트](https://www.ti.com/lit/ds/symlink/ina231.pdf).
