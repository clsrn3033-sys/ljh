# MEBS V2 반복·장애 시나리오 재검증 — 2026-10-19

대상 브랜치: `feature/mebs-v2-pi4b-800x480-20261018`. 기존 V1과 v5 이미지를 보존하고 v6 복사본을 생성했다. 호스트 임시 디렉터리와 QEMU 가상 USB/SD 이미지만 사용했다. 실제 저장장치 포맷·전원 차단은 실행하지 않았다.

| 시나리오 | 결과 | 실제 실행 결과 |
|---|---|---|
| N01 잘못된 외장 디스크→모두 분리→올바른 디스크 재연결 | PASS (수정 전 FAIL) | 원본 2개 파일을 다시 백업·검증했고 이전 `ext4 형식 필요` 오류 문구가 사라짐 |
| N02 복사 중 종료 예약 후 원본 SD 분리 | PASS | 백업은 ERROR, `safe_to_remove=false`, 종료 예약 취소; 원본 파일 보존 |
| N03 복구 시 별도 배터리 경고 | PASS | 오래된 디스크 오류만 제거하고 배터리 경고는 유지 |
| N04 호스트 전원 시나리오 20회 반복 | PASS 20/20 | 매 회 실제 임시 파일 복사·검증과 종료 경계 테스트 실행. [실행 기록](repeat-20.json) |
| N05 QEMU T14: 복사 중 정상 OS 종료→재부팅→원본 재연결 | PASS | 미완료 작업 1개와 `RECOVERY_REQUIRED` 표시, 이후 11개 파일·33,557,739바이트 새 백업 SHA-256 검증 후 `SAFE_TO_REMOVE`; 원본 가상 SD 불변 |
| Raspberry Pi 4B 실기기 전원/DSI/USB/센서 | HARDWARE NOT TESTED | 해당 장비를 연결하지 않음 |

발견한 실제 오류는 [Controls.update](../../../mebs/controls.py)의 오래된 알림 유지였다. `ERROR`에서 정상 상태로 바뀌어도 `notice`가 이전 디스크 오류를 계속 표시했다. 이전 상태의 오류 문구와 현재 알림이 일치할 때만 지우도록 수정했다. 복구 후 표시가 정상인지 호스트 테스트와 QEMU의 [복구 경고 화면](recovery-required.png)→[재시도 성공 화면](retry-safe-to-remove.png)에서 확인했다. 배터리·설정·화면 오류처럼 다른 알림은 유지한다.

호스트 전체 테스트는 **142개 PASS**. QEMU T14는 정상 OS 종료를 시험한 것이며 정전 또는 물리 전원 차단 재현은 아니다. 첫 부팅에서 `READY`까지 약 7.43초, 재부팅까지 약 7.25초가 측정됐다. QEMU `virt` 시간은 Pi 4B 실기기 부팅 시간으로 해석하지 않는다. T14 [결과 로그](qemu-T14-result.log), [호스트 테스트 로그](host-tests.log), [이미지 빌드 로그](image-build.log)를 보존했다.

새 Pi 4B 이미지: `output/pi4-v2-repeat-v6-20261019/images/sdcard.img` (311,427,072바이트), SHA-256 `05fcd3f045b961134f2748583de3dcf0b8ed923aa42c1ae48d97bdce5c48bee4`. 압축본 `sdcard.img.zst` (38,210,547바이트), SHA-256 `82a3121bff86702b891501b54a45041193a9e8dc6ac9a801085e95e0fb2a3138`. `zstd -t`와 해제 스트림의 원본 해시 일치, 3개 파티션, Pi 4B 부팅 파일, 이미지 내부 `controls.py`와 소스의 바이트 일치를 확인했다. [정적 검사 결과](image-validation.json). 이전에 로컬 빌드한 Buildroot 커널/펌웨어를 재사용하고 변경 Python 소스를 별도 이미지에 넣었다. 이번 단계에서 전체 커널을 재빌드하지 않았다.

재실행:

```sh
python3 -m unittest discover -s tests -q
python3 tests/v2-integration/repeat_power_cycle.py --rounds 20 --output docs/v2-ina/repeat-v6/repeat-20.json
python3 tests/v2-integration/run.py \
  --images output/pi4-v2-repeat-v6-20261019/images \
  --prepared-os output/pi4-v2-repeat-v6-qemu-20261019/images/qemu-virt.img \
  --cases T14
```

QEMU에는 로컬 QMP Unix 소켓 생성 권한이 필요하다. 실제 Pi 4B 이미지의 EEPROM 부팅, DSI 화면·터치, 물리 전원, INA 센서 및 5초 부팅 목표는 여전히 미검증이다. 이 결과만으로 실기기 배포 가능이라고 판정하지 않는다.
