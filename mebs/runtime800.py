"""Opt-in dedicated image runtime. UI, sensors and backup have separate loops.

Mock preview never mounts, changes the host clock, poweroffs or touches hardware.
Live entry requires root + image marker, including when headless.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
from threading import Event, Thread
import time

from .appliance import BackupError, Mounts, display_paths, inventory, run_job, sync_filesystem
from .controls import Controls, append_log
from .devices import Roles
from .sensors import BatteryGuard, BH1750, I2C, INA226, Reading, cpu_temperature, estimate, validate_addresses
from .settings import SettingsStore


class ObservedMounts(Mounts):
    def __init__(self, control, **kwargs):
        super().__init__(**kwargs)
        self.control = control
        self.source = None

    def mount(self, disk, selected, role):
        path = super().mount(disk, selected, role)
        if role == 'source':
            self.source = path
        elif self.source is not None:
            from .preflight import capacity, require_space
            values = capacity(self.source, path)
            with self.control.lock:
                self.control.state.update(values)
            require_space(values)
        return path


class Worker:
    def __init__(self, control, stop, mounts, current=inventory, job=run_job, sleeper=time.sleep):
        self.c, self.stop, self.mounts = control, stop, mounts
        self.current, self.job, self.sleep = current, job, sleeper
        self.roles, self.latched = Roles(), False

    def once(self):
        try:
            disks = self.current()
            ids = [d['token'] for d in disks]
            if not ids and not self.mounts.mounted:
                self.latched = False
            assigned = self.roles.observe(ids)
            if self.latched:
                return
            if assigned['state'] == 'ROLES_ASSIGNED':
                if not self.c.begin_job():
                    return  # retry after valid voltage; do not latch unstarted job
                self.latched = True
                try:
                    self.sleep(1)  # allow partition enumeration; then revalidate
                    fresh = {d['token']: d for d in self.current()}
                    if set(fresh) != set(ids):
                        raise BackupError('장치 연결이 변경되었습니다. 다시 연결하세요.')
                    result = self.job(fresh[assigned['source']], fresh[assigned['target']],
                                      self.c.update, self.stop.is_set, self.mounts, current=self.current)
                except Exception as exc:
                    result = dict(state='ERROR', error=str(exc), safe_to_remove=False)
                finally:
                    # A run_job exception also closes mounts before leaving the worker.
                    try:
                        self.mounts.close()
                    except Exception as exc:
                        result = dict(state='ERROR', error=str(exc), safe_to_remove=False)
                self.c.finish_job(result)
            else:
                with self.c.lock:
                    if not self.c.shutdown_pending and not self.c.shutting_down:
                        self.c.update(dict(state={'WAITING_FOR_TARGET': 'READY', 'WAITING_FOR_SOURCE': 'WAITING_SOURCE'}.get(assigned['state'], assigned['state']),
                                           target_connected=assigned['target'] is not None,
                                           source_connected=assigned['source'] is not None))
        except Exception as exc:
            self.latched = True
            self.c.update(dict(state='ERROR', error=str(exc), safe_to_remove=False))

    def run(self):
        try:
            while not self.stop.is_set():
                self.once()
                self.stop.wait(.25)
        finally:
            try:
                self.mounts.close()
            except Exception as exc:
                self.c.update(dict(state='ERROR', error=str(exc), safe_to_remove=False))


class Sensors:
    def __init__(self, config, control):
        validate_addresses(config)
        self.config, self.c = config, control
        self.handles = []
        self.ina = self.bh = None
        self.init_errors = []
        for name, address, factory in [('ina226', 0x40, INA226), ('bh1750', 0x23, BH1750)]:
            item = config.get(name, {})
            if not item.get('enabled'):
                continue
            try:
                bus = I2C(config.get('i2c_bus', '/dev/i2c-1'), item.get('address', address))
                self.handles.append(bus)
                device = factory(bus, item.get('shunt_ohms'), item.get('discharge_polarity', 1)) if name == 'ina226' else factory(bus)
                if name == 'ina226':
                    self.ina = device
                else:
                    self.bh = device
            except (OSError, ValueError) as exc:
                self.init_errors.append(name + ': ' + str(exc))

    def read(self):
        r = Reading()
        errors = list(self.init_errors)
        for name, operation in [('CPU', lambda: setattr(r, 'cpu_c', cpu_temperature())),
                                ('INA226', lambda: self._battery(r)),
                                ('BH1750', lambda: setattr(r, 'lux', self.bh.read()) if self.bh else None)]:
            try:
                operation()
            except (OSError, ValueError) as exc:
                errors.append(name + ': ' + str(exc))
        r.error = '; '.join(errors) or ('배터리/조도 센서 미설정' if not self.ina or not self.bh else '')
        with self.c.lock:
            self.c.reading = r

    def _battery(self, r):
        if self.ina:
            r.voltage, r.current_a = self.ina.read()
            item = self.config.get('ina226', {})
            r.percent, r.runtime_hours = estimate(r.voltage, r.current_a, item.get('ocv_curve'), item.get('capacity_ah'))

    def run(self, stop):
        try:
            while not stop.is_set():
                self.read()
                stop.wait(1)
        finally:
            for handle in self.handles:
                handle.close()


def restore_rtc(config):
    # Kernel DS3231 driver + hwclock owns address 0x68. No direct competing I2C reads.
    rtc = config.get('ds3231', {})
    if not rtc.get('enabled'):
        return 'RTC 미설정'
    device = rtc.get('device')
    if not device or not Path(device).is_char_device():
        return 'RTC 장치 미확인'
    try:
        subprocess.run(['/sbin/hwclock', '--hctosys', '--utc', '--rtc', device], check=True, capture_output=True, timeout=5)
        return ''
    except (OSError, subprocess.SubprocessError) as exc:
        return 'RTC 복원 실패: ' + str(exc)


def live(config, headless=False):
    if os.geteuid() != 0 or not Path('/etc/mebs/appliance').is_file():
        raise BackupError('Live mode requires the dedicated MEBS image')
    from .hardware_profile import validate_runtime
    validate_runtime(config)
    if type(config.get('ui_fps', 30)) is not int or not 1 <= config.get('ui_fps', 30) <= 60:
        raise ValueError('ui_fps must be 1..60')
    stop = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    Path('/run/mebs').mkdir(exist_ok=True, mode=0o700)
    with open('/run/mebs/appliance.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Never silently persist to a USB disk or read-only rootfs.
        data = Path('/var/lib/mebs')
        if not os.path.ismount(data):
            raise BackupError('OS-owned settings partition is not mounted')
        c = Controls(SettingsStore(data / 'settings.json'), guard=BatteryGuard(**config.get('battery_thresholds', {})))
        c.notice = restore_rtc(config) or c.notice
        mounts = ObservedMounts(c)
        worker = Thread(target=Worker(c, stop, mounts).run, name='mebs-backup')
        sensors = Sensors(config, c)
        sensor_thread = Thread(target=sensors.run, args=(stop,), name='mebs-sensors')
        worker.start()
        sensor_thread.start()
        screen = touch = None
        last_connect, last_frame, last_status = -10., -10., None
        splash_frames = None
        try:
            while not stop.is_set():
                now = time.monotonic()
                c.tick()
                if c.shutdown_ready():
                    def flush():
                        if mounts.mounted:
                            raise BackupError('미완료 마운트가 있어 종료를 막았습니다.')
                        sync_filesystem(data)
                        os.sync()
                    def poweroff():
                        subprocess.run(['/sbin/poweroff'], check=True, timeout=10)
                        stop.set()
                    c.perform_shutdown(flush, lambda s: append_log(data/'events.jsonl', s), poweroff)
                if not headless and now-last_connect >= 2:
                    last_connect = now
                    if screen is None:
                        try:
                            from .outputs import open_output
                            screen = open_output(config)
                            from .boot_animation import checks, frames, logo_asset
                            asset = logo_asset()
                            if asset.source == 'text-fallback':
                                c.notice = '임시 텍스트 로고 · 원본 로고 파일 확인 필요'
                            splash_frames = iter(frames(checks(True), steps=3))
                        except (OSError, ValueError):
                            pass  # backup is never gated by a display probe
                    if touch is None and config.get('touch', {}).get('device'):
                        try:
                            from .touch import Touch
                            touch = Touch(config['touch']['device'], c.gesture, config['touch'].get('rotation', 0))
                        except (OSError, ValueError) as exc:
                            c.notice = '터치 연결 실패: ' + str(exc)
                if touch:
                    try:
                        touch.poll()
                    except OSError as exc:
                        touch.close()
                        touch = None
                        c.notice = str(exc)
                if screen and now-last_frame >= 1 / config.get('ui_fps', 30):
                    from .ui800 import render
                    try:
                        if splash_frames is not None:
                            from .boot_animation import render as boot_render
                            from PIL import Image
                            try:
                                pct, opacity, phase, caption = next(splash_frames)
                                try:
                                    boot = boot_render(pct, opacity=opacity, state=phase, caption=caption)
                                except (ValueError, OSError) as exc:
                                    c.notice = '원본 로고 데이터 오류: ' + str(exc)
                                    splash_frames = None
                                    boot = render(c).resize((1280, 720))
                                frame = Image.new('RGB', (800, 480), '#050b14')
                                frame.paste(boot.resize((800, 450), Image.Resampling.LANCZOS), (0, 15))
                            except StopIteration:
                                splash_frames = None
                                frame = render(c)
                        else:
                            frame = render(c)
                        screen.show(frame)
                        from .outputs import apply_backlight
                        apply_backlight(config.get('backlight'), 0 if c.screen_off else c.effective_brightness)
                    except (OSError, ValueError) as exc:
                        screen.close()
                        screen = None
                        c.notice = '화면 연결 실패: ' + str(exc)
                    last_frame = now
                with c.lock:
                    status = dict(c.state, battery_guard=c.guard.status(c.reading.voltage), shutdown_pending=c.shutdown_pending)
                encoded = json.dumps(status, ensure_ascii=True)
                if encoded != last_status:
                    Path('/run/mebs/status.json').write_text(encoded+'\n')
                    print(encoded, flush=True)
                    last_status = encoded
                    if status['state'] in ('ERROR', 'CANCELLED', 'SAFE_TO_REMOVE'):
                        append_log(data/'events.jsonl', status)
                stop.wait(.01)
        finally:
            stop.set()
            worker.join()  # no kill while a filesystem write is outstanding
            sensor_thread.join()
            if screen:
                screen.close()
            if touch:
                touch.close()
            sync_filesystem(data)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', default='/etc/mebs/hardware.json')
    p.add_argument('--headless', action='store_true')
    p.add_argument('--mock-preview', type=Path, help='write PNG previews without hardware access')
    args = p.parse_args()
    if args.mock_preview:
        from .ui800 import render
        import tempfile
        args.mock_preview.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            c = Controls(SettingsStore(Path(tmp)/'settings.json'))
            c.reading = Reading(cpu_c=46, voltage=7.6, current_a=.8, lux=100, percent=65)
            c.update(dict(state='COPYING', demo=True, source_connected=True, target_connected=True, total_bytes=1000000000, copied_bytes=640000000, total_files=45, verified_files=23))
            render(c).save(args.mock_preview/'main.png')
            c.panel = True
            render(c).save(args.mock_preview/'settings.png')
            c.worker_active = True
            c.request_shutdown()
            render(c).save(args.mock_preview/'shutdown.png')
        return
    live(json.loads(Path(args.config).read_text()), args.headless)


if __name__ == '__main__':
    main()
