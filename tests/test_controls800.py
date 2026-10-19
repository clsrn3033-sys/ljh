"""Mock controls and real temporary-directory engine; no physical disks/poweroff."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Event, Thread
import tempfile
import time
import unittest
from unittest import mock

from mebs.controls import Controls, FuturePowerLatch
from mebs.settings import Settings, SettingsStore
from mebs.sensors import BatteryGuard, INA226, Reading, estimate, validate_addresses
from mebs.rtc import DS3231
from mebs.runtime800 import Worker, Sensors, live
from mebs.ui800 import render
from mebs.preflight import capacity, require_space
from mebs.backup import BackupError, backup, verify
from test_appliance import FakeMounts, disk


class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 0.
        self.c = Controls(SettingsStore(self.root/'settings.json'), clock=lambda: self.now)

    def tap(self, x, y):
        return self.c.gesture((x, y), (x, y), .1)

    def test_800x480_main_settings_confirmation_render_with_mock_readings(self):
        self.c.reading = Reading(cpu_c=45, voltage=7.8, current_a=.5, percent=70)
        main = render(self.c)
        self.assertEqual(main.size, (800, 480))
        self.c.gesture((400, 2), (400, 120))
        settings = render(self.c)
        self.assertNotEqual(main.tobytes(), settings.tobytes())
        self.tap(750, 40)
        self.assertTrue(self.c.confirm_power)
        self.assertNotEqual(settings.tobytes(), render(self.c).tobytes())

    def test_swipe_open_close_and_button_cancel(self):
        self.assertEqual(self.c.gesture((400, 10), (400, 100)), 'open')
        self.assertEqual(self.c.gesture((400, 350), (400, 200)), 'close')
        self.assertFalse(self.c.panel)
        self.c.panel = True
        self.tap(750, 40)
        self.tap(120, 290)
        self.assertFalse(self.c.confirm_power)
        self.assertFalse(self.c.shutdown_pending)

    def test_brightness_and_persistent_switches(self):
        self.c.panel = True
        self.tap(400, 135)
        self.assertEqual(self.c.settings.brightness, 50)
        self.tap(100, 205)
        self.tap(650, 280)
        loaded = SettingsStore(self.root/'settings.json').load()
        self.assertEqual(loaded, self.c.settings)
        self.assertTrue(loaded.night_mode)
        self.c.tick()
        self.assertLessEqual(self.c.effective_brightness, 30)

    def test_corrupt_settings_fall_back_and_report_error(self):
        p = self.root/'settings.json'
        p.write_text('{broken')
        store = SettingsStore(p)
        self.assertEqual(store.load(), Settings())
        self.assertIn('설정 읽기 실패', store.error)

    def test_v1_settings_migrate_without_ambient_sensor(self):
        p = self.root/'settings.json'
        p.write_text(json.dumps({'version':1,'brightness':42,'auto_brightness':True,
                                 'night_mode':True,'screen_timeout':60}))
        store = SettingsStore(p)
        self.assertEqual(store.load(), Settings(brightness=42,night_mode=True,screen_timeout=60))
        store.save(store.load())
        saved = json.loads(p.read_text())
        self.assertEqual(saved['version'],2)
        self.assertNotIn('auto_brightness',saved)

    def test_failed_save_keeps_previous_settings(self):
        before = self.c.settings
        with mock.patch.object(self.c.store, 'save', side_effect=OSError('read only')):
            self.assertFalse(self.c.configure(brightness=20))
        self.assertEqual(self.c.settings, before)
        self.assertIn('저장 실패', self.c.notice)

    def test_idle_off_wake_consumes_tap_backup_state_kept(self):
        self.c.begin_job()
        self.c.update(dict(state='COPYING', copied_bytes=123))
        self.now = 121
        self.c.tick()
        self.assertTrue(self.c.screen_off)
        self.assertEqual(render(self.c).getbbox(), None)
        self.assertEqual(self.tap(750, 40), 'wake')
        self.assertFalse(self.c.panel)
        self.assertTrue(self.c.worker_active)
        self.assertEqual(self.c.state['copied_bytes'], 123)

    def test_touch_lock_requires_long_hold_power_still_accessible(self):
        self.c.panel = True
        self.tap(350, 205)
        self.assertTrue(self.c.locked)
        self.tap(100, 205)
        self.assertFalse(self.c.settings.night_mode)
        self.tap(750, 40)
        self.assertTrue(self.c.confirm_power)
        self.tap(100, 290)
        self.c.gesture((50, 30), (50, 30), 1.9)
        self.assertTrue(self.c.locked)
        self.c.gesture((50, 30), (50, 30), 2.1)
        self.assertFalse(self.c.locked)

    def test_shutdown_queue_waits_for_verified_unmounted_completion(self):
        calls = []
        self.c.begin_job()
        self.c.update(dict(state='COPYING'))
        self.c.request_shutdown()
        self.c.confirm_shutdown()
        self.assertFalse(self.c.perform_shutdown(lambda: calls.append('sync'), lambda s: calls.append('log'), lambda: calls.append('power')))
        self.c.update(dict(state='SAFE_TO_REMOVE', safe_to_remove=True))
        self.assertFalse(self.c.shutdown_ready())  # worker still owns final boundary
        self.c.finish_job(dict(state='SAFE_TO_REMOVE', safe_to_remove=True))
        self.assertTrue(self.c.perform_shutdown(lambda: calls.append('sync'), lambda s: calls.append('log'), lambda: calls.append('power')))
        self.assertEqual(calls, ['sync', 'log', 'sync', 'power'])
        self.assertFalse(self.c.begin_job())

    def test_failure_cancels_queued_shutdown_but_manual_retry_available(self):
        self.c.begin_job()
        self.c.request_shutdown()
        self.c.confirm_shutdown()
        self.c.finish_job(dict(state='ERROR', error='hash mismatch'))
        self.assertFalse(self.c.shutdown_pending)
        self.c.request_shutdown()
        self.c.confirm_shutdown()
        self.assertTrue(self.c.shutdown_ready())

    def test_sync_failure_prevents_poweroff(self):
        self.c.request_shutdown()
        self.c.confirm_shutdown()
        power = mock.Mock()
        self.assertFalse(self.c.perform_shutdown(mock.Mock(side_effect=OSError('unflushed')), mock.Mock(), power))
        power.assert_not_called()
        self.assertIn('종료 실패', self.c.notice)

    def test_critical_error_wakes_and_never_times_out(self):
        self.c.screen_off = True
        self.c.update(dict(state='ERROR', error='device removed'))
        self.now = 1000
        self.c.tick()
        self.assertFalse(self.c.screen_off)

    def test_low_voltage_missing_measurement_blocks_only_when_configured(self):
        self.c.guard = BatteryGuard(warn=7.1, block=6.8)  # test values, NOT hardware recommendations
        self.assertFalse(self.c.begin_job())
        self.c.reading.voltage = 6.7
        self.assertFalse(self.c.begin_job())
        self.c.reading.voltage = 7.5
        self.c.reading.sampled_monotonic = self.now
        self.assertTrue(self.c.begin_job())
        self.c.reading.voltage = 6.7
        self.c.tick()
        self.assertTrue(self.c.worker_active)  # worker cancellation is cooperative
        self.assertTrue(self.c.battery_stop_required())

    def test_no_gpio_cutoff(self):
        with self.assertRaises(NotImplementedError):
            FuturePowerLatch().cut_power()

    def test_live_rejected_without_dedicated_marker(self):
        with mock.patch('mebs.runtime800.os.geteuid', return_value=1000):
            with self.assertRaises(BackupError):
                live({})


class SensorTests(unittest.TestCase):
    def test_ina_signed_shunt_and_unknown_shunt(self):
        bus = mock.Mock()
        registers = {0xfe: b'TI', 0xff: b'\x22\x60', 2: (6000).to_bytes(2, 'big'), 1: (-400).to_bytes(2, 'big', signed=True)}
        bus.register.side_effect = lambda r: registers[r]
        self.assertEqual(INA226(bus).read(), (7.5, None))
        self.assertEqual(INA226(bus, .01).read(), (7.5, -.1))
        bus.write.assert_not_called()

    def test_address_collision(self):
        with self.assertRaisesRegex(ValueError, 'collision'):
            validate_addresses({'ina226': {'enabled': True, 'address': 0x68}, 'ds3231': {'enabled': True}})
        validate_addresses({'ina226': {'enabled': False, 'address': 0x68}, 'ds3231': {'enabled': True}})

    def test_missing_sensor_nonfatal_unknown_values(self):
        c = mock.Mock()
        from threading import RLock
        c.lock = RLock()
        with mock.patch('mebs.runtime800.I2C', side_effect=OSError('missing sensor')), mock.patch('mebs.runtime800.cpu_temperature', side_effect=OSError('missing thermal')):
            s = Sensors({'ina226': {'enabled': True}}, c)
            s.read()
        self.assertIsNone(c.reading.voltage)
        self.assertIsNone(c.reading.cpu_c)
        self.assertIn('missing sensor', c.reading.error)

    def test_no_guessed_soc_or_runtime(self):
        self.assertEqual(estimate(7.5, .5, None, None), (None, None))
        self.assertEqual(estimate(7.5, 1, [(7, 0), (8, 100)], 2), (50, 1))
        self.assertEqual(BatteryGuard().status(6), 'UNCONFIGURED')

    def test_rtc_restore_injected_clock_and_oscillator_stop(self):
        bus = mock.Mock()
        bus.register.side_effect = lambda r, count: b'\x00' if r == 15 else bytes([0x30, 0x45, 0x12, 0x07, 0x18, 0x10, 0x26])
        clock = mock.Mock()
        dt = DS3231(bus).restore(clock)
        self.assertEqual(dt, datetime(2026, 10, 18, 12, 45, 30, tzinfo=timezone.utc))
        clock.assert_called_once_with(int(dt.timestamp()))
        bus.register.side_effect = lambda *_: b'\x80'
        with self.assertRaisesRegex(ValueError, 'oscillator'):
            DS3231(bus).restore(clock)
        self.assertEqual(clock.call_count, 1)

    def test_rtc_explicit_first_set_utc(self):
        bus = mock.Mock()
        bus.register.return_value = b'\x80'
        DS3231(bus).set(datetime(2026, 10, 18, 12, 30, 5, tzinfo=timezone.utc))
        self.assertEqual(bus.write.call_args_list[0].args[0], bytes([0, 5, 0x30, 0x12, 7, 0x18, 0x10, 0x26]))
        self.assertEqual(bus.write.call_args_list[1].args[0], b'\x0f\x00')


class WorkerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src, self.dst = self.root/'src', self.root/'dst'
        self.src.mkdir(); self.dst.mkdir()
        (self.src/'camera.xml').write_bytes(b'<metadata>preserve</metadata>')
        (self.src/'clip.mov').write_bytes(b'x' * 3 * 1024 * 1024)
        self.c = Controls(SettingsStore(self.root/'settings.json'))
        self.hdd, self.sd = disk('sda'), disk('sdb', 'exfat')
        self.connected = []
        self.mounts = FakeMounts(self.src, self.dst)
        self.mounts.mounted = []
        self.worker = Worker(self.c, Event(), self.mounts, current=lambda: list(self.connected), sleeper=lambda _: None)

    def arm(self):
        self.worker.once()
        self.connected = [self.hdd]
        self.worker.once()
        self.connected.append(self.sd)

    def test_interrupted_job_is_reported_before_source_reconnect(self):
        pending = self.dst/'.mebs-pending-interrupted'
        pending.mkdir()
        self.worker.inspect_pending = lambda _: [pending.name]
        self.worker.once()
        self.connected = [self.hdd]
        self.worker.once()
        self.assertEqual(self.c.state['state'], 'RECOVERY_REQUIRED')
        self.assertEqual(self.c.state['incomplete_jobs'], 1)
        self.connected.append(self.sd)
        self.worker.once()
        self.assertEqual(self.c.state['state'], 'SAFE_TO_REMOVE')
        self.assertTrue(pending.is_dir())
        verify(self.c.state['job'])

    def test_ram_reading_uses_memavailable_not_demo_values(self):
        from mebs.sensors import ram_usage
        sample = self.root/'meminfo'
        sample.write_text('MemTotal: 1000 kB\nMemFree: 300 kB\nMemAvailable: 250 kB\n')
        self.assertEqual(ram_usage(sample), 75)
        sample.write_text('MemTotal: 0 kB\nMemAvailable: 0 kB\n')
        with self.assertRaises(ValueError):
            ram_usage(sample)

    def test_headless_real_copy_while_quick_settings_and_power_queue(self):
        copied = Event(); release = Event()
        original = self.c.update
        def update(s):
            original(s)
            if s['state'] == 'COPYING' and s.get('copied_bytes', 0) and not copied.is_set():
                copied.set()
                self.assertTrue(release.wait(3))
        self.c.update = update
        self.arm()
        thread = Thread(target=self.worker.once)
        thread.start()
        try:
            self.assertTrue(copied.wait(3))
            self.c.gesture((200, 2), (200, 130))
            self.c.gesture((400, 130), (400, 130))
            self.c.request_shutdown()
            self.c.confirm_shutdown()
            self.assertTrue(self.c.panel)
            self.assertTrue(self.c.shutdown_pending)
            self.assertFalse(self.c.shutdown_ready())
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.c.state['state'], 'SAFE_TO_REMOVE')
        self.assertTrue(self.c.shutdown_ready())
        verify(self.c.state['job'])
        self.assertEqual((self.src/'camera.xml').read_bytes(), b'<metadata>preserve</metadata>')

    def test_device_removal_mid_copy_for_each_role_no_queued_power(self):
        from mebs.appliance import run_job
        for removed in ('source', 'target'):
            with self.subTest(removed=removed):
                # Each fault must copy new data; an earlier verified commit can
                # now be safely reused without entering the COPYING phase.
                (self.src/'clip.mov').write_bytes((b'x' if removed == 'source' else b'y') * 3 * 1024 * 1024)
                self.connected = [self.hdd, self.sd]
                def emit(s):
                    if s['state'] == 'COPYING':
                        self.connected = [self.hdd] if removed == 'source' else [self.sd]
                result = run_job(self.sd, self.hdd, emit, lambda: False, self.mounts, current=lambda: self.connected, sync=lambda _: None)
                self.assertEqual(result['state'], 'ERROR')
                self.assertFalse(result['safe_to_remove'])
                self.assertTrue((self.src/'clip.mov').is_file())

    def test_low_voltage_mid_copy_cancels_and_preserves_source(self):
        self.c.guard = BatteryGuard(block=6.4)
        self.c.reading = Reading(voltage=7.4, sampled_monotonic=time.monotonic())
        original = self.c.update
        def update(state):
            original(state)
            if state['state'] == 'COPYING' and state.get('copied_bytes', 0):
                self.c.reading = Reading(voltage=6.4, sampled_monotonic=time.monotonic())
        self.c.update = update
        self.arm()
        self.worker.once()
        self.assertEqual(self.c.state['state'], 'CANCELLED')
        self.assertFalse(self.c.state['safe_to_remove'])
        self.assertEqual((self.src/'camera.xml').read_bytes(), b'<metadata>preserve</metadata>')
        self.assertTrue((self.src/'clip.mov').is_file())

    def test_capacity_reports_real_bytes_and_no_format_when_short(self):
        values = capacity(self.src, self.dst)
        self.assertEqual(values['total_bytes'], 3*1024*1024+len(b'<metadata>preserve</metadata>'))
        self.assertGreater(values['needed_bytes'], values['total_bytes'])
        values['free_bytes'] = 1
        with self.assertRaisesRegex(BackupError, '필요.*잔여.*포맷'):
            require_space(values)
        self.assertEqual(list(self.dst.iterdir()), [])

    def test_prior_failed_pending_job_retained_and_independent_retry(self):
        def crash(e):
            if e['state'] == 'COPYING':
                raise OSError('simulated interrupted power')
        with self.assertRaises(OSError):
            backup(self.src, self.dst, crash)
        pending = list(self.dst.glob('.mebs-pending-*'))
        self.assertEqual(len(pending), 1)
        with self.assertRaises(BackupError):
            verify(pending[0])
        completed = backup(self.src, self.dst)
        verify(completed)
        self.assertTrue(pending[0].is_dir())


class TouchBoundaryTests(unittest.TestCase):
    def touch(self):
        from mebs.touch import Touch
        touch = Touch.__new__(Touch)
        touch.callback = mock.Mock()
        touch.ranges = {53: (0, 4095), 54: (0, 4095)}
        touch.axes = (53, 54)
        touch.rotation = 0
        touch.slot = 0
        touch.x = touch.y = touch.start = None
        touch.down = touch.dropped = False
        return touch

    def press(self, t):
        t.event(3, 57, 101)
        t.event(3, 53, 4095)
        t.event(3, 54, 4095)
        t.event(0, 0, 0)

    def release(self, t):
        t.event(3, 57, -1)
        t.event(0, 0, 0)

    def test_evdev_scaling_and_release_gesture(self):
        t = self.touch()
        self.press(t)
        self.release(t)
        self.assertEqual(t.callback.call_args.args[:2], ((799, 479), (799, 479)))

    def test_dropped_and_multiple_contacts_never_activate_button(self):
        for mode in ('drop', 'multitouch'):
            t = self.touch()
            self.press(t)
            if mode == 'drop':
                t.event(0, 3, 0)
            else:
                t.event(3, 47, 1)
                t.event(3, 57, 202)
                t.event(3, 47, 0)
            self.release(t)
            t.callback.assert_not_called()

    def test_queued_shutdown_requires_verified_safe_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = Controls(SettingsStore(Path(tmp)/'settings.json'))
            c.begin_job()
            c.request_shutdown()
            c.confirm_shutdown()
            c.finish_job({'state': 'COMPLETE', 'safe_to_remove': False})
            self.assertFalse(c.shutdown_ready())
            c.update({'state': 'SAFE_TO_REMOVE', 'safe_to_remove': False})
            self.assertFalse(c.shutdown_ready())
            c.update({'state': 'SAFE_TO_REMOVE', 'safe_to_remove': True})
            self.assertTrue(c.shutdown_ready())
