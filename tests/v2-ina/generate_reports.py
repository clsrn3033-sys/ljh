#!/usr/bin/env python3
"""Regenerate the design pinout and repeatable virtual measurement ledger."""
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mebs.gpio_virtual import json_data, pinmap, VirtualI2CBus
from mebs.ina import INA226, INA231, VirtualINARegisters

out = ROOT/'docs/v2-ina'
out.mkdir(exist_ok=True,parents=True)
pins=pinmap()
gpio_json=json.dumps(json_data(),indent=2,ensure_ascii=False)+'\n'
(out/'gpio_pinmap.json').write_text(gpio_json)
(ROOT/'buildroot/board/mebs-pi4-dsi/overlay/etc/mebs/gpio_pinmap.json').write_text(gpio_json)
rows=['# Raspberry Pi 4B GPIO 40핀 설계 할당',
      '', '이 표는 설계 및 가상 매핑 검증 결과입니다. 실제 배선/전기적 동작: HARDWARE NOT TESTED.',
      'GPIO2/3은 I²C1, 물리 27/28의 GPIO0/1은 HAT ID EEPROM 예약입니다. RTC/GPS는 이번 구성에 없습니다.',
      '', '```text', 'J8 물리 핀: 왼쪽 홀수 / 오른쪽 짝수']
for n in range(1,40,2):
    rows.append(f'{n:02d} {pins[n-1].default_function:<7} | {n+1:02d} {pins[n].default_function}')
rows += ['```','','|물리 핀|BCM|기본 기능|V2 할당|연결 부품|상태|설정/코드|가상 테스트|실물 확인|',
         '|---:|---:|---|---|---|---|---|---|---|']
for p in pins:
    rows.append(f'|{p.physical}|{p.bcm if p.bcm is not None else "N/A"}|{p.default_function}|{p.assignment}|{p.component}|{p.status}|{p.config_location}|{p.virtual_result}|{p.hardware_result}|')
(out/'V2_GPIO_PINOUT.md').write_text('\n'.join(rows)+'\n')

header=['model','voltage_v','current_a','power_w','source','timestamp_utc','low_voltage_6_4_design']
with (out/'battery_simulation.csv').open('w',newline='') as file:
    writer=csv.writer(file,lineterminator='\n'); writer.writerow(header)
    for model,driver in [('INA226',INA226),('INA231',INA231)]:
        bus=VirtualINARegisters(model,.01)
        monitor=driver(bus,.01,model_confirmed=model=='INA231')
        for i in range(11):
            voltage=round(6.4+.2*i,1)
            bus.inject(voltage,.5)
            m=monitor.sample()
            writer.writerow([m.model,f'{m.voltage:.4f}',f'{m.current_a:.4f}',f'{m.power_w:.4f}',m.source,m.timestamp_utc, 'BLOCK' if m.voltage<=6.4 else 'OK'])
        bus.inject(7.4,-.5)
        m=monitor.sample()
        writer.writerow([m.model,f'{m.voltage:.4f}',f'{m.current_a:.4f}',f'{m.power_w:.4f}',m.source,m.timestamp_utc,'OK'])
with (out/'battery_real.csv').open('w',newline='') as file:
    csv.writer(file,lineterminator='\n').writerow(header)
print(f'Wrote 40 pins and 24 simulated measurements to {out}')
