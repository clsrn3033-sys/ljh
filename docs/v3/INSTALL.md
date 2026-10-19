# MEBS V3 이미지 기록 및 Raspberry Pi 4B 확인 절차

이 문서는 현 단계 이미지의 **실기기 검증 절차**다. DSI 패널·터치 컨트롤러 모델은 아직 확인되지 않았고, `config.txt`가 특정 패널 오버레이를 강제로 선택하지 않는다. 따라서 ARM64 Buildroot 이미지의 로컬 빌드 성공을 DSI 화면·터치·실물 USB 백업 성공으로 해석하지 않는다.

1. 저장소의 [V3 시험 보고서](TEST_REPORT.md)에서 이미지 경로·SHA-256·현재 실패 항목을 먼저 확인한다. 새 microSD 카드와 안정적인 5V 전원, Raspberry Pi 4B, 가능하면 micro-HDMI 모니터와 UART 로그 수집 장치를 준비한다. 기존 V2 카드/사용자 데이터는 보존한다.
2. Linux PC에서 `lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS`로 **새 카드 전체 장치**를 확인한다. 카드의 자동 마운트 파티션을 해제한 뒤 아래 예시의 `/dev/sdX`를 정확한 카드 장치로 바꿔 기록한다. 이 명령은 선택한 카드의 내용을 덮어쓴다. Codex는 호스트의 실제 저장장치에 이 명령을 실행하지 않았다.

   ```bash
   sha256sum output/pi4-v3-atomic-20261019/MABS_V3_RPi4.img
   sudo dd if=output/pi4-v3-atomic-20261019/MABS_V3_RPi4.img of=/dev/sdX bs=4M status=progress conv=fsync
   sync
   ```

3. Pi4에 카드를 꽂고 **USB 백업 대상/원본은 처음에 연결하지 않은 상태**에서 전원을 넣는다. 빨간 PWR·초록 ACT LED, micro-HDMI 출력, UART 콘솔을 각각 관찰한다. HDMI 화면이 없으면 바로 EEPROM 손상으로 단정하지 말고 전원/카드 기록/부트 파티션/커널 로그를 구분한다. 부트로더 EEPROM을 이 절차에서 수정하지 않는다.
4. `BACKUP READY`와 자동 서비스 상태를 확인한다. 실물 DSI 패널의 모델·케이블·터치 컨트롤러를 확인하기 전에는 화면/터치 성공 여부를 미검증으로 남긴다. 필요하면 `config.txt`와 `/etc/mebs/hardware.json`의 패널·터치 경로를 해당 제품의 검증된 사양에 맞춰 **새 이미지 사본**에서 설정한다.
5. 데이터가 없어도 되는 ext4 외장 저장장치를 첫 USB로, 별도의 **읽기 전용 검증용** 카메라 SD 리더를 두 번째 USB로 연결한다. 역할이 모호하면 둘 다 제거 후 순서대로 다시 연결한다. 실제 촬영 원본을 첫 실험에 사용하지 않는다. 백업의 파일 수/폴더/원본·복사본 SHA-256과 기존 외장 파일 보존을 확인한다. V3 탐색기 작업은 백업·검증 후에만 시도한다.
6. 화면이 없더라도 headless 백업 서비스가 돌아가는지 UART의 `/run/mebs/status.json`과 `/var/lib/mebs/events.jsonl`을 확인한다. 전압 센서 미설정 값은 `N/A`이며, 화면의 SIMULATION 표시는 실측값이 아니다. 배터리 전원 차단 기능은 없다.

실물 시험 기록에는 Pi4 보드 리비전, 전원 공급기/부하 전압, microSD 모델, DSI 패널/터치 모델, USB 저장장치 모델·파일시스템, 부팅 로그, 화면 사진, 최종 이미지 SHA-256과 사용한 테스트 원본의 해시를 함께 남긴다. GPIO 40핀 설계 할당은 [GPIO_PINOUT.md](GPIO_PINOUT.md)를 따른다.
