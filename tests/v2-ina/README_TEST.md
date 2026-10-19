# MEBS V2 INA/GPIO 테스트 재실행

이 테스트는 저장소 내 임시 파일과 새 가상 디스크 이미지만 사용합니다. 실제 `/dev/sd*` 또는 microSD는 열지 않습니다. 실물 센서와 전원 회로 검증은 별도 단계입니다.

```bash
python3 -m unittest discover -s tests -p 'test_v2_ina_gpio.py' -v
python3 -m unittest discover -s tests -q
python3 tests/v2-ina/generate_reports.py
python3 tests/v2-ina/build_report.py
```

Pi 이미지 재조립은 기존에 BC250에서 Buildroot로 빌드된 이미지를 기준으로 새 출력 경로를 지정합니다. `build_fixed_image.py`는 기존 출력 경로가 있으면 거부하므로 이름을 바꾸십시오.

```bash
python3 tests/v2-integration/build_fixed_image.py output/pi4-v2-recovery-v4-20261019/images output/pi4-v2-ina-next/images
python3 tests/v2-integration/build_qemu_image.py output/pi4-v2-ina-next/images output/pi4-v2-ina-next-qemu/qemu-virt.img
python3 tests/v2-integration/run.py --images output/pi4-v2-ina-next/images --prepared-os output/pi4-v2-ina-next-qemu/qemu-virt.img --cases T01,T02,T03,T04,T05,T06,T07,T08,T09,T10,T11
```

QEMU `virt`는 Pi 4B의 GPIO·I²C·DSI 회로를 에뮬레이션하지 않습니다. 실제 보드 부팅과 실물 센서 측정은 `docs/v2-ina/V2_HARDWARE_CHECKLIST.md`에 남겨 둡니다. 샌드박스 환경에서는 QEMU의 로컬 QMP UNIX 소켓 생성이 막힐 수 있으며, 이 경우 제한이 없는 사용자 세션에서 실행해야 합니다.
