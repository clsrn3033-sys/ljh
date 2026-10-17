# 1차 개발 및 테스트 기록

이 문서는 1차 시점의 기록이다. 최신 화면 구현과 50개 테스트 결과는
[2차 결과](phase2-results.md)를 참고한다.

날짜: 2026-10-17, BC250/Bazzite의 현재 Codex 실행 환경.

## 소스 출처 및 변경

사용자 승인: 빈 `clsrn3033-sys/ljh`에 이번 지시서대로 신규 구현.
원격 파일/커밋/브랜치가 비어 있음을 GitHub 도구로 확인했다. shell clone은 DNS 오류.
같은 원격 주소를 등록한 `/var/home/bazzite/ljh` 로컬 저장소를 초기화했다.
브랜치: `work/mebs-foundation`. 원격 변경과 GitHub push 없음.

백업 엔진/명령줄/읽기 전용 USB 관찰기, 33개 테스트, 로컬 zipapp 빌드/데모,
Buildroot 외부 패키지 및 소스 빌드/QEMU 스크립트, 요구사항 문서를 새로 추가했다.
중간 코드 검토에서 Buildroot 동기화 대상을 전체 프로젝트 대신 `mebs/`로 좁혀
출력 디렉터리 재귀 복사를 방지했고, upstream에 없는 개별 LSBLK 설정 대신 실제
util-linux BINARIES 설정을 사용했다. 이 수정은 소스 검토이며 Buildroot 빌드 검증은 아니다.

## 직접 실행한 검증

| 실행 | 결과 | 검증 범위 |
| --- | --- | --- |
| `make test` | 33개 통과 | 임시 디렉터리 및 실제 subprocess에서 백업 안전 로직 |
| `make build` | 성공 | 이 컴퓨터에서 Python 소스를 zipapp으로 묶음; OS 빌드 아님 |
| `make demo` | 성공 | 빌드된 `.pyz`로 2,097,193바이트/2파일 복사 및 별도 verify |
| `python3 dist/mebs.pyz ready` | 성공 | MEBS/한글 표기/미확정 Produced by/엔진 준비 문구 |
| `python3 dist/mebs.pyz devices` | 성공, 빈 목록 | 이 샌드박스에 보이는 lsblk 결과; 실제 USB 연결 테스트 아님 |
| QEMU TCG 시작/monitor quit | 성공 | 디스크·네트워크 없이 에뮬레이터 프로세스 시작/종료만 |
| `bash -n` (shell scripts) | 통과 | shell 문법만; 이미지 빌드/부팅 검증 아님 |
| `scripts/check-host.sh` | 실패 | `patch` 누락. 다른 검사 명령은 발견됨. KVM 미노출 |
| Buildroot 소스 URL HEAD | 실패 | `curl: (6) Could not resolve host: buildroot.org` |

현재 환경: AMD BC-250 6코어/12스레드, 메모리 약 14.8GiB, Bazzite 43,
Python 3.14.3, QEMU 10.1.5. 호스트 홈 여유 약 150GB. 장치 노드/컨테이너 런타임
접근 제한이 있어 호스트 자체에서 지원되지 않는 것으로 단정하지 않는다.

테스트 상세:

- 한글 경로/XML/빈 폴더/빈 파일/수정 시각/권한/user xattr 보존.
- 기존 대상 데이터와 이전 백업 불변, 빈 원본, 동일/중첩 경로 거부.
- 심볼릭 링크/FIFO/잠금 경합/위험한 잠금 링크 거부.
- 공간 사전 검사, 복사 중 ENOSPC 주입, 부분 write 처리.
- SHA-256 불일치 주입, 복사 후 실제 데이터 오염 감지.
- 원본 변경/추가 감지, 취소, 완료 후 재검증에서 변조/추가 파일/경로 탈출 거부.
- 장치 삽입 순서/동시 감지/시작 전 연결/분리/세 번째 장치의 역할 판단.
- 실제 SIGTERM: 실패 기록과 부분 작업 유지, 원본 내용 불변.
- 실제 SIGKILL: 핸들러 없이 부분 작업 유지, 완료 작업 없음, 원본 내용 불변.

ENOSPC 주입과 해시 불일치 주입은 실제 USB 하드웨어 장애 시험이 아니다.
SIGKILL은 프로세스 강제 종료이며 물리적 전원 상실이나 저장장치 캐시 손상 시험이 아니다.

## 로그

- [unit-tests.log](logs/unit-tests.log)
- [demo.log](logs/demo.log)
- [host-check.log](logs/host-check.log)
- [qemu-tcg-smoke.log](logs/qemu-tcg-smoke.log)
- [ready.log](logs/ready.log)
- [devices.log](logs/devices.log)

데모 로그의 `/tmp/mebs-demo-...` 경로는 종료 시 정리된 임시 자료이다.
각 데모 실행의 UUID/시간은 달라진다. 빌드 산출물 `dist/mebs.pyz`는 Git에서 제외한다.

## 남은 작업 및 차단 조건

1. 일반 호스트 터미널 또는 홈 기반 컨테이너에서 DNS/패키지 의존성 해결.
   현재 Podman/Distrobox는 런타임 디렉터리 쓰기 제한으로 실행할 수 없다.
   호스트 전역 패키지 설치/설정 변경은 하지 않았다.
2. Buildroot 소스 확보 후 QEMU용 로컬 툴체인/커널/rootfs 빌드 및 게스트 백업 테스트.
   현재 Buildroot 소스가 없으므로 빌드 오류 분석 단계에 아직 도달하지 않았다.
3. LCD 사양과 이미지 확인 후 경량 GUI/진행률/부팅 화면. 이름 최종 확인.
4. USB 파일시스템/역할 정책 확정 후 원본 ro 마운트, 자동 백업, 안전 분리.
5. GPIO/전원 회로 확인 후 취소→flush→unmount→shutdown 순서 실물 검증.
6. Pi4 실물 검증 후 Orange Pi 3B V1.1 BSP와 이미지 제작. 5초 부팅 실측.

실제 USB 자동 백업, GUI/LCD/GPIO, 포맷, 안전 분리 실행, OS 이미지 빌드,
QEMU 게스트 부팅, 보드 테스트, 5초 목표는 현재 완료/성공으로 보고하지 않는다.
