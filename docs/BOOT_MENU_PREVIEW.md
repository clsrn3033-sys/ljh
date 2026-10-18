# 첨부 디자인 기준 부팅 → 메뉴 프리뷰

사용자 최신 정정: **Produced by 이정헌**. 부팅, 메인, 설정 및 CLI 표기를 수정했다. 첨부 원본 JPEG에 있던 이전 이름은 원본 보존을 위해 픽셀을 수정하지 않고, 실행 화면에서 새 제작자 문구를 렌더링한다.

부팅의 검정/백색 로고/청록색 게이지에 맞춰 새800×480 메인/설정 UI도 검정·청록색 테마를 사용한다. 기존 렌더러의 기본 테마는 별도 호출에서 유지하며 새 UI에서 테마를 지정한다. 원본 참조와 초기 기록에 남아 있는 이전 제작자 이름은 최신 지시가 아니다.

```sh
MEBS_FONT="$PWD/.local-build/sysroot/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc" \
PYTHONPATH="$PWD" .venv/bin/python scripts/preview-journey.py
```

출력: `artifacts/boot-menu-preview/`

- `boot-to-menu.gif`: 로고 페이드/준비 단계→메인→외장 하드→SD→복사→스와이프 설정→밝기→전원 확인→종료 예약→검증→완료.
- `preview.html`: 브라우저에서 파일로 여는 자급식 장면 선택/자동 재생. 인터넷/서버 없음. 프리뷰 버튼은 이미지 장면만 바꾼다.
- `storyboard.jpg`: 대표8개 장면 한눈에 보기.
- `01-boot.png`, `03-main.png`, `07-settings.png` 및 나머지800×480 개별 화면.
- `preview.json`: 모의 데이터/실행 범위/장면/프레임 수.

실제 boot_animation/ui800 렌더러와 Controls의 스와이프/밝기/종료 제스처를 사용한다. OS 부팅·물리 터치·실제 복사·배터리 실측·poweroff 시험은 아니다. 모든 센서·백업 상태는 모의 입력이고 재생 시간은 연출용이다. 실제5초 부팅이나FPS 결과를 뜻하지 않는다. 기본 로고는 제공 JPEG에서 추출한 실제 mask다.

자동 테스트118개 통과. 프리뷰 생성 시 화면800×480/RGB, 설정창 열기, 백업 활성 유지, 종료 예약이 즉시 종료를 허용하지 않는 조건, 완료 후 safe flag를 검사했다. 이미지 빌드403 차단/실물 미확정 상태는 이 프리뷰와 별개다.
