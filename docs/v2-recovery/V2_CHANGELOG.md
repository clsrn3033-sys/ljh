# MEBS V2 이번 수정

- `mebs/backup.py`: 검증된 완성 job과 동일한 파일·폴더·모드·mtime·확장 속성만
  다시 사용할 수 있게 했다. 복사본 손상·원본 변경 시 새 백업으로 처리한다.
  빈 카드 전용 오류 및 새 복사 시 실제 필요/잔여 바이트 경고를 추가했다.
- `mebs/appliance.py`, `mebs/runtime800.py`: 첫 USB 외장하드의 미완료 job을
  읽기 전용 검사해 `RECOVERY_REQUIRED`로 표시한다. 원본 재연결 시 새 작업을 실행하며
  부분 작업은 보존한다. 강제 종료 직후 pending inode의 `is_dir()`가 실패할 수 있어
  이름만 검사하도록 고쳤다. 기존 안전 분리·원본 읽기 전용·장치 식별 경계를 유지했다.
- `mebs/display.py`, `mebs/controls.py`: 복구 경고 및 검증된 재사용 작업의
  완료 상태가 실제 UI에 표시되도록 했다.
- `mebs/sensors.py`, `mebs/ui800.py`: 실제 `/proc/meminfo` RAM 사용률과
  센서 미연결 시 N/A 표시를 추가했다. 승인된 MEBS 로고·제작자 문구·색상은 유지했다.
- `tests/test_backup.py`, `tests/test_controls800.py`: 새 요구에 맞는 중복·빈 카드·
  중단 경고·메모리·공간 부족 회귀 시험 추가/갱신.
- `tests/v2-integration/`: Pi 이미지 재조립 안전성 수정, 별도 QEMU 이미지 생성,
  실제 가상 FAT32/ext4·QMP 장애 재시험 및 20회 부팅 측정 도구 추가.

V1 폴더·원본 이미지 삭제/덮어쓰기, EEPROM 변경, 실제 SD 포맷, GPIO 물리 전원 차단은 수행하지 않았다.
