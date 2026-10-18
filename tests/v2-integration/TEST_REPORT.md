# MEBS V2 실제 가상 디스크 통합 시험

2026-10-19 KST. 브랜치 `feature/mebs-v2-pi4b-800x480-20261018`.
V1과 기존 이미지를 보존하고 V2를 시험했다. 원격 저장소에 업로드하지 않았다.

최종 후보 이미지로 12개 항목 모두 다시 실행한 결과는
[ARM64 재시험 보고서](ARM64_RETEST_20261019.md)를 우선 확인한다.
재시험에서도 **8 PASS / 3 FAIL / 1 BLOCKED**였고 원본 IMG 해시는 유지됐다.

## 결론

**QEMU ARM64 virt에서는 정상 init → MEBS 자동 시작 → USB 순차 인식 → 실제
파일 복사 → SHA-256 검증 → 정상 unmount → SAFE_TO_REMOVE를 확인했다.**
Raspberry Pi 4B의 EEPROM/펌웨어 부팅, 실제 USB 전원, DSI 및 터치는 검증하지 않았다.
QEMU `raspi4b` 직접 부팅은 30초 내 커널/로그인 출력이 없어 BLOCKED이다.
현재 후보 이미지는 **실기기 시험용이며 촬영 원본에 사용하는 배포 승인본이 아니다.**

- 백업 시나리오: **8 PASS / 3 FAIL / 1 BLOCKED**, 총 12개 중 66.7% 통과.
- 실제 실행한 11개 중 8개 통과(72.7%). 미실행 포맷을 통과로 세지 않았다.
- 호스트 기존 unittest: **118개 PASS** ([로그](logs/host-tests.log)).
- 앞선 XML 1개 정기 smoke 시험: 02:13~05:43 KST, 30분 간격 **8/8 PASS**.
  이 결과를 전체 기능 통과로 해석하지 않는다.
- 표식 없이 먼저 연결한 USB로 백업 성공: [별도 최종 시험](runs/20261019-064559/results.json).
  `수정금지.txt`를 필요 조건으로 추가하지 않았다.

상세 판정·실행 명령·예상/실제 결과는 [BACKUP_TEST_RESULTS.md](BACKUP_TEST_RESULTS.md),
발견 문제와 수정은 [ISSUES.md](ISSUES.md), 재실행은 [README_TEST.md](README_TEST.md).

## 환경과 부팅 증거

호스트: BC250 Bazzite 43, Linux 6.17.7 계열, QEMU 10.1.5.
guest: Cortex-A72 2 vCPU, RAM 1GiB, Buildroot 2026.08, ARM64 Linux 6.12.61-v8.
기존 로컬 소스 빌드의 커널/펌웨어/rootfs를 사용한다. 완성 OS 다운로드는 사용하지 않았다.

`virt`는 microSD를 `/dev/vda`로 노출하므로 **폐기용 복사본**의 fstab 설정 파티션만
`mmcblk0p3` → `vda3`로 변경했다. 원본/배포 후보는 Pi의 mmcblk 경로를 유지한다.
테스트 root cmdline은 `/dev/vda2`, PID 1은 `init`, S50mebs가 앱을 자동 실행한다.
`init=/bin/sh`로 수동 실행한 결과를 자동 시작으로 세지 않았다.
설정 파티션 실제 마운트와 저장장치 없는 READY도 확인했다.

최종 후보 T01: 호스트 VM 시작부터 READY 확인까지 8.023초, guest uptime 7.95초.
이는 serial 로그인·폴링 시간이 포함된 QEMU 측정이다. 실물 5초 목표 달성 증거가 아니다.
[BOOT_LOG.txt](BOOT_LOG.txt)에 커널·init·READY와 raspi4b 실패 로그를 함께 기록했다.
초기 status.json 생성 전 조회 traceback은 테스트 폴링 경합이며, 재실행 도구에서는
파일 생성 전 BOOTING으로 기다리도록 수정했다.

