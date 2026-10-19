#!/usr/bin/env python3
"""Assemble a new Buildroot image with V2 source fixes; never overwrite input.

The kernel/toolchain/firmware were already built locally. A Python-only change
needs no recompilation. Both the new ext4 and raw SD image receive identical
source bytes. The original Pi fstab is retained (no QEMU paths in this image).
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    source=args.input.resolve(); output=args.output.resolve()
    if output.exists():
        raise SystemExit('Output already exists; choose a new directory')
    original=sha(source/'sdcard.img')
    shutil.copytree(source,output,symlinks=True)
    table=json.loads(subprocess.check_output(['sfdisk','--json',str(output/'sdcard.img')]))['partitiontable']
    root=table['partitions'][1]
    offset,length=root['start']*table['sectorsize'],root['size']*table['sectorsize']
    filesystem=output/'rootfs.ext2'
    with (output/'sdcard.img').open('rb') as src, filesystem.open('wb') as dst:
        src.seek(offset)
        remaining=length
        while remaining:
            chunk=src.read(min(1048576,remaining))
            if not chunk: raise RuntimeError('Truncated image')
            dst.write(chunk); remaining-=len(chunk)
    updates={
        '/usr/lib/mebs/mebs/appliance.py':ROOT/'mebs/appliance.py',
        '/usr/lib/mebs/mebs/backup.py':ROOT/'mebs/backup.py',
        '/usr/lib/mebs/mebs/runtime800.py':ROOT/'mebs/runtime800.py',
        '/usr/lib/mebs/mebs/display.py':ROOT/'mebs/display.py',
        '/usr/lib/mebs/mebs/controls.py':ROOT/'mebs/controls.py',
        '/usr/lib/mebs/mebs/sensors.py':ROOT/'mebs/sensors.py',
        '/usr/lib/mebs/mebs/ina.py':ROOT/'mebs/ina.py',
        '/usr/lib/mebs/mebs/gpio_virtual.py':ROOT/'mebs/gpio_virtual.py',
        '/usr/lib/mebs/mebs/hardware_profile.py':ROOT/'mebs/hardware_profile.py',
        '/usr/lib/mebs/mebs/ui800.py':ROOT/'mebs/ui800.py',
        '/etc/mebs/hardware.json':ROOT/'buildroot/board/mebs-pi4-dsi/overlay/etc/mebs/hardware.json',
        '/etc/mebs/gpio_pinmap.json':ROOT/'buildroot/board/mebs-pi4-dsi/overlay/etc/mebs/gpio_pinmap.json',
        '/etc/default/seedrng':ROOT/'buildroot/board/mebs-pi4-dsi/overlay/etc/default/seedrng',
    }
    default_dir=subprocess.check_output(['debugfs','-R','stat /etc/default',str(filesystem)],stderr=subprocess.DEVNULL)
    if b'Type: directory' not in default_dir:
        subprocess.run(['debugfs','-w','-R','mkdir /etc/default',str(filesystem)],check=True)
    for guest,module in updates.items():
        for query in [f'rm {guest}',f'write {module} {guest}']:
            subprocess.run(['debugfs','-w','-R',query,str(filesystem)],check=True)
        installed=subprocess.check_output(['debugfs','-R',f'cat {guest}',str(filesystem)],stderr=subprocess.DEVNULL)
        assert installed==module.read_bytes()
    subprocess.run(['e2fsck','-fn',str(filesystem)],check=True)
    with (output/'sdcard.img').open('r+b') as dst, filesystem.open('rb') as src:
        dst.seek(offset); shutil.copyfileobj(src,dst,1048576)
    assert sha(source/'sdcard.img')==original
    record={'base_image':str(source/'sdcard.img'),'base_sha256':original,
            'fixed_sha256':sha(output/'sdcard.img'),'changed_files':{guest:sha(module) for guest,module in updates.items()},
            'method':'Python source and seedrng configuration update in new copy of locally built Buildroot image; kernel/firmware unchanged; no QEMU fstab change',
            'physical_hardware_tested':False}
    (output/'V2_FIX_PROVENANCE.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))

if __name__=='__main__': main()
