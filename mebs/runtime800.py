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
import tempfile
from threading import Event, Thread
import time

from .appliance import BackupError, Mounts, display_paths, inventory, run_job, sync_filesystem
from .controls import Controls, append_log
from .devices import Roles
from .sensors import BatteryGuard, I2C, INA226, INA231, Reading, VirtualINARegisters, cpu_temperature, ram_usage, estimate, validate_addresses, voltage_percent
from .settings import SettingsStore


def publish_status(path, encoded):
    """Expose either the previous complete status or the next complete status."""
    path = Path(path)
    fd, pending = tempfile.mkstemp(prefix='.status-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(encoded + '\n')
        os.replace(pending, path)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)


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
            from .preflight import capacity
            values = capacity(self.source, path)
            with self.control.lock:
                self.control.state.update(values)
            # The engine checks free space after exact-duplicate reuse. A full
            # destination can still safely reuse an already verified job.
        return path


class Worker:
    def __init__(self, control, stop, mounts, current=inventory, job=run_job,
                 sleeper=time.sleep, inspect_pending=None):
        self.c, self.stop, self.mounts = control, stop, mounts
        self.current, self.job, self.sleep = current, job, sleeper
        self.roles, self.latched = Roles(), False
        self.inspect_pending = inspect_pending or getattr(mounts, 'inspect_pending', lambda _: [])
        self.inspected_target = None
        self.pending_count = 0

    def once(self):
        try:
            disks = self.current()
            ids = [d['token'] for d in disks]
            if not ids and not self.mounts.mounted:
                self.latched = False
                self.inspected_target = None
                self.pending_count = 0
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
                                      self.c.update, lambda: self.stop.is_set() or self.c.battery_stop_required(),
                                      self.mounts, current=self.current)
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
                if (assigned['state'] == 'WAITING_FOR_SOURCE' and
                        assigned['target'] != self.inspected_target):
                    target = next(d for d in disks if d['token'] == assigned['target'])
                    self.pending_count = len(self.inspect_pending(target))
                    self.inspected_target = assigned['target']
                with self.c.lock:
                    if not self.c.shutdown_pending and not self.c.shutting_down:
                        phase = ('RECOVERY_REQUIRED' if assigned['state'] == 'WAITING_FOR_SOURCE'
                                 and self.pending_count else
                                 {'WAITING_FOR_TARGET': 'READY', 'WAITING_FOR_SOURCE': 'WAITING_SOURCE'}.get(assigned['state'], assigned['state']))
                        self.c.update(dict(state=phase,
                                           target_connected=assigned['target'] is not None,
                                           source_connected=assigned['source'] is not None,
                                           incomplete_jobs=self.pending_count,
                                           error='이전 백업이 중단되었습니다. 원본 SD를 다시 연결하면 새 백업으로 재시도합니다.' if phase == 'RECOVERY_REQUIRED' else ''))
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
    def __init__(self, config, control, bus_factory=None):
        validate_addresses(config)
        self.config, self.c = config, control
        self.handles = []
        self.ina = None
        self.display_ina = None
        self.init_errors = []
        mode = config.get('sensor_mode', 'REAL')
        if mode == 'SIMULATION' and config.get('simulation_explicit') is not True:
            raise ValueError('Simulation requires explicit test configuration')
        for name, address, factory in [('ina226', 0x40, INA226), ('ina231', 0x40, INA231)]:
            item = config.get(name, {})
            if not item.get('enabled'):
                continue
            try:
                if mode == 'SIMULATION':
                    if bus_factory is None:
                        raise ValueError('Simulation requires injected virtual I2C bus')
                    bus = bus_factory(name, item.get('address', address))
                    if not getattr(bus, 'simulation', False):
                        raise ValueError('Simulation bus must be explicitly virtual')
                else:
                    bus = I2C(config.get('i2c_bus', '/dev/i2c-1'), item.get('address', address))
                    self.handles.append(bus)
                self.ina = factory(bus, item.get('shunt_ohms'), item.get('discharge_polarity', 1),
                                   model_confirmed=item.get('model_confirmed', False),
                                   max_current_a=item.get('max_current_a'),
                                   program_calibration=item.get('program_calibration', False))
            except (OSError, ValueError) as exc:
                self.init_errors.append(name + ': ' + str(exc))
        preview = config.get('battery_display_simulation', {})
        if preview.get('enabled') is True:
            # A separate register bus supplies UI-only values. Never assign it
            # to self.ina or c.reading, which the battery guard consumes.
            self.display_ina = INA226(VirtualINARegisters('INA226', .01), .01)

    def read(self):
        r = Reading()
        errors = list(self.init_errors)
        for name, operation in [('CPU', lambda: setattr(r, 'cpu_c', cpu_temperature())),
                                ('RAM', lambda: setattr(r, 'ram_percent', ram_usage())),
                                ('INA', lambda: self._battery(r))]:
            try:
                operation()
            except (OSError, ValueError) as exc:
                errors.append(name + ': ' + str(exc))
        r.error = '; '.join(errors) or ('배터리 센서 미설정' if not self.ina else '')
        demo = None
        if r.sensor_source == 'N/A' and self.display_ina:
            preview = self.config['battery_display_simulation']
            self.display_ina.bus.inject(preview['voltage_v'], preview['current_a'])
            m = self.display_ina.sample()
            design = self.config.get('battery_design', {})
            demo = Reading(voltage=m.voltage, current_a=m.current_a, power_w=m.power_w,
                           sensor_source='SIMULATION', sensor_model='VIRTUAL INA226',
                           sampled_utc=m.timestamp_utc, sampled_monotonic=m.sampled_monotonic,
                           percent=voltage_percent(m.voltage, design.get('empty_v',6.3), design.get('full_v',8.4)),
                           percent_kind='VOLTAGE_ESTIMATE')
        with self.c.lock:
            self.c.reading = r
            self.c.display_battery = demo

    def _battery(self, r):
        if self.ina:
            measurement = self.ina.sample()
            if measurement.source != self.config.get('sensor_mode', 'REAL'):
                raise ValueError('sensor mode/source mismatch')
            r.voltage, r.current_a, r.power_w = measurement.voltage, measurement.current_a, measurement.power_w
            r.sensor_source, r.sensor_model = measurement.source, measurement.model
            r.sampled_utc, r.sampled_monotonic = measurement.timestamp_utc, measurement.sampled_monotonic
            design = self.config.get('battery_design', {})
            r.percent = voltage_percent(r.voltage, design.get('empty_v',6.3), design.get('full_v',8.4))
            r.percent_kind = 'VOLTAGE_ESTIMATE'

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


