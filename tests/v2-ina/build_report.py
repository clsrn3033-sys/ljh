#!/usr/bin/env python3
"""Generate evidence-linked V2 INA, battery and image reports from actual runs."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/v2-ina'
LOG=ROOT/'tests/v2-ina/logs'
IMG=ROOT/'output/pi4-v2-ina-v1-20261019/images/sdcard.img'
QEMU=ROOT/'output/pi4-v2-ina-qemu-v1-20261019/images/qemu-virt.img'

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def write(name,value):
    (OUT/name).write_text(value.strip()+'\n')

host=(LOG/'host-tests.log').read_text() if (LOG/'host-tests.log').is_file() else ''
focused=(LOG/'ina-gpio-tests.log').read_text() if (LOG/'ina-gpio-tests.log').is_file() else ''
host_count=re.search(r'Ran (\d+) tests',host)
focused_count=re.search(r'Ran (\d+) tests',focused)
host_pass=bool(re.search(r'Ran \d+ tests.*\n\nOK',host,re.S))
focused_pass=bool(re.search(r'Ran \d+ tests.*\n\nOK',focused,re.S))
qemu_log='\n'.join(path.read_text() for path in sorted(LOG.glob('qemu-T*.log')))
qemu_rows=[]
for line in qemu_log.splitlines():
    if line.startswith('{'):
        try:
            entry=json.loads(line)
            if 'id' in entry and 'status' in entry: qemu_rows.append(entry)
        except json.JSONDecodeError: pass
qemu_status={row['id']:row['status'] for row in qemu_rows}
boot_times=[row['boot_seconds'] for row in qemu_rows if row.get('status')=='PASS' and isinstance(row.get('boot_seconds'),(int,float))]
evidence_dirs=[]
for evidence in re.finditer(r'^EVIDENCE (.+)$',qemu_log,re.M):
    evidence_dirs.append(Path(evidence.group(1)))
    results_file=Path(evidence.group(1))/'results.json'
    if results_file.is_file():
        qemu_status.update({row['id']:row['status'] for row in json.loads(results_file.read_text())})
image_sha=sha(IMG) if IMG.is_file() else None
archive=IMG.with_name('sdcard.img.zst')
archive_sha=sha(archive) if archive.is_file() else None
qemu_sha=sha(QEMU) if QEMU.is_file() else None
table=json.loads(subprocess.check_output(['sfdisk','--json',str(IMG)]))['partitiontable'] if image_sha else None
provenance=json.loads((IMG.parent/'V2_FIX_PROVENANCE.json').read_text()) if image_sha else {}
inspect=(LOG/'image-inspection.log').read_text() if (LOG/'image-inspection.log').is_file() else ''
fsck=(LOG/'rootfs-fsck.log').read_text() if (LOG/'rootfs-fsck.log').is_file() else ''
image_check=image_sha is not None and all('BOOT ::'+name+' FOUND' in inspect for name in ['config.txt','cmdline.txt','start4.elf','fixup4.dat','Image','bcm2711-rpi-4-b.dtb']) and 'I2C_CONFIG True' in inspect and 'I2C_KERNEL True' in inspect and 'Pass 5: Checking group summary information' in fsck

write('V2_INA_DRIVER_REPORT.md',f'''
# V2 INA226/INA231 드라이버 결과 (초기 이미지 기록)

최신 CPU/배터리 화면 및 6.3~8.4V 전압 추정 퍼센트는 `V2_TELEMETRY_UPDATE.md`를 참조하십시오.

- 출발 브랜치: `feature/mebs-v2-pi4b-800x480-20261018`, 출발 커밋 `4fc04cb`.
- 구현: `mebs/ina.py`, `mebs/sensors.py`, `mebs/runtime800.py`, `mebs/hardware_profile.py`.
- 모델 식별: INA226은 0xFE/0xFF의 TI/2260 계열 값을 검사합니다. INA231은 데이터시트에 고유 ID 레지스터가 없어 모듈 모델을 독립적으로 확인하고 `model_confirmed`를 설정해야 합니다. I²C ACK만으로 모델을 확정하지 않습니다.
- 레지스터: shunt 01h(부호 있는 2.5µV/LSB), bus 02h(1.25mV/LSB), calibration 05h(명시적으로 활성화할 때만 기록). 전류는 확인된 션트값을 통한 shunt 전압/저항으로 계산하며 전력은 V×A로 계산합니다. 실물 션트, 극성, 3.3V 풀업 검증 전에는 활성화하지 않습니다.
- 데이터: 전압·전류·전력, UTC와 monotonic 타임스탬프, 모델, `REAL`/`SIMULATION` 출처. 끊김/짧은 읽기/범위 초과/오래된 가상값은 N/A 또는 오류로 처리합니다.
- 이 초기 이미지의 기본값은 REAL 모드, 센서 비활성, N/A였습니다. 최신 화면은 실측 SOC가 아닌 전압 기준 `~%`를 표시합니다.
- 테스트: 집중 센서/GPIO 단위 테스트 **{'PASS' if focused_pass else 'NOT TESTED/FAIL'}** ({focused_count.group(1) if focused_count else 0}개); 전체 호스트 회귀 **{'PASS' if host_pass else 'NOT TESTED/FAIL'}** ({host_count.group(1) if host_count else 0}개). 로그 `tests/v2-ina/logs/ina-gpio-tests.log`, `host-tests.log`.
- 실제 INA226/INA231 측정: **HARDWARE NOT TESTED**. 실제 배터리/충전 회로 연결 및 전압 계측 전 사용 불가.

근거: [TI INA226 데이터시트](https://www.ti.com/lit/ds/symlink/ina226.pdf), [TI INA231 데이터시트](https://www.ti.com/lit/ds/symlink/ina231.pdf).
''')

write('V2_GPIO_VIRTUAL_TEST.md',f'''
# V2 GPIO 가상 테스트

- 1~40 물리 핀, BCM 매핑, 전원/GND 구분, HAT ID 27/28 예약: **{'PASS' if focused_pass else 'NOT TESTED/FAIL'}** (SIMULATION TESTED).
- 설계 할당 1=3.3V, 3=BCM2/SDA1, 5=BCM3/SCL1, 6=GND. 나머지는 미사용 또는 예약; 중복과 7비트 I²C 주소 충돌을 검사합니다.
- 가상 I²C: 주소 0x40의 명시적 센서 연결, NACK/연결 해제, 재연결. 실제 GPIO 또는 배터리를 제어하지 않습니다.
- 핀 설정: `docs/v2-ina/gpio_pinmap.json`; 전체 표와 배치도 `V2_GPIO_PINOUT.md`.
- 3.3V 모듈의 실제 배선/전기적 특성: **HARDWARE NOT TESTED**.
- 명령: `python3 -m unittest discover -s tests -p 'test_v2_ina_gpio.py' -v`.

근거: [Raspberry Pi GPIO 공식 문서](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html).
''')

write('V2_BATTERY_TEST_REPORT.md',f'''
# V2 배터리 가상 측정 및 보호

- 2S 설계값 6.4~8.4V의 11개 전압 구간과 충전·방전 전류, 전력을 INA226/INA231 각각 주입: **{'PASS' if focused_pass else 'NOT TESTED/FAIL'}**, SIMULATION TESTED. 24행 원시 기록은 `battery_simulation.csv`.
- 센서 분리, NACK, 오래된 수치, 범위 외 전압/전류, 재연결: **{'PASS' if focused_pass else 'NOT TESTED/FAIL'}**, SIMULATION TESTED.
- 6.4V 차단 로직: 계측 경로가 확인되어 보호가 설정되면 새 백업을 막고 진행 중인 복사를 협조적으로 중단합니다. 원본은 보존하며 중단 작업을 성공으로 표시하지 않습니다. **{'PASS' if host_pass else 'NOT TESTED/FAIL'}** (임시 파일 실제 복사 테스트).
- 기본 이미지에서는 센서/팩 배선, BMS, 션트가 미확인이라 보호 임계값이 꺼져 있습니다. 6.4V는 설계 후보로만 기록합니다. 실기기에서 계측 경로를 확인하고 임계값을 활성화해야 합니다.
- `battery_real.csv`는 헤더만 있으며 실측 기록은 없습니다. **HARDWARE NOT TESTED**.
- UI 시뮬레이션 화면: `docs/v2-ina/battery-simulation-preview.png`에 SIMULATION 표기와 전압/전류/전력, 측정 상태를 표시했습니다. 실제 센서 화면이 아닙니다.
- 실제 SOC는 검증하지 않았습니다. 최신 화면의 `~%`는 전압 직선 환산 추정치입니다. 실제 배터리 방전/충전/저전압 시험은 하지 않았습니다.
''')

parts='\n'.join(f"|{i+1}|{p['type']}|{p['start']}|{p['size']}|" for i,p in enumerate(table['partitions'])) if table else ''
write('V2_IMAGE_BUILD_REPORT.md',f'''
# V2 Raspberry Pi 4B 초기 INA 이미지 빌드 결과

이 보고서의 IMG는 INA 초기 이미지입니다. 최신 CPU/배터리 표시 이미지 경로와 SHA-256은 `V2_TELEMETRY_UPDATE.md`에 있습니다.

- 상태: **{'PASS' if image_check else 'BLOCKED/FAIL'}** (파일 생성·정적 검사), 실제 Pi 4B 부팅은 **HARDWARE NOT TESTED**.
- Raspberry Pi IMG: `{IMG}`; {IMG.stat().st_size if image_sha else 'N/A'} bytes; SHA-256 `{image_sha or 'N/A'}`.
- 다운로드/전송용 zstd 파일: `{archive if archive_sha else 'NOT BUILT'}`; SHA-256 `{archive_sha or 'N/A'}`. 복원 시 `zstd -d -c sdcard.img.zst > sdcard.img`.
- QEMU virt IMG: `{QEMU}`; SHA-256 `{qemu_sha or 'N/A'}`. 이 이미지는 fstab의 OS 설정 파티션 이름만 vda3으로 적응한 별도 테스트용입니다.
- 생성 방식: BC250에서 기존 Buildroot 소스로 로컬 빌드된 커널/펌웨어/루트FS를 기반으로 **새 파일로 복사**하고 V2 Python 드라이버, UI/런타임, hardware.json, GPIO JSON을 주입했습니다. 이번 단계에 커널을 다시 컴파일한 것은 아닙니다. 원래 이미지 SHA는 provenance JSON에 남아 있습니다.
- I²C: `dtparam=i2c_arm=on`, 커널 `CONFIG_I2C_BCM2835=y`, `CONFIG_I2C_CHARDEV=y`. 40핀의 GPIO2/3 설계 대응. 실제 `/dev/i2c-1` 생성은 실기기에서 확인해야 합니다.
- 정적 확인: FAT의 `config.txt`, `cmdline.txt`, `start4.elf`, `fixup4.dat`, `Image`, bcm2711-rpi-4-b.dtb; 루트FS의 MEBS init 서비스/드라이버/설정; e2fsck. 로그 `tests/v2-ina/logs/image-inspection.log`, `rootfs-fsck.log`.

|번호|형식 코드|시작 섹터|섹터 수|\n|---:|---|---:|---:|
{parts}

- QEMU ARM64 virt 기능 테스트: **{', '.join(k+':'+v for k,v in qemu_status.items()) if qemu_status else 'NOT TESTED'}**. QEMU virt 성공은 Raspberry Pi 4B 실물 부팅 성공을 뜻하지 않습니다.
- QEMU 부팅 시간 관측: **{f'{min(boot_times):.2f}~{max(boot_times):.2f}초' if boot_times else 'NOT TESTED'}**. 5초 실물 부팅 목표는 달성 여부를 판정하지 않았습니다.
- 로그: `tests/v2-ina/logs/image-build.log`, `qemu-image-build.log`, `qemu-T*.log`.
- 명령: `python3 tests/v2-integration/build_fixed_image.py output/pi4-v2-recovery-v4-20261019/images output/pi4-v2-ina-v1-20261019/images` (새 출력 경로만 사용).
''')

write('V2_HARDWARE_CHECKLIST.md','''
# V2 실물 검증 체크리스트

현재 아래 항목은 전부 **HARDWARE NOT TESTED**입니다. 알리익스프레스 부품 도착 이후 별도 실물 검증이 필요합니다.

|대상|실물에서 확인할 사항|
|---|---|
|Raspberry Pi 4B|안정적인 5V/3A 이상 공급, ACT LED/HDMI/시리얼 콘솔, 반복 부팅, EEPROM 상태, `/dev/i2c-1`|
|INA226/INA231|실제 모듈 모델과 핀 배치, 3.3V 전원·I²C 풀업 전압, I²C 주소, 션트값/허용전력, 전류 방향, VBUS가 2S 팩을 측정하는지|
|배터리/전원|2S BMS/밸런싱, 5V 강압기 연속·순간 부하, USB 드라이브 연결 시 전압강하, INA 션트 방열|
|보호 기준|실측 저전압과 BMS 차단 특성 확인 후 6.4V 소프트웨어 임계값 활성화; 진행 중 백업의 재시작 가능성 확인|
|디스플레이|5인치 800×480 DSI 패널 모델/케이블/터치 컨트롤러, DRM/프레임버퍼, 부팅 화면|
|데이터|폐기 가능한 USB/SD로 복사·해시·분리·중단; 실제 사용자 데이터로 포맷 시험 금지|
|시간|QEMU는 RTC 미설정 상태에서 백업 폴더에 1970-01-01을 기록했습니다. 실물에서 시간 동기화 정책을 확인해야 정확한 날짜를 보장할 수 있습니다. RTC 구현은 이번 작업 범위에서 제외합니다.|

RTC와 GPS/GNSS는 이 버전에 추가하지 않았습니다. GPIO2/3 버스 공유 가능성은 주소·전압·풀업을 확인한 뒤 별도 설계합니다. GPIO 물리 전원 차단은 구현하지 않았습니다.
''')

write('V2_CHANGELOG.md','''
# V2 INA/GPIO 변경 내역

- `mebs/ina.py`: INA226 ID 검사, INA231 명시적 모델 확인, 레지스터 측정·계산·보정, 가상 레지스터 버스.
- `mebs/gpio_virtual.py`: Pi4B 40핀 매핑, 설계 할당 검증, 가상 I²C 주소/충돌 검사.
- `mebs/sensors.py`, `mebs/hardware_profile.py`: 공통 측정 구조, 모델·전압/션트/보호 활성화 검증.
- `mebs/runtime800.py`, `mebs/controls.py`, `mebs/ui800.py`: 1초 텔레메트리, REAL/SIMULATION 표시, N/A, V/A/W, 저전압 및 stale 측정 중단 경로.
- `buildroot/board/mebs-pi4-dsi/overlay/etc/mebs/hardware.json`: 기본 REAL + 센서 비활성 및 설계 정보.
- `tests/test_v2_ina_gpio.py`, `tests/test_controls800.py`: 레지스터·핀맵·배터리 보호·실제 임시 파일 복사 회귀.
- `tests/v2-integration/build_fixed_image.py`, `tests/v2-ina/*`: 새 Pi 이미지에 파일 통합, 증거 기반 자동 보고.
- 기존 V1 디렉터리, 기존 빌드 이미지, UI 로고 파일은 수정하지 않았습니다. RTC/GPS 기능도 추가하지 않았습니다.
''')

matrix=[('1','GPIO 40핀 매핑','focused'),('2','BCM-물리 핀 일치','focused'),('3','GPIO 중복 할당','focused'),('4','I²C 핀 설정','image'),('5','INA226 단위','focused'),('6','INA231 단위','focused'),('7','가상 I²C 통신','focused'),('8','센서 분리','focused'),('9','비정상 전압/전류','focused'),('10','11개 전압 구간','focused'),('11','UI 1초 갱신','host'),('12','REAL/SIMULATION 구분','focused'),('13','저전압 보호','host'),('14','기존 백업 회귀','host'),('15','Pi 이미지 생성','image'),('16','드라이버/설정 포함','image'),('17','부팅 서비스 정적 포함','image'),('18','QEMU virt 동작',qemu_status.get('T01','NOT TESTED')),('19','실제 Pi 부팅','hardware'),('20','실제 INA 측정','hardware')]
def result(kind):
    if kind=='focused': return 'PASS · SIMULATION TESTED' if focused_pass else 'NOT TESTED/FAIL'
    if kind=='host': return 'PASS · HOST TESTED' if host_pass else 'NOT TESTED/FAIL'
    if kind=='image': return 'PASS · STATIC TESTED' if image_check else 'BLOCKED/FAIL'
    if kind=='hardware': return 'NOT TESTED · HARDWARE NOT TESTED'
    return kind+' · QEMU virt'
rows='\n'.join(f'|{id}|{name}|{result(kind)}|' for id,name,kind in matrix)
qemu_names={'T01':'정상 복사·SHA-256','T02':'동일 파일 재백업','T03':'용량 부족',
            'T04':'복사 중 대상 분리','T05':'복사 중 원본 분리','T06':'VM 강제 종료·재시작 복구',
            'T07':'복사된 XML 변조 후 명시적 재검증','T08':'읽기 전용 대상','T09':'잘못된 대상 파일시스템',
            'T10':'빈 원본 SD','T11':'한글·특수문자 파일명','T12':'수동 포맷'}
qemu_table='\n'.join(f'|{id}|{name}|{qemu_status.get(id,"NOT TESTED")}|' for id,name in qemu_names.items())
write('V2_TEST_SUMMARY.md',f'''
# V2 INA/GPIO 초기 이미지 테스트 요약

이 표는 초기 INA 이미지 결과입니다. 최신 화면과 새 이미지 테스트는 `V2_TELEMETRY_UPDATE.md`에 기록했습니다.

|ID|항목|결과|\n|---:|---|---|
{rows}

QEMU 별도 사례: {', '.join(k+':'+v for k,v in qemu_status.items()) if qemu_status else 'NOT TESTED'}.

|사례|실행 내용|결과|\n|---|---|---|
{qemu_table}

T01~T11은 각 사례의 새 가상 USB/SD 이미지를 사용했고, 원본 가상 SD 이미지 SHA-256이 그대로임을 확인했습니다. T12는 수동 포맷 기능이 아직 없어 실행하지 않았으며 실제 디스크 포맷도 하지 않았습니다. 게스트 로그와 `results.json`은 {', '.join('`'+str(path.relative_to(ROOT))+'`' for path in evidence_dirs) if evidence_dirs else '`tests/v2-integration/runs/`'}에 있습니다.
실물 부팅, 센서, DSI, 배터리 테스트는 수행하지 않았습니다. 샌드박스 소켓 오류로 차단된 첫 QEMU 시도는 `tests/v2-ina/logs/qemu-full.log`에, 전원 차단으로 중단된 실행은 `qemu-full-real.log`에 따로 남겼습니다.
''')
print('Generated reports for actual evidence:', 'host',host_pass,'focused',focused_pass,'image',image_check,'qemu',qemu_status)
