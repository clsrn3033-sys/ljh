#!/usr/bin/env python3
"""Compare V2/V3 QEMU virt boot and idle memory with the same harness."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('v2_harness', ROOT/'tests/v2-integration/run.py')
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


def sample(images, temp, output, label):
    os_image = v2.prepare_os(images, temp)
    logs = output / label
    logs.mkdir(parents=True, exist_ok=True)
    values = []
    for index in range(3):
        folder = temp / str(index)
        folder.mkdir()
        guest = None
        try:
            guest = v2.Guest(images, os_image, folder, logs, f'boot-{index+1}')
            output_text = guest.py("""import json,pathlib
available=int(next(line.split()[1] for line in open('/proc/meminfo') if line.startswith('MemAvailable:')))
rss=None
for path in pathlib.Path('/proc').iterdir():
    if not path.name.isdigit(): continue
    try:
        if b'mebs.runtime800' in (path/'cmdline').read_bytes():
            rss=int(next(line.split()[1] for line in (path/'status').read_text().splitlines() if line.startswith('VmRSS:')))
            break
    except (OSError,StopIteration): pass
print('MEBS_METRICS'+json.dumps({'available_kib':available,'mebs_rss_kib':rss}))""")
            found=re.search(r'MEBS_METRICS(\{[^\r\n]+\})',output_text)
            if not found:
                raise RuntimeError('Guest memory metrics missing: '+output_text[-500:])
            metrics=json.loads(found.group(1))
            values.append(dict(boot_seconds=guest.boot_seconds, **metrics))
        finally:
            if guest:
                guest.close()
    return {'image_bytes':(images/'sdcard.img').stat().st_size,
            'image_sha256':v2.sha(images/'sdcard.img'), 'runs':values,
            'mean_boot_seconds':round(sum(x['boot_seconds'] for x in values)/len(values),3)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--v2',type=Path,default=ROOT/'output/pi4-v2-repeat-v6-20261019/images')
    p.add_argument('--v3',type=Path,required=True)
    p.add_argument('--output',type=Path,default=ROOT/'docs/v3/boot-comparison.json')
    args=p.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    results={'machine':'QEMU virt cortex-a72, 1024 MiB, 2 vCPU; not Pi4B hardware',
             'metric':'QEMU launch to auto-start MEBS READY plus harness login; 3 cold VM runs per image'}
    for label, images in (('v2',args.v2.resolve()),('v3',args.v3.resolve())):
        with tempfile.TemporaryDirectory(prefix=f'mebs-{label}-boot-') as folder:
            results[label]=sample(images,Path(folder),args.output.parent,label)
    args.output.write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))


if __name__=='__main__':
    main()
