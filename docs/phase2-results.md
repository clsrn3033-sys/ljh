# 2차 구현·실행 결과 — 화면 및 포터블 모니터 시험 준비

2026-10-17, BC250/Bazzite의 현재 Codex 실행 환경.
사용자 C7의 구현 요청과 C8의 Raspberry Pi + 포터블 모니터 선택에 따른 작업이다.
최종 Orange Pi 3B V1.1 부팅 이미지와 독립 자동 백업 제품은 아직 완성되지 않았다.

## 바로 열어 보기

```bash
cd /var/home/bazzite/ljh
xdg-open preview/index.html
```

- [오프라인 미리보기](../preview/index.html): 재생, 이전/다음, 위치 이동, 정상/손상/취소 전환.
- [애니메이션](../preview/demo.gif), [준비 화면](../preview/ready.png), [완료 화면](../preview/complete.png).
- [실패 화면](../preview/error.png), [취소 화면](../preview/cancelled.png).

일반 브라우저에서 파일로 여는 방식이며 서버·외부 CDN·네트워크 요청은 없다.
휴대폰에서는 `preview/index.html` 파일을 옮겨 HTML 열기를 지원하는 브라우저로
열 수 있다. HTML 실행을 제한하는 앱에서는 PNG/GIF로 화면을 확인할 수 있다.
이 파일은 실제 샘플 실행 기록을 재생하며 휴대폰에서 장치를 원격 제어하는 기능은 아니다.
생성 파일은 Git에서 제외하며 `make preview`로 다시 만든다.

## 구현 내용

- 기존 엔진에 파일 수/전체 크기 및 파일별 검증 이벤트 추가, 별도 검증 중 취소 지원.
- `BackupSession`: 준비→원본 선택→대상 선택→복사→검증→독립 재검증→완료.
  오류/취소는 성공이 되지 않으며 `safe_to_remove`는 항상 false다. 실제 unmount는 미구현.
- 800×480 Pillow 화면: 한글 표기, 상태/게이지, 원본/대상, 미확정 제작자 이름.
  실제 로고 제공 전 MEBS 텍스트를 사용한다. 색상/배치는 이번 구현 초안이다.
- 동일 화면을 Linux fbdev로 출력하는 선택형 `display-demo` 명령.
- 로컬 `.pyz` 오류 종료 코드가 사라지던 문제 수정. 실패 시 이제 exit 1을 보존한다.
- Buildroot 패키지에 선택형 화면 의존성과 HTML 템플릿 설치 추가. 실제 이미지 빌드는 미검증.

## 실제 실행 검증

| 실행 | 관측 결과 | 범위/한계 |
| --- | --- | --- |
| `make test` | 기존 33개 포함 **50개 통과** | 임시 디렉터리, subprocess, 상태/화면 메모리 로직 |
| `make preview` | 로컬 `.pyz` 빌드 및 HTML/PNG/GIF 생성 성공 | 실제 3개 샘플 시나리오 실행; OS 빌드 아님 |
| 정상 시나리오 | 원본 해시 불변, 완료 작업 1개, 독립 재검증 통과 | 12MiB 테스트 바이트 + XML/한글 텍스트/빈 폴더 |
| 대상 손상 시나리오 | 검증 오류, 원본 해시 불변, 완료 작업 0개 | 복사된 임시 대상 파일에 손상을 주입 |
| 취소 시나리오 | 취소 상태, 원본 해시 불변, 완료 작업 0개 | 복사 중 취소 요청; 전원 상실 아님 |
| `node tests/check_preview.mjs preview/index.html` | 재생/이동/시나리오 전환/결과 표기 통과 | Node 표준 라이브러리의 DOM 모형; 실제 브라우저 렌더링 시험 아님 |
| 생성 PNG 직접 열람 | 한글·문구·상태·게이지 배치 확인 | 화면 파일 검사; 실제 LCD 시험 아님 |
| Linux 헤더와 ctypes ABI 비교 | Fixed=80, Variable=160, line_length offset=48, red offset=32 일치 | 현재 x86_64만 검증. ARM은 미검증 |
| `python3 dist/mebs.pyz display-demo --device /dev/fb0` | `FAILED`, ENOENT, exit 1 | 현재 환경에 fb0 미노출. 포터블 모니터 출력은 미검증 |

샘플 `.MP4` 파일은 테스트 바이트이며 재생 가능한 촬영 영상이 아니다.
원본 보존은 파일 내용 해시 기준이며 호스트 마운트 정책에 따른 atime 변경 가능성이 있다.
샘플 원본/대상은 임시 폴더에 만들며 사용자 USB에는 접근하지 않는다.
기존 SIGTERM/SIGKILL 시험을 포함해도 물리적 전원 차단 내구성을 증명하지 않는다.

