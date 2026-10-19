# V2 GPIO 가상 테스트

- 1~40 물리 핀, BCM 매핑, 전원/GND 구분, HAT ID 27/28 예약: **PASS** (SIMULATION TESTED).
- 설계 할당 1=3.3V, 3=BCM2/SDA1, 5=BCM3/SCL1, 6=GND. 나머지는 미사용 또는 예약; 중복과 7비트 I²C 주소 충돌을 검사합니다.
- 가상 I²C: 주소 0x40의 명시적 센서 연결, NACK/연결 해제, 재연결. 실제 GPIO 또는 배터리를 제어하지 않습니다.
- 핀 설정: `docs/v2-ina/gpio_pinmap.json`; 전체 표와 배치도 `V2_GPIO_PINOUT.md`.
- 3.3V 모듈의 실제 배선/전기적 특성: **HARDWARE NOT TESTED**.
- 명령: `python3 -m unittest discover -s tests -p 'test_v2_ina_gpio.py' -v`.

근거: [Raspberry Pi GPIO 공식 문서](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html).
