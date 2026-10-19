# V2 INA/GPIO 테스트 요약

|ID|항목|결과|
|---:|---|---|
|1|GPIO 40핀 매핑|PASS · SIMULATION TESTED|
|2|BCM-물리 핀 일치|PASS · SIMULATION TESTED|
|3|GPIO 중복 할당|PASS · SIMULATION TESTED|
|4|I²C 핀 설정|PASS · STATIC TESTED|
|5|INA226 단위|PASS · SIMULATION TESTED|
|6|INA231 단위|PASS · SIMULATION TESTED|
|7|가상 I²C 통신|PASS · SIMULATION TESTED|
|8|센서 분리|PASS · SIMULATION TESTED|
|9|비정상 전압/전류|PASS · SIMULATION TESTED|
|10|11개 전압 구간|PASS · SIMULATION TESTED|
|11|UI 1초 갱신|PASS · HOST TESTED|
|12|REAL/SIMULATION 구분|PASS · SIMULATION TESTED|
|13|저전압 보호|PASS · HOST TESTED|
|14|기존 백업 회귀|PASS · HOST TESTED|
|15|Pi 이미지 생성|PASS · STATIC TESTED|
|16|드라이버/설정 포함|PASS · STATIC TESTED|
|17|부팅 서비스 정적 포함|PASS · STATIC TESTED|
|18|QEMU virt 동작|PASS · QEMU virt|
|19|실제 Pi 부팅|NOT TESTED · HARDWARE NOT TESTED|
|20|실제 INA 측정|NOT TESTED · HARDWARE NOT TESTED|

QEMU 별도 사례: T01:PASS, T02:PASS, T03:PASS, T04:PASS, T05:PASS, T06:PASS, T07:PASS, T08:PASS, T09:PASS, T10:PASS, T11:PASS, T12:BLOCKED.

|사례|실행 내용|결과|
|---|---|---|
|T01|정상 복사·SHA-256|PASS|
|T02|동일 파일 재백업|PASS|
|T03|용량 부족|PASS|
|T04|복사 중 대상 분리|PASS|
|T05|복사 중 원본 분리|PASS|
|T06|VM 강제 종료·재시작 복구|PASS|
|T07|복사된 XML 변조 후 명시적 재검증|PASS|
|T08|읽기 전용 대상|PASS|
|T09|잘못된 대상 파일시스템|PASS|
|T10|빈 원본 SD|PASS|
|T11|한글·특수문자 파일명|PASS|
|T12|수동 포맷|BLOCKED|

T01~T11은 각 사례의 새 가상 USB/SD 이미지를 사용했고, 원본 가상 SD 이미지 SHA-256이 그대로임을 확인했습니다. T12는 수동 포맷 기능이 아직 없어 실행하지 않았으며 실제 디스크 포맷도 하지 않았습니다. 게스트 로그와 `results.json`은 `tests/v2-integration/runs/20261019-113452`, `tests/v2-integration/runs/20261019-114320`, `tests/v2-integration/runs/20261019-114652`에 있습니다.
실물 부팅, 센서, DSI, 배터리 테스트는 수행하지 않았습니다. 샌드박스 소켓 오류로 차단된 첫 QEMU 시도는 `tests/v2-ina/logs/qemu-full.log`에, 전원 차단으로 중단된 실행은 `qemu-full-real.log`에 따로 남겼습니다.
