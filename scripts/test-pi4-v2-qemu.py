#!/usr/bin/env python3
"""Disposable end-to-end Pi4 image test on QEMU virt (USB target + SD source).

Uses only temporary regular files under /tmp. This does not emulate Pi firmware,
DSI, GPIO or electrical behavior, and it never opens a host block device.
Requires the host's existing pexpect module; installs nothing.
"""
from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time as monotonic_time

import pexpect

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGES = ROOT / 'output/pi4-v2-dsi-800x480-20261018/images'
PROMPT = r'~ # '


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def create_fixtures(directory: Path):
    target = directory / 'external-ext4.img'
    source = directory / 'camera-vfat.img'
    target.touch()
    with target.open('r+b') as f:
        f.truncate(128 * 1024 * 1024)
    run('mkfs.ext4', '-q', '-F', str(target))
    run('mkfs.vfat', '-C', str(source), '32768', stdout=subprocess.DEVNULL)
    run('mmd', '-i', str(source), '::DCIM')
    payload = b'<?xml version="1.0"?><clip id="QEMU-TEST">MEBS fixture</clip>\n'
    sample = directory / 'C0001.XML'
    sample.write_bytes(payload)
    run('mcopy', '-i', str(source), str(sample), '::DCIM/C0001.XML')
    return target, source, hashlib.sha256(payload).hexdigest()


def qmp_execute(sock, stream, name, arguments=None):
    request = {'execute': name}
    if arguments is not None:
        request['arguments'] = arguments
    stream.write((json.dumps(request) + '\r\n').encode())
    while True:
        line = stream.readline()
        if not line:
            raise RuntimeError('QEMU QMP socket closed')
        reply = json.loads(line)
        if 'return' in reply:
            return reply['return']
        if 'error' in reply:
            raise RuntimeError(f'QMP {name} failed: {reply["error"]}')


def boot_qemu(images: Path, target: Path, case_dir: Path, log):
    qmp_path = case_dir / 'qmp.sock'
    overlay = case_dir / 'os.qcow2'
    run('qemu-img', 'create', '-q', '-f', 'qcow2', '-F', 'raw', '-b',
        str(images / 'sdcard.img'), str(overlay))
    args = [
        '-M', 'virt', '-cpu', 'cortex-a72', '-m', '1024', '-smp', '2',
        '-nographic', '-nic', 'none', '-monitor', 'none',
        '-kernel', str(images / 'Image'),
        '-append', 'root=/dev/vda2 rootwait ro console=ttyAMA0,115200 init=/bin/sh loglevel=4',
        '-drive', f'file={overlay},format=qcow2,if=none,id=os',
        '-device', 'virtio-blk-device,drive=os',
        '-qmp', f'unix:{qmp_path},server,nowait',
        '-device', 'qemu-xhci,id=xhci',
        '-drive', f'file={target},format=raw,if=none,id=external',
        '-device', 'usb-storage,bus=xhci.0,drive=external',
    ]
    child = pexpect.spawn('qemu-system-aarch64', args, encoding='utf-8', timeout=60,
                          echo=False, dimensions=(30, 120))
    child.logfile_read = log
    child.expect(PROMPT)
    child.sendline('mount -t proc proc /proc; mount -t sysfs sysfs /sys; '
                   'mount -t devtmpfs devtmpfs /dev; mount -t tmpfs tmpfs /run; '
                   'mount -t tmpfs tmpfs /tmp; mount /dev/vda3 /var/lib/mebs; '
                   'echo MEBS_QEMU_READY')
    child.expect('MEBS_QEMU_READY')
    child.expect(PROMPT)
    child.sendline('/etc/init.d/S50mebs start; sleep 4; cat /run/mebs/status.json')
    child.expect(PROMPT)
    text = child.before
    if 'WAITING_SOURCE' not in text:
        child.sendline('cat /run/mebs/service.log 2>&1; ls -la /run/mebs; mount; cat /etc/mebs/hardware.json')
        child.expect(PROMPT)
        text += child.before
        raise RuntimeError('single target did not enter WAITING_SOURCE: ' + text[-1000:])

    qmp = socket.socket(socket.AF_UNIX)
    qmp.settimeout(10)
    qmp.connect(str(qmp_path))
    stream = qmp.makefile('rwb', buffering=0)
    greeting = json.loads(stream.readline())
    if 'QMP' not in greeting:
        raise RuntimeError('missing QMP greeting')
    qmp_execute(qmp, stream, 'qmp_capabilities')
    return child, qmp, stream, qmp_path


def guest_status(child):
    child.sendline('cat /run/mebs/status.json')
    child.expect(PROMPT)
    matches = re.findall(r'\{[^{}\r\n]+\}', child.before)
    for candidate in reversed(matches):
        try:
            value = json.loads(candidate)
            if 'state' in value:
                return value
        except json.JSONDecodeError:
            pass
    return None


