#!/usr/bin/env python3
"""Run the shipped ARM64 V2 software against disposable QEMU USB images.

Never opens host block devices. The sole guest adaptation is fstab's OS settings
partition name (mmcblk0p3 -> vda3), in a temporary image copy. PID 1 and S50mebs
are the production ones; the harness does not start MEBS itself.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import tempfile
import time

import pexpect
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('old_harness', ROOT/'scripts/test-pi4-v2-qemu.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
PROMPT = r'MEBS_TEST# '


def command(*args):
    return subprocess.run([str(x) for x in args], check=True, capture_output=True, text=True).stdout


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare_os(images, temp):
    original = images/'sdcard.img'
    assert original.is_file() and not original.is_block_device()
    table = json.loads(command('sfdisk', '--json', original))['partitiontable']
    part = table['partitions'][1]
    offset, length = part['start']*table['sectorsize'], part['size']*table['sectorsize']
    raw, root = temp/'test-os.img', temp/'root.ext4'
    command('cp', '--sparse=always', original, raw)
    with original.open('rb') as src, root.open('wb') as dst:
        src.seek(offset)
        for _ in range(length//1048576):
            dst.write(src.read(1048576))
        dst.write(src.read(length%1048576))
    fstab = command('debugfs', '-R', 'cat /etc/fstab', root)
    assert '/dev/mmcblk0p3 /var/lib/mebs' in fstab
    (temp/'fstab').write_text(fstab.replace('/dev/mmcblk0p3 /var/lib/mebs', '/dev/vda3 /var/lib/mebs'))
    command('debugfs', '-w', '-R', 'rm /etc/fstab', root)
    command('debugfs', '-w', '-R', f'write {temp}/fstab /etc/fstab', root)
    with raw.open('r+b') as dst, root.open('rb') as src:
        dst.seek(offset)
        shutil.copyfileobj(src, dst, 1048576)
    return raw


def fixtures(folder, *, empty=False, large=False, short=False, marker=False, bad_target=False):
    tree, existing = folder/'camera-tree', folder/'target-tree'
    tree.mkdir(); existing.mkdir()
    (existing/'KEEP_EXISTING.txt').write_text('Existing user data must survive.\n')
    if marker:
        (existing/'수정금지.txt').write_text('MEBS integration fixture.\n')
    if not empty:
        for name in ['DCIM/A', 'DCIM/B', 'PRIVATE/CLIP', 'EMPTY', '한글 폴더/深い/하위']:
            (tree/name).mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (32, 24), '#58dfff').save(tree/'DCIM/A/사진 01.JPG')
        command('ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=32x24:d=0.2',
                '-c:v', 'mpeg4', '-y', tree/'PRIVATE/CLIP/C0001.MP4')
        (tree/'PRIVATE/CLIP/C0001.XML').write_text('<?xml version="1.0"?><clip>촬영 &amp; metadata</clip>\n')
        (tree/'DCIM/A/same.bin').write_bytes(b'identical content\x00'*41)
        (tree/'DCIM/B/same.bin').write_bytes(b'identical content\x00'*41)
        (tree/'한글 폴더/深い/하위/파일 [1] & 공백.txt').write_text('한국어 中文 integrity\n')
        (tree/'.hidden').write_bytes(b'hidden')
        (tree/'zero.dat').touch()
        (tree/'가.txt').write_bytes(b'first distinct Korean filename')
        (tree/'나.txt').write_bytes(b'second distinct Korean filename')
        if large or short:
            with (tree/'PRIVATE/CLIP/large.bin').open('wb') as stream:
                for i in range(32):
                    stream.write(bytes([i])*1048576)
    expected = {str(p.relative_to(tree)): sha(p) for p in tree.rglob('*') if p.is_file()}
    directories = sorted(str(p.relative_to(tree)) for p in tree.rglob('*') if p.is_dir())
    target, source = folder/'virtual_external.img', folder/'virtual_camera_sd.img'
    with target.open('wb') as stream:
        stream.truncate((16 if short else 192)*1048576)
    if bad_target:
        command('mkfs.vfat', '-F', '32', target)
        command('mcopy', '-i', target, *list(existing.iterdir()), '::/')
    else:
        command('mkfs.ext4', '-q', '-F', '-d', existing, target)
    command('mkfs.vfat', '-F', '32', '-C', source, '65536')
    if list(tree.iterdir()):
        command('mcopy', '-s', '-i', source, *list(tree.iterdir()), '::/')
    expected_target = {p.name: sha(p) for p in existing.iterdir()}
    return target, source, expected, directories, expected_target


class Guest:
    def __init__(self, images, os_image, folder, logs, case, *, overlay=None):
        self.folder, self.events, self.index = folder, [], 0
        self.ready = False
        self.log = (logs/f'{case}.serial.log').open('w', buffering=1)
        self.overlay = overlay or folder/'os.qcow2'
        if not self.overlay.exists():
            command('qemu-img', 'create', '-q', '-f', 'qcow2', '-F', 'raw', '-b', os_image, self.overlay)
        self.socket_path = folder/'qmp.sock'
        self.socket_path.unlink(missing_ok=True)
        args = ['-M', 'virt', '-cpu', 'cortex-a72', '-m', '1024', '-smp', '2',
                '-nographic', '-nic', 'none', '-monitor', 'none', '-kernel', str(images/'Image'),
                '-append', 'root=/dev/vda2 rootwait ro console=ttyAMA0,115200 loglevel=6',
                '-drive', f'file={self.overlay},format=qcow2,if=none,id=os',
                '-device', 'virtio-blk-device,drive=os', '-device', 'qemu-xhci,id=xhci',
                '-qmp', f'unix:{self.socket_path},server=on,wait=off']
        self.log.write('COMMAND '+shlex.join(['qemu-system-aarch64', *args])+'\n')
        started = time.monotonic()
        self.child = pexpect.spawn('qemu-system-aarch64', args, encoding='utf-8', codec_errors='replace',
                                   timeout=60, echo=False, dimensions=(40, 300))
        self.child.logfile_read = self.log
        self.child.expect('mebs login:')
        self.child.sendline('root')
        self.child.expect(r'(?:~ )?# ')
        self.child.sendline("stty -echo; export PS1=$(printf 'MEBS_'; printf 'TEST# ')")
        self.child.expect(PROMPT)
        self.ready = True
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(15)
        self.sock.connect(str(self.socket_path))
        self.stream = self.sock.makefile('rwb', buffering=0)
        json.loads(self.stream.readline())
        self.qmp('qmp_capabilities')
        state = self.wait({'READY'}, 20)
        self.boot_seconds = time.monotonic()-started
        self.boot_evidence = self.py("import os,pathlib; print({'pid1':pathlib.Path('/proc/1/comm').read_text().strip(),'settings_mounted':os.path.ismount('/var/lib/mebs'),'status':pathlib.Path('/run/mebs/status.json').read_text(),'uptime':pathlib.Path('/proc/uptime').read_text()})")
        self.log.write(f'FULL_INIT_AUTO_READY wall_seconds={self.boot_seconds:.3f} {state}\n')

    def qmp(self, name, args=None):
        return old.qmp_execute(self.sock, self.stream, name, args)

    def shell(self, cmd, timeout=60):
        self.child.sendline(cmd)
        self.child.expect(PROMPT, timeout=timeout)
        return self.child.before

    def py(self, code, timeout=60):
        encoded = base64.b64encode(code.encode()).decode()
        return self.shell("PYTHONPATH=/usr/lib/mebs python3 -c "+shlex.quote(f"import base64;exec(base64.b64decode('{encoded}'))"), timeout)

    def json(self, expression):
        output = self.py('import json; print("MEBS_JSON"+json.dumps('+expression+', ensure_ascii=True))')
        matches = re.findall(r'MEBS_JSON([^\r\n]+)', output)
        if not matches:
            raise RuntimeError('No guest JSON: '+output[-1500:])
        return json.loads(matches[-1])

    def status(self):
        state = self.json("json.load(open('/run/mebs/status.json')) if __import__('os').path.exists('/run/mebs/status.json') else {'state':'BOOTING'}")
        if not self.events or self.events[-1]['status'] != state:
            self.events.append({'monotonic':time.monotonic(), 'status':state})
        return state

    def wait(self, states, timeout=90, tolerate_errors=False):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            try:
                state = self.status()
            except RuntimeError:
                time.sleep(.2)
                continue
            if state.get('state') in states:
                return state
            if not tolerate_errors and state.get('state') in {'ERROR','CANCELLED','AMBIGUOUS'}:
                raise RuntimeError('Unexpected state '+str(state))
            time.sleep(.1)
        raise TimeoutError(f'Expected {states}, last={state}')

    def attach(self, path, role, *, readonly=False, throttle=False):
        self.qmp('blockdev-add', {'driver':'file','filename':str(path),'node-name':role+'-file','read-only':readonly})
        self.qmp('blockdev-add', {'driver':'raw','file':role+'-file','node-name':role+'-raw','read-only':readonly})
        drive = role+'-raw'
        if throttle:
            self.qmp('object-add', {'qom-type':'throttle-group','id':role+'-limit','limits':{'bps-total':2097152}})
            self.qmp('blockdev-add', {'driver':'throttle','throttle-group':role+'-limit','file':drive,'node-name':role+'-slow','read-only':readonly})
            drive = role+'-slow'
        self.qmp('device_add', {'driver':'usb-storage','drive':drive,'bus':'xhci.0','id':role+'-usb'})
        return drive

    def reattach(self, role, drive):
        self.qmp('device_add', {'driver':'usb-storage','drive':drive,'bus':'xhci.0','id':role+'-usb'})

    def detach(self, role):
        self.qmp('device_del', {'id':role+'-usb'})

    def inspect_target(self, writable=False):
        self.shell('mkdir -p /run/inspect; mount -t ext4 -o '+('rw' if writable else 'ro')+' /dev/sda /run/inspect')
        return self.json("__import__('subprocess').check_output(['mount'],text=True)")

    def manifests(self):
        return self.json("[{'job':str(p),'manifest':json.load(open(p/'manifest.json')),'files':{str(f.relative_to(p/'data')):__import__('hashlib').sha256(f.read_bytes()).hexdigest() for f in (p/'data').rglob('*') if f.is_file()},'dirs':sorted(str(f.relative_to(p/'data')) for f in (p/'data').rglob('*') if f.is_dir())} for p in __import__('pathlib').Path('/run/inspect').glob('mebs-backup-*')]")

    def capture(self, destination):
        output = self.py("import base64,io,json,pathlib; from mebs.controls import Controls; from mebs.settings import SettingsStore; from mebs.runtime800 import Sensors; from mebs.ui800 import render; c=Controls(SettingsStore(pathlib.Path('/var/lib/mebs/settings.json'))); c.update(json.load(open('/run/mebs/status.json'))); Sensors(json.load(open('/etc/mebs/hardware.json')),c).read(); b=io.BytesIO(); render(c).save(b,format='PNG'); print('MEBS_PNG'+base64.b64encode(b.getvalue()).decode()+'END_PNG')")
        payload = re.search(r'MEBS_PNG(.*?)END_PNG', output, re.S)
        if not payload:
            raise RuntimeError('Screenshot not returned: '+output[-1000:])
        destination.write_bytes(base64.b64decode(payload[1]))

    def kill(self):
        os.kill(self.child.pid, signal.SIGKILL)
        self.child.expect(pexpect.EOF, timeout=15)

    def close(self):
        if hasattr(self, 'child') and self.child.isalive():
            try:
                if self.ready:
                    self.shell('cat /run/mebs/service.log; mount', timeout=5)
                    self.child.sendline('poweroff -f')
                    self.child.expect(pexpect.EOF, timeout=20)
                else:
                    self.child.close(force=True)
            finally:
                if self.child.isalive():
                    self.child.close(force=True)
        for name in ('stream','sock','log'):
            handle = getattr(self,name,None)
            if handle is not None:
                handle.close()


def test(case, images, os_image, temp, logs, screenshots):
    folder = temp/case
    folder.mkdir()
    target, source, expected, dirs, existing = fixtures(folder, empty=case=='T10',
        large=case in {'T04','T05','T06','T14'}, short=case=='T03', bad_target=case=='T09')
    source_hash = sha(source)
    (logs/f'{case}.fixture.json').write_text(json.dumps({'files':expected,'directories':dirs,'source_image_sha256':source_hash,'existing_target':existing},ensure_ascii=False,indent=2))
    guest = None
    result = {'id':case,'status':'FAIL','executed':True}
    try:
        guest = Guest.__new__(Guest)
        guest.__init__(images, os_image, folder, logs, case)
        result['boot_seconds'] = guest.boot_seconds
        result['autostart'] = True
        td = guest.attach(target, 'target', readonly=case=='T08')
        if case in {'T08','T09'}:
            status = guest.wait({'ERROR'}, 30)
            result['state'] = status
            assert not status.get('safe_to_remove') and status.get('copied_bytes',0)==0, status
            assert ('읽기 전용' if case=='T08' else 'ext4') in status.get('error',''), status
            result.update(status='PASS', detail='Invalid destination rejected when first inserted, before the camera source was connected')
            return result
        guest.wait({'WAITING_SOURCE'})
        sd = guest.attach(source, 'source', readonly=True, throttle=case in {'T04','T05','T06','T14'})
        if case == 'T14':
            deadline = time.monotonic() + 60
            while True:
                active = guest.status()
                if active.get('state') == 'COPYING' and active.get('copied_bytes', 0) >= 1048576:
                    break
                if active.get('state') in {'ERROR', 'CANCELLED', 'SAFE_TO_REMOVE'} or time.monotonic() >= deadline:
                    raise AssertionError('Copy did not remain active before normal shutdown: '+str(active))
                time.sleep(.1)
            overlay = guest.overlay
            guest.child.sendline('poweroff')
            guest.child.expect('Power down', timeout=90)
            guest.child.expect(pexpect.EOF, timeout=30)
            old_events = guest.events[:]
            guest.close()
            guest = Guest(images, os_image, folder, logs, case+'-reboot', overlay=overlay)
            guest.events = old_events + guest.events
            guest.attach(target, 'target')
            recovered = guest.wait({'RECOVERY_REQUIRED','ERROR'}, 40)
            if recovered['state'] == 'RECOVERY_REQUIRED':
                guest.capture(screenshots/'T14-guest-recovery-required.png')
            guest.inspect_target()
            pending = guest.json("[p.name for p in __import__('pathlib').Path('/run/inspect').glob('.mebs-pending-*')]")
            guest.shell('umount /run/inspect')
            assert recovered['state'] == 'RECOVERY_REQUIRED' and pending and not recovered.get('safe_to_remove'), recovered
            guest.attach(source, 'source', readonly=True)
            retried = guest.wait({'SAFE_TO_REMOVE','ERROR'}, 180)
            assert retried['state'] == 'SAFE_TO_REMOVE' and retried.get('safe_to_remove'), retried
            guest.inspect_target()
            jobs = guest.manifests()
            assert len(jobs) == 1 and jobs[0]['files'] == expected, jobs
            guest.shell('umount /run/inspect')
            guest.capture(screenshots/'T14-guest-retry-safe-to-remove.png')
            result.update(status='PASS', state=recovered, retry_state=retried, pending=pending,
                          detail='Normal shutdown during active copy left pending job; reboot warned; reconnected source completed a new verified backup',
                          reboot_seconds=guest.boot_seconds)
            return result
        if case in {'T04','T05','T06'}:
            guest.wait({'COPYING'}, 90)
            if case=='T06':
                guest.kill()
                events = guest.events[:]
                guest.close()
                guest = Guest.__new__(Guest)
                guest.__init__(images, os_image, folder, logs, case+'-reboot')
                guest.attach(target, 'target')
                status = guest.wait({'RECOVERY_REQUIRED','WAITING_SOURCE','ERROR'})
                if status['state'] == 'RECOVERY_REQUIRED':
                    guest.capture(screenshots/'T06-guest-recovery-required.png')
                guest.inspect_target()
                pending = guest.json("[str(p) for p in __import__('pathlib').Path('/run/inspect').glob('.mebs-pending-*')]")
                guest.shell('umount /run/inspect')
                if pending and status['state'] == 'RECOVERY_REQUIRED':
                    guest.attach(source, 'source', readonly=True)
                    retry = guest.wait({'SAFE_TO_REMOVE','ERROR'}, 180)
                    if retry['state'] == 'SAFE_TO_REMOVE':
                        guest.inspect_target()
                        jobs = guest.manifests()
                        assert len(jobs) == 1 and jobs[0]['files'] == expected, jobs
                        result.update(status='PASS', detail='VM SIGKILL left pending job; boot displayed recovery warning; reconnected source made a new verified backup', pending=pending, state=retry)
                    else:
                        result.update(status='FAIL', detail='Recovery warning shown but retry failed', pending=pending, state=retry)
                else:
                    result.update(status='FAIL', detail='VM SIGKILL pending job not identified on reboot', pending=pending, state=status)
                guest.events = events+guest.events
                return result
            guest.detach('target' if case=='T04' else 'source')
        status = guest.wait({'SAFE_TO_REMOVE','ERROR','CANCELLED'}, 120)
        result['state'] = status
        if case=='T10':
            guest.capture(screenshots/'T10-guest-empty-source.png')
        if case in {'T03','T04','T05'}:
            assert status['state']=='ERROR' and not status.get('safe_to_remove'), status
            result.update(status='PASS',detail='Actual guest rejection/error; never marked safe')
        elif case=='T10':
            good = status['state']=='ERROR' and '백업할 파일 없음' in status.get('error','') and not status.get('safe_to_remove')
            result.update(status='PASS' if good else 'FAIL',detail='Empty source rejected with a no-files message' if good else 'Empty source did not produce a no-files warning')
        else:
            assert status['state']=='SAFE_TO_REMOVE' and status.get('safe_to_remove'), status
            guest.inspect_target()
            jobs = guest.manifests()
            assert len(jobs)==1 and jobs[0]['files']==expected and jobs[0]['dirs']==dirs, jobs
            observed = guest.json("{p.name:__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in __import__('pathlib').Path('/run/inspect').iterdir() if p.is_file() and p.name!='.mebs.lock'}")
            assert observed == existing, observed
            result.update(status='PASS',detail='Every file hash and directory match; existing target data preserved',files=len(expected),bytes=status['total_bytes'])
            guest.shell('umount /run/inspect')
            if case=='T01':
                guest.capture(screenshots/'T01-guest-safe-to-remove.png')
            if case=='T13':
                # The VM has no configured touchscreen. Exercise the normal
                # guest OS shutdown and next boot, not the button/fade path.
                overlay = guest.overlay
                guest.child.sendline('poweroff')
                guest.child.expect('Power down', timeout=30)
                guest.child.expect(pexpect.EOF, timeout=30)
                old_events = guest.events[:]
                guest.close()
                guest = Guest(images, os_image, folder, logs, case+'-reboot', overlay=overlay)
                guest.events = old_events + guest.events
                restarted = guest.status()
                assert restarted['state'] == 'READY' and not restarted['source_connected'] and not restarted['target_connected'], restarted
                result.update(detail='Guest normal OS poweroff reached Power down; persistent OS rebooted to READY without USB', reboot_state=restarted, reboot_seconds=guest.boot_seconds)
            if case=='T02':
                guest.detach('source'); guest.detach('target')
                guest.wait({'READY'}, tolerate_errors=True)
                guest.reattach('target',td); guest.wait({'WAITING_SOURCE'})
                guest.reattach('source',sd); second=guest.wait({'SAFE_TO_REMOVE'})
                guest.inspect_target(); count=len(guest.manifests())
                reused = count==1 and second.get('copied_bytes')==0 and second.get('deduplicated') is True
                result.update(status='PASS' if reused else 'FAIL',detail=f'Identical rebackup left {count} committed jobs; copied_bytes={second.get("copied_bytes")}; deduplicated={second.get("deduplicated")}',jobs=count)
            if case=='T07':
                guest.inspect_target(writable=True)
                output=guest.py("from pathlib import Path; from mebs.backup import verify,BackupError; p=next(Path('/run/inspect').glob('mebs-backup-*')); f=next((p/'data').rglob('*.XML')); b=bytearray(f.read_bytes()); b[0]^=1; f.write_bytes(b);\ntry: verify(p); print('TAMPER_NOT_DETECTED')\nexcept BackupError as e: print('TAMPER_DETECTED',str(e))")
                assert 'TAMPER_DETECTED' in output and 'TAMPER_NOT_DETECTED' not in output, output
                result['detail']='Actual copied XML byte altered in guest; explicitly invoked production verify rejected hash mismatch (not autonomous post-completion monitoring)'
    finally:
        result['source_unchanged'] = sha(source)==source_hash
        if guest:
            (logs/f'{case}.events.json').write_text(json.dumps(guest.events,ensure_ascii=False,indent=2))
            guest.close()
        if not result['source_unchanged']:
            raise AssertionError('Source image was modified')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images',type=Path,default=ROOT/'output/pi4-v2-recovery-v4-20261019/images')
    parser.add_argument('--prepared-os',type=Path,help='separate QEMU raw image with vda3 fstab adaptation')
    parser.add_argument('--cases',default='T01,T02,T03,T04,T05,T06,T07,T08,T09,T10,T11,T12')
    args=parser.parse_args()
    cases = [case.strip() for case in args.cases.split(',')]
    supported = {f'T{number:02d}' for number in range(1, 15)}
    if not cases or any(case not in supported for case in cases) or len(cases) != len(set(cases)):
        parser.error('--cases must be unique IDs from T01 through T14')
    images=args.images.resolve()
    stamp=time.strftime('%Y%m%d-%H%M%S')
    evidence=HERE/'runs'/stamp
    logs=evidence/'logs'; screenshots=evidence/'screenshots'
    logs.mkdir(parents=True); screenshots.mkdir()
    original_hash=sha(images/'sdcard.img')
    results=[]
    with tempfile.TemporaryDirectory(prefix='mebs-v2-suite-') as path:
        temp=Path(path)
        os_image=args.prepared_os.resolve() if args.prepared_os else prepare_os(images,temp)
        if not os_image.is_file() or os_image.is_block_device():
            raise SystemExit('Prepared OS must be a regular image file')
        for case in cases:
            started=time.monotonic()
            if case == 'T12':
                result={'id':'T12','status':'BLOCKED','executed':False,
                        'detail':'Shipped V2 has no manual formatter or format-approval UI. No SD format executed.'}
            else:
                try:
                    result=test(case,images,os_image,temp,logs,screenshots)
                except AssertionError as exc:
                    result={'id':case,'status':'FAIL','executed':True,'error':repr(exc)}
                except Exception as exc:
                    result={'id':case,'status':'BLOCKED','executed':True,'error':repr(exc)}
            result['elapsed_seconds']=round(time.monotonic()-started,3)
            results.append(result)
            (evidence/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
            print(json.dumps(result,ensure_ascii=False),flush=True)
    assert sha(images/'sdcard.img')==original_hash, 'Original image changed'
    (evidence/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    (evidence/'environment.json').write_text(json.dumps({'image':str(images/'sdcard.img'),'sha256':original_hash,'original_unchanged':True,'qemu':command('qemu-system-aarch64','--version').splitlines()[0],'adaptation':'test copy fstab mmcblk0p3 -> vda3 only','machine':'virt / cortex-a72 / 1024MiB / 2 vCPU','hardware_tested':False},indent=2))
    print('EVIDENCE '+str(evidence),flush=True)
    return 0 if all(x['status']=='PASS' for x in results) else 1


if __name__=='__main__':
    raise SystemExit(main())
