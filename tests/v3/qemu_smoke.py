#!/usr/bin/env python3
"""Boot the ARM64 V3 Buildroot image in QEMU virt with disposable USB images."""
import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('v2_harness', ROOT/'tests/v2-integration/run.py')
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--images', type=Path, default=ROOT/'output/pi4-v3-performance-lock-20261019/images')
    parser.add_argument('--output', type=Path, default=ROOT/'docs/v3')
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    images = args.images.resolve()
    original = v2.sha(images/'sdcard.img')
    record = {'machine':'QEMU virt cortex-a72; not Raspberry Pi 4B hardware',
              'image':str(images/'sdcard.img'),'image_sha256':original,
              'hardware_tested':False,'status':'FAIL'}
    with tempfile.TemporaryDirectory(prefix='mebs-v3-qemu-') as tempname:
        temp = Path(tempname)
        os_image = v2.prepare_os(images, temp)
        fixture = temp/'fixture'; fixture.mkdir()
        target, source, expected, directories, existing = v2.fixtures(fixture)
        source_hash = v2.sha(source)
        folder = temp/'vm'; folder.mkdir()
        guest = None
        try:
            guest = v2.Guest(images, os_image, folder, output, 'v3-explorer')
            guest.attach(target,'target')
            storage = guest.wait({'WAITING_SOURCE'},40)
            guest.attach(source,'source',readonly=True)
            finished = guest.wait({'SAFE_TO_REMOVE'},120)
            record['backup'] = {'storage_ready':storage['state'],
                                'complete':finished['state'],'files':finished.get('verified_files'),
                                'safe_to_remove':finished.get('safe_to_remove')}
            record['performance'] = finished.get('performance')
            assert record['performance']['mode'] in ('BASE', 'UNAVAILABLE')
            assert finished.get('safe_to_remove') is True
            guest.py("import pathlib,subprocess; pathlib.Path('/run/v3-source').mkdir(exist_ok=True); pathlib.Path('/run/v3-target').mkdir(exist_ok=True); subprocess.run(['mount','-t','vfat','-o','ro,utf8=1','/dev/sdb','/run/v3-source'],check=True); subprocess.run(['mount','-t','ext4','-o','rw','/dev/sda','/run/v3-target'],check=True)")
            code = """import base64,hashlib,io,json,pathlib,types
from mebs.explorer_v3 import Browser
from mebs.ui_explorer_v3 import ExplorerUI
from mebs.ui_explorer_v3_layout import render
from mebs.backup import verify
b=Browser('/run/v3-source','/run/v3-target')
rows=b.listdir('source','DCIM/A')
photo=b.thumbnail('source','DCIM/A/사진 01.JPG')
movie=b.probe_video('source','PRIVATE/CLIP/C0001.MP4')
video_thumb=b.thumbnail('source','PRIVATE/CLIP/C0001.MP4')
copy=b.copy_from_source('DCIM/A/사진 01.JPG',confirm=True)
old=copy['path']
moved=b.move_target('MEBS_FILES/사진 01.JPG',confirm=True)
b.delete_target('MEBS_FILES/Archive/사진 01.JPG',confirm=True)
jobs=list(pathlib.Path('/run/v3-target').glob('mebs-backup-*'))
verified=verify(jobs[0])
c=types.SimpleNamespace(reading=types.SimpleNamespace(cpu_c=None,ram_percent=None,voltage=None),state={'demo':True})
s=types.SimpleNamespace(browser=b,control=c,close=lambda:None)
u=ExplorerUI(s);u.path=pathlib.Path('DCIM/A');u.select(next(item for item in rows if item['kind']=='image'))
image=io.BytesIO();render(u).save(image,format='PNG')
result={'rows':[item['name'] for item in rows], 'photo_size':photo.size,'video':movie,'video_thumbnail_size':video_thumb.size,'copy_hash':copy['sha256'],'copy_bytes':copy['bytes'],'moved_to':moved,'original_workspace_file_exists':pathlib.Path(old).exists(),'archive_file_exists':pathlib.Path(moved).exists(),'backup_verified_files':len(verified['files'])}
print('V3_JSON'+json.dumps(result,ensure_ascii=True)+'END_JSON')
print('V3_PNG_BEGIN')
encoded=base64.b64encode(image.getvalue()).decode()
for offset in range(0,len(encoded),512): print(encoded[offset:offset+512])
print('V3_PNG_END')"""
            response = guest.py(code, timeout=90)
            found = re.search(r'V3_JSON(.*?)END_JSON', response, re.S)
            picture = re.search(r'V3_PNG_BEGIN\s+([A-Za-z0-9+/=\s]+?)\s+V3_PNG_END', response, re.S)
            if not found or not picture:
                # The shared V2 harness can consume an earlier shell prompt
                # while this long guest command is still printing. Wait for
                # the explicit end marker, then read the completed serial log.
                guest.child.expect('V3_PNG_END', timeout=90)
                guest.child.expect(v2.PROMPT, timeout=10)
                guest.log.flush()
                response = Path(guest.log.name).read_text(errors='replace')
                found = re.search(r'V3_JSON(.*?)END_JSON', response, re.S)
                picture = re.search(r'V3_PNG_BEGIN\s+([A-Za-z0-9+/=\s]+?)\s+V3_PNG_END', response, re.S)
            if not found or not picture:
                raise RuntimeError('Guest result missing: '+response[-1200:])
            result = json.loads(found.group(1))
            (output/'qemu-explorer.png').write_bytes(base64.b64decode(''.join(picture.group(1).split())))
            record['explorer'] = result
            assert result['backup_verified_files'] == len(expected)
            assert result['photo_size'] == [32,24]
            assert result['video_thumbnail_size'][0] > 0
            assert not result['original_workspace_file_exists'] and not result['archive_file_exists']
            guest.py("import subprocess; subprocess.run(['umount','/run/v3-source'],check=True); subprocess.run(['umount','/run/v3-target'],check=True)")
            record['status'] = 'PASS'
            record['qemu_boot_seconds'] = guest.boot_seconds
        finally:
            if guest:
                guest.close()
        record['source_image_unchanged'] = v2.sha(source) == source_hash
    record['os_image_unchanged'] = v2.sha(images/'sdcard.img') == original
    (output/'qemu-explorer.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(record,ensure_ascii=False,indent=2))
    return 0 if record['status']=='PASS' and record['source_image_unchanged'] and record['os_image_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
