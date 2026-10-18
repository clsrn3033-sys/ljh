#!/usr/bin/env python3
"""Reboot one disposable QEMU ARM64 overlay 20 times and record actual READY times."""
import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('integration_run', HERE/'run.py')
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--prepared-os', type=Path, required=True)
    parser.add_argument('--count', type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.count <= 20:
        raise SystemExit('count must be 1..20')
    images, os_image = args.images.resolve(), args.prepared_os.resolve()
    if not os_image.is_file() or os_image.is_block_device():
        raise SystemExit('Prepared OS must be a regular file')
    evidence = HERE/'boot-runs'/__import__('time').strftime('%Y%m%d-%H%M%S')
    evidence.mkdir(parents=True)
    rows=[]
    with tempfile.TemporaryDirectory(prefix='mebs-boot-repeat-') as temp:
        overlay=Path(temp)/'persistent-os.qcow2'
        for index in range(1,args.count+1):
            folder=Path(temp)/f'boot-{index:02d}'
            folder.mkdir()
            guest=None
            try:
                guest=suite.Guest.__new__(suite.Guest)
                guest.__init__(images,os_image,folder,evidence,f'boot-{index:02d}',overlay=overlay)
                row={'run':index,'status':'PASS','ready_seconds':round(guest.boot_seconds,3),
                     'pid1_init':"'pid1': 'init'" in guest.boot_evidence,
                     'settings_mounted':"'settings_mounted': True" in guest.boot_evidence}
                if not row['pid1_init'] or not row['settings_mounted']:
                    row['status']='FAIL'
            except Exception as exc:
                row={'run':index,'status':'FAIL','error':repr(exc)}
            finally:
                if guest:
                    guest.close()
            rows.append(row)
            (evidence/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
            print(json.dumps(row),flush=True)
    good=[row['ready_seconds'] for row in rows if row['status']=='PASS']
    summary={'image':str(os_image),'runs':len(rows),'passed':len(good),'failed':len(rows)-len(good),
             'min_seconds':min(good) if good else None,'median_seconds':round(statistics.median(good),3) if good else None,
             'max_seconds':max(good) if good else None,
             'measurement':'QEMU process start to automatic READY after serial login/status polling; not physical cold boot',
             'physical_hardware_tested':False}
    (evidence/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('EVIDENCE',evidence)
    return 0 if len(good)==args.count else 1

if __name__=='__main__':
    raise SystemExit(main())
