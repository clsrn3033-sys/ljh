#!/usr/bin/env python3
"""Host-only power-on → real temporary backup → queued shutdown GIF.

No physical media, actual poweroff, or GPIO is accessed. Boot checks and
display are simulated; copied bytes and SHA-256 comparison are real.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from mebs.appliance import run_job
from mebs.backup import verify
from mebs.boot_animation import frames as boot_frames, render as boot_render
from mebs.controls import Controls
from mebs.runtime800 import show_shutdown
from mebs.settings import SettingsStore
from mebs.ui800 import render as ui_render
from test_appliance import FakeMounts, disk


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def label(frame):
    frame = frame.copy()
    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, 216, 19), fill='black')
    draw.text((5, 3), 'HOST SIMULATION / REAL COPY', fill='#58dfff')
    return frame


class PreviewScreen:
    def __init__(self):
        self.frames = []

    def show(self, image):
        self.frames.append(image.copy())


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    snapshots = output / 'screenshots'
    snapshots.mkdir(exist_ok=True)
    movie, durations, phases = [], [], []

    def add(name, image, duration=300):
        image = image.copy() if name == 'POWER_OFF' else label(image)
        movie.append(image)
        durations.append(duration)
        if name not in phases:
            image.save(snapshots / f'{len(phases):02d}-{name}.png')
            phases.append(name)

    for percent, opacity, state, caption in boot_frames([True] * 5, steps=2):
        boot = boot_render(percent, opacity=opacity, state=state, caption=caption)
        resized = boot.resize((800, 450), Image.Resampling.LANCZOS)
        frame = Image.new('RGB', (800, 480), 'black')
        frame.paste(resized, (0, 15))
        add('BOOT_LOADING' if state != 'ready' else 'BACKUP_READY', frame, 90)

    with tempfile.TemporaryDirectory(prefix='mebs-power-cycle-') as path:
        root = Path(path)
        source, target = root / 'source', root / 'target'
        (source / 'DCIM').mkdir(parents=True); target.mkdir()
        data = {
            'DCIM/photo.JPG': b'JPEG sample\x00' * 40000,
            'DCIM/clip.MP4': b'video sample\x00' * 30000,
            'DCIM/clip.XML': b'<clip>metadata</clip>\n',
        }
        for name, content in data.items():
            (source / name).write_bytes(content)
        original = {name: digest(source / name) for name in data}
        c = Controls(SettingsStore(root / 'settings.json'))
        c.update({'state': 'WAITING_SOURCE', 'target_connected': True, 'source_connected': False})
        add('STORAGE_READY', ui_render(c), 450)
        c.update({'state': 'SCANNING', 'target_connected': True, 'source_connected': True})
        add('SD_READY', ui_render(c), 450)
        assert c.begin_job()
        queued = False
        seen = set()
        def emit(status):
            nonlocal queued
            c.update(status)
            phase = status['state']
            if phase in {'COPYING', 'VERIFYING', 'UNMOUNTING', 'SAFE_TO_REMOVE'} and phase not in seen:
                seen.add(phase)
                add(phase, ui_render(c), 500)
            if phase == 'COPYING' and status.get('copied_bytes', 0) and not queued:
                queued = True
                c.gesture((400, 10), (400, 110))
                c.gesture((750, 40), (750, 40))
                add('POWER_CONFIRM_DURING_COPY', ui_render(c), 500)
                assert c.gesture((580, 290), (580, 290)) == 'shutdown-confirmed'
                assert not c.shutdown_ready()
                add('SHUTDOWN_QUEUED', ui_render(c), 500)
                c.panel = False

        mounts = FakeMounts(source, target)
        result = run_job(disk('sdb', 'exfat'), disk('sda'), emit, lambda: False,
                         mounts, current=lambda: [disk('sda'), disk('sdb', 'exfat')])
        c.finish_job(result)
        assert queued and c.shutdown_ready() and result['state'] == 'SAFE_TO_REMOVE'
        verified = verify(result['job'])
        assert len(verified['files']) == len(data)
        assert {name: digest(source / name) for name in data} == original
        assert {name: digest(Path(result['job']) / 'data' / name) for name in data} == original
        assert 'close' in mounts.calls
        add('SAFE_TO_REMOVE', ui_render(c), 600)
        screen = PreviewScreen()
        order = []
        def poweroff_preview():
            order.append('fade')
            show_shutdown(screen, sleeper=lambda _: None)
            order.append('poweroff simulated')
        assert c.perform_shutdown(lambda: order.append('sync'),
                                  lambda _: order.append('log'), poweroff_preview)
        assert order == ['sync', 'log', 'sync', 'fade', 'poweroff simulated']
        for index, frame in enumerate(screen.frames):
            add('SHUTDOWN_FADE' if index == 0 else 'POWER_OFF' if index == len(screen.frames)-1
                else 'SHUTDOWN_FADE', frame, 600 if index == len(screen.frames)-1 else 90)
        assert screen.frames[-1].getbbox() is None
        restarted = Controls(SettingsStore(root / 'settings.json'))
        assert restarted.state['state'] == 'READY' and not restarted.shutdown_pending
        for percent, opacity, state, caption in boot_frames([True] * 5, steps=1):
            boot = boot_render(percent, opacity=opacity, state=state, caption=caption)
            resized = boot.resize((800, 450), Image.Resampling.LANCZOS)
            frame = Image.new('RGB', (800, 480), 'black')
            frame.paste(resized, (0, 15))
            add('REBOOT_READY' if state == 'ready' else 'REBOOT_LOADING', frame, 120)
        report = {
            'mode': 'HOST SIMULATION / REAL TEMPORARY FILE COPY',
            'hardware_tested': False,
            'os_poweroff_executed': False,
            'source_sha256': original,
            'destination_sha256': {name: digest(Path(result['job']) / 'data' / name) for name in data},
            'backup_state': result['state'],
            'safe_to_remove': result['safe_to_remove'],
            'queued_during_copy': queued,
            'shutdown_order': order,
            'restarted_ready': restarted.state['state'] == 'READY',
            'phases': phases,
        }
    movie[0].save(output / 'power-cycle.gif', save_all=True,
                  append_images=movie[1:], duration=durations, loop=0, optimize=True)
    (output / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(json.dumps(build(parser.parse_args().output), ensure_ascii=False, indent=2))
