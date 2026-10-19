#!/usr/bin/env python3
"""Read-only V3 Pi4 image validation; never opens block devices."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
MODULES=('appliance.py','backup.py','controls.py','runtime800.py','ui800.py',
         'explorer_v3.py','ui_explorer_v3.py','ui_explorer_v3_layout.py')


def run(*args):
    return subprocess.run([str(arg) for arg in args],check=True,capture_output=True).stdout


def sha(path):
    with Path(path).open('rb') as data:
        return hashlib.file_digest(data,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output-dir',type=Path,default=ROOT/'output/pi4-v3-atomic-20261019')
    p.add_argument('--report',type=Path,default=ROOT/'docs/v3/image-validation.json')
    args=p.parse_args()
    out=args.output_dir.resolve(); image=out/'MABS_V3_RPi4.img'; images=out/'images'
    if not image.is_file() or image.is_block_device():
        raise SystemExit('Regular image file required')
    disk=images/'sdcard.img'; root=images/'rootfs.ext2'; boot=images/'boot.vfat'
    table=json.loads(run('sfdisk','--json',image))['partitiontable']
    assert len(table['partitions'])==3
    assert table['partitions'][0]['bootable'] and table['partitions'][0]['type']=='c'
    assert table['partitions'][1]['type']=='83' and table['partitions'][2]['type']=='83'
    assert sha(image)==sha(disk)
    assert run('file',images/'Image').find(b'ARM64 boot executable')>=0
    for guest in ('start4.elf','fixup4.dat','config.txt','cmdline.txt','Image','bcm2711-rpi-4-b.dtb'):
        run('mtype','-i',boot,'::'+guest) if guest.endswith('.txt') else run('mdir','-i',boot,'::'+guest)
    config=run('mtype','-i',boot,'::config.txt').decode()
    cmdline=run('mtype','-i',boot,'::cmdline.txt').decode()
    assert 'arm_64bit=1' in config and 'kernel=Image' in config
    assert 'root=/dev/mmcblk0p2' in cmdline
    fsck=subprocess.run(['e2fsck','-fn',str(root)],capture_output=True,text=True)
    assert fsck.returncode==0, fsck.stdout[-1200:]+fsck.stderr[-1200:]
    installed={}
    for name in MODULES:
        source=ROOT/'mebs'/name
        guest='/usr/lib/mebs/mebs/'+name
        data=run('debugfs','-R','cat '+guest,root)
        actual=hashlib.sha256(data).hexdigest()
        assert actual==sha(source), name+' in image differs from V3 source'
        installed[name]=actual
    for name in ('ffprobe','ffmpeg'):
        binary=images.parent/'target/usr/bin'/name
        assert binary.is_file()
        description=run('file',binary).decode()
        assert 'ARM aarch64' in description, description
        run('debugfs','-R','stat /usr/bin/'+name,root)
    fstab=run('debugfs','-R','cat /etc/fstab',root).decode()
    assert '/dev/mmcblk0p3 /var/lib/mebs' in fstab
    assert '/dev/vda3 /var/lib/mebs' not in fstab
    record={'status':'PASS','physical_hardware_tested':False,'image':str(image),
            'size_bytes':image.stat().st_size,'sha256':sha(image),'base_v2_sha256':sha(ROOT/'output/pi4-v2-repeat-v6-20261019/images/sdcard.img'),
            'partitions':table['partitions'],'boot_files':'start4.elf fixup4.dat config.txt cmdline.txt Image bcm2711-rpi-4-b.dtb',
            'rootfs_fsck':'PASS','source_module_sha256':installed,'ffprobe_ffmpeg':'ARM64 ELF present',
            'pi_boot':'HARDWARE NOT TESTED','dsi_touch':'HARDWARE NOT TESTED'}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(record,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