def show_shutdown(screen, *, fps=15, sleeper=time.sleep):
    """Display-only fade; callers must finish backup/unmount/sync first."""
    if screen is None:
        return
    if not 1 <= fps <= 60:
        raise ValueError('shutdown fps must be 1..60')
    from PIL import Image
    from .boot_animation import render as boot_render, shutdown_frames
    full = boot_render(0, state='shutdown').resize((800, 450), Image.Resampling.LANCZOS)
    full_frame = Image.new('RGB', (800, 480), 'black')
    full_frame.paste(full, (0, 15))
    black = Image.new('RGB', (800, 480), 'black')
    for opacity in shutdown_frames():
        screen.show(Image.blend(black, full_frame, opacity))
        if opacity:
            sleeper(1 / fps)


def poweroff_after_fade(screen, poweroff, report=print):
    """A missing/broken screen cannot block a completed safe shutdown."""
    try:
        show_shutdown(screen)
    except Exception as exc:
        report('Shutdown display unavailable: ' + str(exc))
    poweroff()


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
        backup_worker = Worker(c, stop, mounts)
        worker = Thread(target=backup_worker.run, name='mebs-backup')
        sensors = Sensors(config, c)
        sensor_thread = Thread(target=sensors.run, args=(stop,), name='mebs-sensors')
        worker.start()
        sensor_thread.start()
        screen = touch = explorer_ui = None
        from .explorer_v3 import ApplianceSession, ExplorerError
        explorer_session = ApplianceSession(c, backup_worker)
        def on_touch(start, end, duration):
            nonlocal explorer_ui
            if explorer_ui is not None:
                result = explorer_ui.gesture(start, end, duration)
                if result in ('closed', 'safe-eject'):
                    explorer_ui = None
                    c.notice = '안전 분리 완료' if result == 'safe-eject' else ''
                return result
            action = c.gesture(start, end, duration)
            if action == 'explorer-open':
                try:
                    from .ui_explorer_v3 import ExplorerUI
                    explorer_session.open()
                    explorer_ui = ExplorerUI(explorer_session)
                except (ExplorerError, BackupError, OSError, ValueError) as exc:
                    c.notice = '탐색기: ' + str(exc)
            return action
        last_connect, last_frame, last_status, last_explorer_check = -10., -10., None, -10.
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
                        # Only reached after the job has completed, all mounts
                        # are closed and both metadata flushes have succeeded.
                        poweroff_after_fade(screen,
                                            lambda: subprocess.run(['/sbin/poweroff'], check=True, timeout=10),
                                            lambda message: print(message, flush=True))
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
                            touch = Touch(config['touch']['device'], on_touch, config['touch'].get('rotation', 0))
                        except (OSError, ValueError) as exc:
                            c.notice = '터치 연결 실패: ' + str(exc)
                if touch:
                    try:
                        touch.poll()
                    except OSError as exc:
                        touch.close()
                        touch = None
                        c.notice = str(exc)
                if explorer_ui is not None and now-last_explorer_check >= .5:
                    last_explorer_check = now
                    try:
                        explorer_session.refresh()
                    except (ExplorerError, BackupError, OSError) as exc:
                        explorer_ui = None
                        c.notice = '탐색기: ' + str(exc)
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
                        elif explorer_ui is not None:
                            from .ui_explorer_v3_layout import render as render_explorer
                            frame = render_explorer(explorer_ui)
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
                    status = dict(c.state, battery_guard=c.battery_status(),
                                  battery_voltage=c.reading.voltage, battery_current_a=c.reading.current_a,
                                  battery_power_w=c.reading.power_w, sensor_source=c.reading.sensor_source,
                                  sensor_model=c.reading.sensor_model, sensor_timestamp=c.reading.sampled_utc,
                                  display_battery_source=c.display_battery.sensor_source if c.display_battery else 'N/A',
                                  display_battery_voltage=c.display_battery.voltage if c.display_battery else None,
                                  shutdown_pending=c.shutdown_pending)
                encoded = json.dumps(status, ensure_ascii=True)
                if encoded != last_status:
                    publish_status('/run/mebs/status.json', encoded)
                    print(encoded, flush=True)
                    last_status = encoded
                    if status['state'] in ('ERROR', 'CANCELLED', 'SAFE_TO_REMOVE'):
                        append_log(data/'events.jsonl', status)
                stop.wait(.01)
        finally:
            stop.set()
            if explorer_ui is not None:
                try:
                    explorer_session.close()
                except (BackupError, OSError) as exc:
                    print('Explorer unmount failed: ' + str(exc), flush=True)
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
            Sensors({'sensor_mode':'REAL','battery_display_simulation':{'enabled':True,
                     'voltage_v':7.4,'current_a':.5}},c).read()
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
