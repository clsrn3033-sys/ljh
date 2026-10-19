# V2 CPU 온도·배터리 표시 업데이트 (2026-10-19)

## 구현

- CPU 온도는 Raspberry Pi의 `/sys/class/thermal/thermal_zone0/temp`를 우선 읽습니다. 해당 파일이 없는 Linux 호스트에서는 `k10temp`, `coretemp`, `cpu_thermal`, `soc_thermal` hwmon 장치만 검색합니다. GPU 온도를 CPU 온도로 표시하지 않습니다.
- 실측 배터리 센서가 없을 때 7.40V, 0.50A, 3.70W를 **표시 전용 가상 INA226**에서 가져와 `SIMULATION · 실측 없음`으로 표시합니다. 실제 센서가 연결되면 실측값을 우선합니다.
- 배터리 정격 3000mAh, 6.3V=0%, 8.4V=100%를 적용했습니다. 7.40V는 약 52%입니다. 이는 **전압 직선 환산 추정치**이며 방전 곡선·전류 적산으로 검증한 실제 SOC가 아닙니다. 부하와 온도에 따라 오차가 날 수 있습니다.
- 가상 수치는 실제 `Controls.reading`에 넣지 않습니다. 저전압 보호가 설정된 경우 실측 센서가 없거나 측정값이 오래되면 백업 시작을 막습니다. 실물 BMS·션트·전원 경로가 아직 미확인이라 배포 이미지의 6.4V 보호 임계값은 여전히 비활성입니다.

## 실행한 검사

|검사|실제 결과|
|---|---|
|BC250 CPU 온도|`k10temp`에서 50.25°C 실측 (`telemetry-preview/cpu-sensor-host.log`). 호스트 미리보기 화면은 생성 당시 약 51°C 표시|
|호스트 Python 회귀|`python3 -m unittest discover -s tests -q` — 135개 PASS|
|화면 캡처|[메인](telemetry-preview/main.png), [설정](telemetry-preview/settings.png): 전압, 약 52%, SIMULATION, 3000mAh 정격 표시|
|QEMU ARM64 virt 새 이미지|T01 PASS, 게스트 서비스 자동 실행, 파일 10개 실제 복사·검증, `SAFE_TO_REMOVE`. 부팅 7.58초|
|QEMU 배터리 상태|실측 `sensor_source=N/A`, 표시 전용 `display_battery_source=SIMULATION`, 7.4V. 게스트 [화면](../../tests/v2-integration/runs/20261019-130835/screenshots/T01-guest-safe-to-remove.png)|
|QEMU CPU 온도|N/A — QEMU `virt`에 Raspberry Pi CPU 온도 센서가 없음|
|실제 Raspberry Pi 4B CPU·INA 측정|**HARDWARE NOT TESTED**|
|수동 SD 포맷|**BLOCKED** — 기존 V2에 미구현, 포맷 명령 실행 안 함|

새 Raspberry Pi IMG: `/var/home/bazzite/ljh/output/pi4-v2-telemetry-v4-20261019/images/sdcard.img` (311,427,072 bytes), SHA-256 `678d2b4753099f0c95e87375f7ce04305fd4beae220cf49504112b28ab9cef02`.

전송용 zstd: `/var/home/bazzite/ljh/output/pi4-v2-telemetry-v4-20261019/images/sdcard.img.zst` (40,167,503 bytes), SHA-256 `4a8c6c757fa2114e3b4d3c910633d6d5f4db0aa68801a66f7ef0b10b3c47eeb8`. 압축 해제 결과의 SHA-256이 IMG와 일치합니다.

게스트 증거는 `tests/v2-integration/runs/20261019-130835/results.json`과 해당 `logs/`에 있습니다. 기존 V1 및 이전 이미지 출력은 보존했습니다. GPIO 전원 차단, RTC, GPS는 추가하지 않았습니다.