def test_once(images: Path, log_path: Path):
    case_dir = Path(tempfile.mkdtemp(prefix='mebs-pi4-v2-e2e-'))
    child = qmp = stream = None
    try:
        target, source, expected_hash = create_fixtures(case_dir)
        source_hash_before = hashlib.sha256(source.read_bytes()).hexdigest()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('w', buffering=1) as log:
            log.write(f'UTC start: {datetime.now().astimezone().isoformat()}\n')
            log.write(f'Image: {images / "sdcard.img"}\n')
            child, qmp, stream, qmp_path = boot_qemu(images, target, case_dir, log)
            qmp_execute(qmp, stream, 'blockdev-add', {
                'driver': 'file', 'filename': str(source), 'node-name': 'camera-file',
                'read-only': True,
            })
            qmp_execute(qmp, stream, 'blockdev-add', {
                'driver': 'raw', 'file': 'camera-file', 'node-name': 'camera-disk',
                'read-only': True,
            })
            qmp_execute(qmp, stream, 'device_add', {
                'driver': 'usb-storage', 'drive': 'camera-disk',
                'bus': 'xhci.0', 'id': 'camera-usb',
            })
            deadline = monotonic_time.monotonic() + 60
            status = None
            while monotonic_time.monotonic() < deadline:
                monotonic_time.sleep(1)
                status = guest_status(child)
                if status and status.get('state') in ('SAFE_TO_REMOVE', 'ERROR', 'AMBIGUOUS'):
                    break
            if not status or status.get('state') != 'SAFE_TO_REMOVE' or status.get('safe_to_remove') is not True:
                raise RuntimeError(f'backup did not reach safe removal: {status}')
            if (status.get('verified_files') != 1 or status.get('total_files') != 1
                    or status.get('copied_bytes') != status.get('total_bytes')):
                raise RuntimeError(f'expected one copied and verified file: {status}')

            child.sendline('mkdir -p /run/verify; mount -t ext4 -o ro /dev/sda /run/verify; '
                           'find /run/verify -type f -name C0001.XML -exec sha256sum {} +')
            child.expect(PROMPT)
            matches = re.findall(r'([0-9a-f]{64})\s+([^\r\n]*C0001\.XML)', child.before)
            if not matches or matches[-1][0] != expected_hash:
                raise RuntimeError(f'copied XML SHA-256 mismatch: {child.before[-1000:]}')
            if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash_before:
                raise RuntimeError('virtual source SD image changed during backup')
            child.sendline('umount /run/verify; /etc/init.d/S50mebs stop; poweroff -f')
            child.expect(pexpect.EOF, timeout=15)
            qmp.close(); qmp = None
            result = {
                'status': 'PASS', 'state': status['state'], 'verified_files': 1,
                'source_sha256': expected_hash, 'target_sha256': matches[-1][0],
                'source_unchanged': True, 'finished': datetime.now().astimezone().isoformat(),
                'log': str(log_path),
            }
            log.write('RESULT ' + json.dumps(result, ensure_ascii=False) + '\n')
            return result
    finally:
        if qmp is not None:
            qmp.close()
        if child is not None and child.isalive():
            try:
                child.sendline('poweroff -f')
                child.expect(pexpect.EOF, timeout=10)
            except Exception:
                child.close(force=True)
        shutil.rmtree(case_dir, ignore_errors=True)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images', type=Path, default=DEFAULT_IMAGES)
    parser.add_argument('--log-dir', type=Path, default=ROOT / 'TEST_LOGS')
    parser.add_argument('--repeat-until', metavar='HH:MM')
    parser.add_argument('--interval-minutes', type=int, default=30)
    return parser.parse_args()


def main():
    args = parse_args()
    images = args.images.resolve()
    if not (images / 'Image').is_file() or not (images / 'sdcard.img').is_file():
        raise SystemExit(f'Built Pi4 image is missing under {images}')
    until = None
    if args.repeat_until:
        hour, minute = map(int, args.repeat_until.split(':', 1))
        now = datetime.now().astimezone()
        until = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if until <= now:
            until += timedelta(days=1)
    run_number = 0
    while True:
        # Keep wall-clock scheduling separate from monotonic duration timing.
        # monotonic() has an arbitrary origin and must not be converted to an
        # epoch timestamp when calculating the next scheduled run.
        run_started_at = datetime.now().astimezone()
        run_number += 1
        stamp = datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
        log = args.log_dir / f'v2-qemu-e2e-{run_number:02d}-{stamp}.log'
        try:
            result = test_once(images, log)
        except Exception as exc:
            result = {'status': 'FAIL', 'error': repr(exc), 'log': str(log),
                      'finished': datetime.now().astimezone().isoformat()}
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open('a') as output:
                output.write('RESULT ' + json.dumps(result, ensure_ascii=False) + '\n')
        print(json.dumps({'run': run_number, **result}, ensure_ascii=False), flush=True)
        if until is None:
            break
        now = datetime.now().astimezone()
        next_start = run_started_at + timedelta(minutes=args.interval_minutes)
        if now >= until or next_start >= until:
            break
        monotonic_time.sleep(max(0, (next_start - now).total_seconds()))


if __name__ == '__main__':
    main()
