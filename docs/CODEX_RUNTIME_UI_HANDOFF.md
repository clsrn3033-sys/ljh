# MEBS 실행 UI 개발 · Codex 인수인계

## 범위
대상: Raspberry Pi 4 / Buildroot, 향후 Orange Pi 3B V1.1 이식.
브랜치: `feature/mebs-runtime-ui` (기반: `feature/mebs-boot-animation`).
기존 `main`, 백업 엔진, SD 포맷 로직은 수정하지 않음.

## 현재 납품
- `mebs/runtime_ui.py`: 기존 서비스가 방출하는 상태 사전으로 1280×720 PNG/Pillow 프레임 출력.
- `tests/test_runtime_ui.py`: 상태별 렌더, 진행률, PNG, 원본 상태 불변 및 안전분리 상태 구분 회귀 테스트.
- 새로운 디자인: 검정 배경, 하늘색 강조선, 외장 저장장치 / SD카드 상태, 복사 진행률, SHA-256 상태, 안전 분리 대기와 오류 표시.
- 별도 채팅 미리보기 GIF 및 PNG는 **시뮬레이션**. 현재 GitHub 소스의 실기 렌더 출력과 픽셀 단위 동일하다는 보장은 없으며 재생성 검증 필요.

## Codex 검증 · 연동 요청
1. 로컬 Bazzite 작업 트리 변경사항을 `git status -sb`로 먼저 확인. `git pull`, `git reset`, `git checkout`으로 미커밋 작업을 잃지 말 것.
2. 원격 브랜치 `feature/mebs-runtime-ui`와 로컬 작업을 비교해 충돌 없는 작업 트리에서 검증할 것.
3. `MEBS_FONT`이 설정된 호스트에서 `python3 -m unittest discover -s tests -v` 수행. 의존성 및 코드 오류가 나면 원인을 기록하고 최소 수정.
4. 현재 `mebs/appliance.py`의 `from .display import render` 교체는 **아직 수행하지 않음**. 유효한 이벤트 입력 확인 후 런타임 선택 옵션 등 안전한 방법으로 연결할 것.
5. 프레임버퍼 `Framebuffer.show`의 자동 스케일·이미지 할당·CPU·RAM 사용량을 장시간 계측. 실제 USB와 Pi4 micro-HDMI/KMS 화면까지 검증. 표시 실패 시 백업 동작을 오인하지 않도록 하되 백업 처리 정책은 유지.
6. 복사 데이터 100%가 최종 검증 완료나 안전 분리를 의미하지 않도록 분리하고, `SAFE_TO_REMOVE` + 참인 `safe_to_remove`만 안전 분리 상태로 표시.
7. `READY`는 시스템 부팅 완료 상태이지 USB 장치가 이미 연결됐다는 뜻이 아님. 첫 번째 외장 저장장치, 두 번째 SD카드 순서를 그대로 사용.
8. 원본 포맷·삭제, 기존 백업 엔진 동작, 마운트·분리 안전장치, 원본 데이터는 수정하지 말 것.
9. Buildroot SD 이미지 재생성, QEMU 상태 검증 및 실제 Pi4 실기 검증은 미완료로 표기하고 결과·로그·이미지 경로를 보고할 것.

## 상태 구분
`READY → WAITING_SOURCE → CONNECTED → COPYING → VERIFYING → FINAL_CHECK → UNMOUNTING → SAFE_TO_REMOVE`.
장치 식별에 따른 `MOUNTING` 및 `SCANNING`도 지원.
`ERROR / CANCELLED / AMBIGUOUS`에서는 원본 보존 경고.

## 실행 예
```bash
MEBS_FONT=/usr/share/fonts/mebs/NotoSansCJK-Regular.ttc python3 -m unittest tests.test_runtime_ui -v
```
이미지와 실제 저장장치의 연결 및 하드웨어 결과는 Codex 재검증 전까지 승인하지 말 것.
