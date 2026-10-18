# Pi4B 실제 하드웨어 식별 · 2026-10-18 추가 조사

후속 업데이트: 사용자 원본 JPEG가 제공되어 로고 mask 추출·부팅 화면 적용을 완료했다. 아래의 원본 파일 필요/fallback 내용은 첨부 전 조사 기록이다. 최신 적용 상태와 하드웨어 변경 설계는 [PI4B_HARDWARE_REV_A.md](PI4B_HARDWARE_REV_A.md)를 참고한다.

## 현재 확인 수준

- LCD: 사용자 판매 설명상 5인치 DSI 800×480 약60Hz 정전식. 제조사/제품/PCB revision/패널·터치 칩 이름은 아직 없다. 이 정보만으로 특정 overlay나 드라이버를 선택하지 않았다.
- INA226: IC/주소 범위만 확인. 실제 션트저항과 정격은 소프트웨어 IC ID나 주소에서 알 수 없다. `R010`은 통상0.010Ω, `R100`은0.100Ω 표기지만 반드시 실물/해당 모듈 도면으로 확인한다. 정격전력은 저항 표기만으로 확정하지 않는다.
- 배터리: 사용자가 추가로 **8.4V**를 알려줬다. 앞서 제공한 2S·4.2V/cell 충전 모듈 설명과 일치하는 완충 전압 정보다. 실제 셀 모델/용량/방전한계와 별도 BMS 사양은 아니다. 저전압 경고/차단 임계값을8.4V로 설정하지 않았다.
- 충전 모듈: 앞서 제공한 보라색2S/3S boost charger, 기본2S,100K B4100 NTC,2S balancing 사양을 유지한다. 충전 회로 보호 목록을 BMS의 방전 보호로 대체하지 않는다.

현재 실행 환경은 클라우드 x86_64이며 Pi4B가 연결돼 있지 않다. `docs/logs/cloud-hardware-identification.json`이 model=null/is_pi4b=false로 이를 기록한다. 호스트 장치를 Pi4 실측 결과로 보고하지 않는다.

## 실물에서 수집하는 방법

실제 Raspberry Pi 4B에서 다음 명령을 실행한다(부팅 가능한 기존 Raspberry Pi OS에서도 가능).

```sh
python3 scripts/pi4-hardware-report.py --output hardware-report.json
```

도구는 Pi 모델, 이미 커널에 바인딩된 I²C 장치/driver, DRM 연결 상태/modes, evdev 이름, backlight 경로를 읽는다. mount·디스크 쓰기·I²C 스캔/레지스터 쓰기·드라이버 강제 바인딩·GPIO 조작·전원 종료는 하지 않는다. 보고서 파일만 지정 위치에 쓴다. Pi4B가 아니면 수집을 중단하고 비대상임을 기록한다.

보고서에 기기가 안 나오는 것은 물리적으로 없다는 확정이 아니라 현재 커널/DT에 등록되지 않았을 수도 있다. 션트·배터리·BMS의 전기적 정격은 이 도구로 측정할 수 없다.

남은 식별 자료: LCD 구매 링크/뒷면 모델·PCB revision, INA226 션트 인쇄/모듈 사양, 배터리 셀 모델/용량 및 BMS 모델·차단전압·정격전류.

## 로고 오류 조사와 수정

기존 boot 브랜치 Git 이력을 확보했으나 해당 파일 버전은 하나뿐이며 별도 원본 이미지 파일은 없었다. 원본 LOGO_MASK는1539자이고, 증분 복호화는1080자 부근에서 invalid distance 오류, 전체 Base85는1250 부근에서 overflow다.

첫 오류 전후를 포함해 단일 문자 삽입으로 완전한 zlib checksum/정확한10824byte mask 복원 가능성을 검사했으나 후보0개였다. 첫1250자 구간의 단일 문자 치환 검사도 유효 prefix 후보0개였다. 원형을 보장하지 못하는 복원 이미지를 채택하지 않았다. 조사 스크립트/결과는 artifacts/logo-recovery에 있다. 손상 전 전체 소스는 /workspace/1/work/baselines/ljh-boot.tar로 보존된다.

수정한 로더 `mebs/logo_asset.py`는 다음 순서로 처리한다.

1. 명시적인 `MEBS_LOGO=/절대경로/logo.png` 또는 `/etc/mebs/logo.png` 파일이 있으면 검증 후 사용.
2. PNG가 없거나 잘못되면 기존 embedded mask를 체크섬/길이/EOF 검증.
3. 손상이면 원래 main의 MEBS 텍스트 식별자를 임시 로고로 표시. 부팅 화면에 `TEXT LOGO FALLBACK / original asset pending`를 명시. live 메인에도 임시 로고 상태 안내.

원본 LOGO_MASK 문자열은 수정하지 않았다. 정상 원본 PNG가 제공되면 새 임의 로고로 재디자인하지 않고 주어진 모양의 비율을 유지해 표시한다. PNG는 투명 배경+로고 alpha 또는 흰 로고/검정 배경 mask 형식, 단일 정지 PNG≤2MiB/4MP다. 밝은 불투명 배경에 어두운 글자는 mask 형식이 아니므로 그대로 넣지 않는다. 설정 후 프로세스를 재시작하면 적용된다. PNG나 원본 마스크가 잘못돼도 UI가 예외로 중단되지 않는다.

기존 boot 레이아웃/제작자 표기/게이지/페이드는 유지했다. 원래 승인 로고의 픽셀 복원은 여전히 미완료이며 정상 원본 파일이 필요하다. `artifacts/boot-safe/boot-demo.gif`와 progress/ready PNG는 **임시 텍스트 로고·모의 준비 단계**를 실제 렌더러로 생성한 것이며 실제 부팅 성공/5초 목표 달성 근거가 아니다.

자동 테스트: 기존104+새6=110개 통과. 실제 손상 데이터 fallback, 정상 compressed mask, 잘못된 길이/후행 bytes 거부, 외부 PNG alpha/aspect, 잘못된 PNG 처리, 호스트/가상 Pi sysfs 식별을 시험했다. 실제 DSI/터치/센서/배터리/BMS 전기 검증은 미실시. 이미지 빌드의 다운로드403 차단은 별개로 아직 해결되지 않았다.