재현 명령:

```bash
make test
make preview
# Node가 있다면 선택적으로 실행 (화면 생성 자체에는 Node 불필요)
node tests/check_preview.mjs preview/index.html
```

현재 호스트에서는 PATH의 Node 대신
`/usr/lib/chatgpt/resources/cua_node/bin/node`를 사용했다.
현재 설치된 Python 3.14.3, Pillow 11.3.0과 Noto Sans CJK 폰트를 사용했으며
시스템 패키지는 설치하지 않았다. `MEBS_FONT`로 다른 한글 폰트 파일을 지정할 수 있다.

실행 로그/데이터:

- [미리보기 생성 로그](logs/phase2-preview.log)
- [framebuffer ABI 검사](logs/phase2-framebuffer-abi.log)
- [정상 증거](../preview/evidence/success.json), [손상 증거](../preview/evidence/corruption.json), [취소 증거](../preview/evidence/cancel.json)

## Raspberry Pi 4 + 포터블 모니터 시험 절차

사용자가 보드와 포터블 모니터 사용을 선택했다. 모델/입력/터치 정보는 아직 없으므로
HDMI는 임시 가정이다. 최종 소형 터치 LCD 요구를 취소하지 않았다.

실물 Linux에서 Python/Pillow/한글 폰트 및 **32-bit truecolor `/dev/fb0`**가 있고
실행 사용자에게 해당 framebuffer 접근 권한이 있을 때 다음 시험이 가능하다:

```bash
python3 scripts/build.py
MEBS_FONT=/path/to/NotoSansCJK-Regular.ttc python3 dist/mebs.pyz display-demo --device /dev/fb0
# 오류 표시 시험
MEBS_FONT=/path/to/NotoSansCJK-Regular.ttc python3 dist/mebs.pyz display-demo --device /dev/fb0 --case corruption
```

명령은 화면 메모리에 실제로 출력하므로 활성 콘솔/그래픽 화면을 덮어 표시한다.
시험 전 해당 화면에서 진행 중인 작업을 정리한다. 해상도/드라이버 설정은 변경하지 않는다.
화면 크기에 맞춰 비율을 유지하며 표시하고 샘플 상태를 잠깐씩 보여 준다. 인위적인
표시 지연이 있으므로 이 명령으로 복사 성능이나 5초 부팅 목표를 측정하지 않는다.

DRM만 노출되거나 16-bit/팔레트 등 지원하지 않는 모드라면 이 시험 코드는 동작하지 않는다.
권한·드라이버 변경을 자동 수행하지 않으며 실물 정보에 맞춰 별도 검토해야 한다.
fbdev 구현 근거: [Linux framebuffer API](https://docs.kernel.org/fb/api.html).
터치 입력·GPIO·자동 서비스·실제 USB 자동 시작은 이 시험 명령에 없다.

Buildroot에서는 C++ 지원 툴체인과 `BR2_PACKAGE_MEBS_DISPLAY=y`를 선택하면
Pillow/FreeType 의존성을 추가한다. 한글 폰트는 별도 rootfs overlay와 `MEBS_FONT`로
제공해야 한다. 이 설정의 빌드/실물 동작은 아직 검증하지 않았다.

## 다음 단계와 차단 조건

1. 현재 환경의 DNS 제한, `patch` 부재 및 컨테이너 실행 제한을 해소할 수 있는
   홈 기반 빌드 환경 확보. Buildroot 소스가 없어 툴체인/커널/rootfs를 아직 빌드하지 못했다.
2. QEMU 게스트 이미지를 소스로 빌드하고 게스트 안에서 기존 백업/오류 시험.
3. 지원 파일시스템·필수 메타데이터와 역할 정책 확정 후 원본 읽기 전용 마운트,
   장치 신원 확인, 자동 시작, 안전 unmount 구현 및 가상 USB 시험.
4. Pi4 + 포터블 모니터에서 실제 표시/삽입/검증/분리 시험. 모니터 입력과 보드 접근 필요.
5. GPIO·배터리/충전·최종 LCD 및 Orange Pi V1.1 BSP를 확정하고 최종 SD 이미지/실물 검증.

배터리·충전 회로와 정확한 폴더 명명·중복 처리 규칙은 사용자 설명대로 미확정이다.
공유 대화 전체 및 과거 승인 디자인은 여전히 확보하지 못했다.
원격 저장소 업로드·호스트 전역 설정 변경·SD 기록은 하지 않았다.
