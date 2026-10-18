#!/usr/bin/env python3
"""Read-only identification report on the actual Pi. No I2C scan/register writes.

Does not infer a panel model from resolution, or a resistor/BMS from an IC ID.
Run on the target: python3 scripts/pi4-hardware-report.py --output hardware-report.json
"""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    try:
        return Path(path).read_text(errors='replace').replace('\x00', ' ').strip()
    except OSError:
        return None


def collect(root=Path('/')):
    def under(path):
        return root / path.lstrip('/')
    model = read(under('/proc/device-tree/model'))
    result = {'read_only': True, 'model': model,
              'compatible': read(under('/proc/device-tree/compatible')),
              'is_pi4b': bool(model and 'Raspberry Pi 4 Model B' in model),
              'drm': [], 'i2c_bound_devices': [], 'input': [], 'backlight': [],
              'physical_only_unknowns': ['exact panel/PCB model', 'INA226 shunt resistance and power rating',
                                         'battery cell model/capacity', 'BMS model and discharge cutoff specs']}
    if not result['is_pi4b']:
        result['note'] = 'Not the target Pi4B: no hardware readiness inference may be made.'
        return result
    for path in sorted(under('/sys/class/drm').glob('card*-*')):
        item = {'connector': path.name, 'status': read(path/'status'), 'modes': read(path/'modes')}
        try:
            data = (path/'edid').read_bytes()
            item['edid_bytes'] = len(data)
            item['edid_sha256'] = hashlib.sha256(data).hexdigest() if data else None
        except OSError:
            pass
        result['drm'].append(item)
    for path in sorted(under('/sys/bus/i2c/devices').glob('*-*')):
        item = {'device': path.name, 'name': read(path/'name'), 'modalias': read(path/'modalias')}
        if item['name'] is not None:
            try:
                item['driver'] = (path/'driver').resolve(strict=True).name
            except OSError:
                item['driver'] = None
            result['i2c_bound_devices'].append(item)
    for path in sorted(under('/sys/class/input').glob('event*')):
        result['input'].append({'event': path.name, 'name': read(path/'device/name'),
                                'modalias': read(path/'device/modalias'), 'phys': read(path/'device/phys')})
    for path in sorted(under('/sys/class/backlight').glob('*')):
        result['backlight'].append({'name': path.name, 'max_brightness': read(path/'max_brightness'),
                                    'brightness': read(path/'brightness')})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    payload = json.dumps(collect(), ensure_ascii=False, indent=2)+'\n'
    if args.output:
        args.output.write_text(payload)
    else:
        print(payload, end='')


if __name__ == '__main__':
    main()