QEMU 10.1.5에는 raspi4b 모델이 실제 존재하지만 실행 시 PCIe, RNG200, thermal,
GENET 비활성화 경고가 있었다. [공식 보드 문서](https://www.qemu.org/docs/master/system/arm/raspi.html)도
일부 장치 미구현을 명시한다. 최신 문서와 설치 버전은 다를 수 있다.
직접 `-kernel` 시험은 성공하더라도 EEPROM/start4.elf 부팅 검증이 아니다.

## 화면

요청한 화면 시연은 대화 중 **한 번** 제공했다.
[화면 파일](runs/20261019-063738/screenshots/T01-guest-safe-to-remove.png)은 ARM guest에서
실제 백업 상태 JSON을 production `mebs.ui800.render`로 그린 800×480 PNG이다.
정상 백업 10/10 파일, Storage/SD Ready 및 안전 분리 상태를 표시했다.
배터리/CPU 센서가 없는 guest에서 수치를 만들어 넣지 않았다.

이는 guest offscreen 화면이며 QEMU framebuffer나 실제 DSI 화면 캡처는 아니다.
실제 자동 GUI 출력·부팅 애니메이션 전체 재생·터치/백라이트·DS3231/INA226은
NOT TESTED. 빠른 설정/종료 안전성은 호스트 단위 시험 범위이며 실물 시험이 아니다.
RAM 사용률 UI는 현재 누락되어 있다. UI CPU/RAM 성능은 이번 실행에서 측정하지 않았다.

## 수정 및 이미지

1. `mebs/appliance.py`: FAT32 mount에 `utf8=1` 추가. 이전에는 원본 한글 이름이
   `?`로 읽혀 파일 해시가 맞아도 경로가 손실됐다. 수정 후 실제 FAT32에서 경로·해시 확인.
2. `buildroot/board/mebs-pi4-dsi/overlay/etc/default/seedrng`: read-only root 대신
   OS 전용 설정 파티션에 seed 보관. 최종 부팅 로그에서 seed 저장 성공 확인.

새 후보: `output/pi4-v2-validated-20261019/images/sdcard.img` (297MiB).
압축: `artifacts/MEBS-V2-test-candidate-20261019.img.zst` (약 37.2MiB).
파일명 validated는 하드웨어 검증 완료를 의미하지 않는다.

```text
raw SHA-256: 27104982a1c9d5a6931d6ce4c3f301f53041e261365e43a5c759eece261f94ec
zst SHA-256: 8f0651896ab4ccd2260416a3e5a74b9a5d83d0250b41c0f791a8ce47796bc941
```

로컬 Buildroot 빌드에 Python/config 두 파일만 반영한 **새 복사본**이다.
이번 수정에서 커널 전체를 재컴파일하지 않았다. `V2_FIX_PROVENANCE.json`에 추적 정보를 기록했다.
boot FAT32 96MiB, root ext4 192MiB, settings ext4 8MiB; Pi4 펌웨어·ARM64 magic·
fstab·서비스 검사와 세 파일시스템 read-only fsck, zstd 무결성 검사를 통과했다.
[구조 검사](logs/final-image-inspection.log), [fsck](logs/final-filesystems.log),
[압축 검사](logs/final-compression.log).

원본 IMG SHA-256은 `272fcf5e9ab509ec9e3ce6d15dca0bf9a206d18f0f7441b8020a2c0f598618a3`로 유지했다.
호스트 mount/loop/물리 디스크 포맷은 사용하지 않았고 모든 QEMU 데이터는 시험 전용 파일이다.

## 실기기 다음 시험

1. 촬영 원본과 기존 백업 하드를 분리하고 폐기 가능한 microSD에 후보 이미지를 기록한다.
   다른 디스크를 잘못 선택하지 않도록 기록 장치의 용량/모델을 직접 확인한다.
2. Pi4B에 적정 전원과 micro-HDMI 모니터를 연결하고 디스크 없이 READY 및 로그를 확인한다.
   EEPROM을 변경하지 않는다. DSI 모듈 모델이 확정되기 전 패널 동작을 가정하지 않는다.
3. 샘플만 담은 ext4 USB를 먼저 연결, 샘플 FAT32 SD를 다음 연결한다.
   용량·경로·해시·오류 표시를 별도 PC와 대조하고 SAFE_TO_REMOVE 후 분리한다.
4. 중복/중단 작업 안내·빈 카드 메시지·날짜·포맷 요구를 해결한 뒤 별도 회귀 시험한다.
5. 실제 USB 전원 안정성, 강제 전원 차단 내구성, DSI/터치/센서, cold boot 시간은
   실기기에서 추가 검증해야 한다. 현재 결과만으로 현장 데이터 안전성을 보장하지 않는다.
