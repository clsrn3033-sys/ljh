#!/usr/bin/env python3
"""Bounded Pi4 model probe. Kernel is loaded directly; EEPROM is not tested."""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images',required=True,type=Path)
    args=parser.parse_args()
    images=args.images.resolve()
    image=images/'sdcard.img'
    if not image.is_file() or image.is_block_device():
        raise SystemExit('A regular disk image file is required')
    output=Path(__file__).resolve().parent/'logs'/('raspi4b-'+time.strftime('%Y%m%d-%H%M%S')+'.log')
    output.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mebs-pi4-probe-') as temp:
        copy=Path(temp)/'sd.raw'
        subprocess.run(['cp','--sparse=always',str(image),str(copy)],check=True)
        with copy.open('r+b') as stream:
            stream.truncate(1 << (image.stat().st_size-1).bit_length())
        command=['qemu-system-aarch64','-M','raspi4b','-m','2G','-smp','4','-display','none',
                 '-serial','stdio','-monitor','none','-kernel',str(images/'Image'),
                 '-dtb',str(images/'bcm2711-rpi-4-b.dtb'),
                 '-append','root=/dev/mmcblk0p2 rootwait ro console=ttyAMA0,115200 console=ttyS0,115200 loglevel=7',
                 '-drive',f'file={copy},format=raw,if=sd']
        started=time.monotonic()
        try:
            result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
            serial,code=result.stdout,result.returncode
        except subprocess.TimeoutExpired as exc:
            serial,code=exc.stdout or b'',124
        record={'status':'BLOCKED','qemu_exit':code,'wall_seconds':round(time.monotonic()-started,3),
                'kernel_log_observed':b'Linux version' in serial,'login_observed':b'login:' in serial,
                'note':'No real Pi, EEPROM/firmware boot or DSI tested. Inspect serial log; a timeout is not boot success.'}
        output.write_text('COMMAND '+shlex.join(command)+'\n'+serial.decode(errors='replace')+'\nRESULT '+json.dumps(record)+'\n')
        print(json.dumps(record)); print(output)

if __name__=='__main__': main()
