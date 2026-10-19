"""Power-button lifecycle with real temporary-file backup and a mock display."""
from pathlib import Path
from threading import Event, Thread
import tempfile
import unittest

from mebs.backup import verify
from mebs.boot_animation import frames, render as boot_render, shutdown_frames
from mebs.controls import Controls
from mebs.runtime800 import Worker, poweroff_after_fade, show_shutdown
from mebs.settings import SettingsStore
from test_appliance import FakeMounts, disk


class Screen:
    def __init__(self):
        self.frames = []

    def show(self, frame):
        self.frames.append(frame.copy())


class PowerCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.target = self.root / 'source', self.root / 'target'
        self.source.mkdir(); self.target.mkdir()
        (self.source / 'DCIM').mkdir()
        (self.source / 'DCIM' / '사진.JPG').write_bytes(b'photo' * 400000)
        (self.source / 'DCIM' / '정보.XML').write_bytes(b'<clip>metadata</clip>')
        self.control = Controls(SettingsStore(self.root / 'settings.json'))

    def test_boot_copy_button_queue_verify_fade_poweroff_and_next_boot(self):
        boot = list(frames([True] * 5, steps=2))
        self.assertEqual(boot[0][0], 0)
        self.assertEqual((boot[-1][0], boot[-1][2]), (100, 'ready'))
        self.assertTrue(boot_render(*boot[0][:1]).getbbox())

        c = self.control
        copying = Event(); release = Event()
        original_update = c.update
        states = []
        def update(state):
            original_update(state)
            states.append(state['state'])
            if state['state'] == 'COPYING' and state.get('copied_bytes', 0) and not copying.is_set():
                copying.set()
                self.assertTrue(release.wait(5))
        c.update = update
        mounts = FakeMounts(self.source, self.target)
        mounts.mounted = []
        hdd, sd = disk('sda'), disk('sdb', 'exfat')
        connected = []
        worker = Worker(c, Event(), mounts, current=lambda: list(connected), sleeper=lambda _: None)
        worker.once()
        connected.append(hdd); worker.once()
        self.assertEqual(c.state['state'], 'WAITING_SOURCE')
        connected.append(sd)
        thread = Thread(target=worker.once)
        thread.start()
        try:
            self.assertTrue(copying.wait(5))
            self.assertEqual(c.gesture((400, 10), (400, 110)), 'open')
            self.assertEqual(c.gesture((750, 40), (750, 40)), 'power')
            self.assertTrue(c.confirm_power)
            self.assertEqual(c.gesture((580, 290), (580, 290)), 'shutdown-confirmed')
            self.assertTrue(c.shutdown_pending)
            self.assertFalse(c.shutdown_ready())
            c.last_touch -= 1_000_000
            c.tick()
            self.assertFalse(c.screen_off)
            self.assertFalse(c.perform_shutdown(lambda: None, lambda _: None,
                                                 lambda: self.fail('powered off during copy')))
        finally:
            release.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertIn('VERIFYING', states)
        self.assertLess(states.index('VERIFYING'), states.index('SAFE_TO_REMOVE'))
        self.assertEqual(c.state['state'], 'SAFE_TO_REMOVE')
        self.assertTrue(c.state['safe_to_remove'])
        self.assertIn('close', mounts.calls)
        self.assertEqual(len(verify(c.state['job'])['files']), 2)
        self.assertEqual((self.source / 'DCIM' / '정보.XML').read_bytes(), b'<clip>metadata</clip>')

        screen = Screen(); order = []
        def fade_and_poweroff():
            order.append('fade')
            show_shutdown(screen, sleeper=lambda _: None)
            order.append('poweroff')
        self.assertTrue(c.perform_shutdown(lambda: order.append('sync'),
                                           lambda _: order.append('log'), fade_and_poweroff))
        self.assertEqual(order, ['sync', 'log', 'sync', 'fade', 'poweroff'])
        self.assertEqual(len(screen.frames), 9)
        self.assertIsNone(screen.frames[-1].getbbox())
        self.assertTrue(screen.frames[0].getbbox())
        self.assertTrue(all(sum(screen.frames[i].convert('L').getdata()) >=
                            sum(screen.frames[i+1].convert('L').getdata())
                            for i in range(8)))
        # A fresh boot cannot inherit the previous shutdown request.
        next_boot = Controls(SettingsStore(self.root / 'settings.json'))
        self.assertFalse(next_boot.shutdown_pending)
        self.assertEqual(next_boot.state['state'], 'READY')

    def test_failed_copy_never_runs_queued_shutdown_or_fade(self):
        c = self.control
        c.begin_job(); c.update({'state': 'COPYING'})
        c.request_shutdown(); c.confirm_shutdown()
        c.finish_job({'state': 'ERROR', 'error': 'Verification Failed', 'safe_to_remove': False})
        screen = Screen(); power = []
        self.assertFalse(c.perform_shutdown(lambda: None, lambda _: None,
                                            lambda: power.append('poweroff')))
        self.assertFalse(c.shutdown_pending)
        self.assertFalse(screen.frames)
        self.assertFalse(power)

    def test_sync_failure_and_bad_screen_do_not_confuse_shutdown(self):
        c = self.control
        c.request_shutdown(); c.confirm_shutdown()
        power = []
        self.assertFalse(c.perform_shutdown(lambda: (_ for _ in ()).throw(OSError('syncfs failed')),
                                            lambda _: None, lambda: power.append('poweroff')))
        self.assertFalse(power)
        with self.assertRaises(ValueError):
            list(shutdown_frames(0))
        self.assertIsNone(show_shutdown(None))

    def test_failed_display_does_not_block_poweroff_and_poweroff_failure_is_visible(self):
        class BrokenScreen:
            def show(self, _):
                raise OSError('display detached')
        power, messages = [], []
        poweroff_after_fade(BrokenScreen(), lambda: power.append('poweroff'), messages.append)
        self.assertEqual(power, ['poweroff'])
        self.assertIn('display detached', messages[0])
        c = self.control
        c.request_shutdown(); c.confirm_shutdown()
        self.assertFalse(c.perform_shutdown(lambda: None, lambda _: None,
                                            lambda: (_ for _ in ()).throw(OSError('poweroff failed'))))
        self.assertFalse(c.shutting_down)
        self.assertIn('poweroff failed', c.notice)
        self.assertFalse(c.screen_off)

    def test_reconnect_after_bad_destination_clears_stale_error_message(self):
        c = self.control
        mounts = FakeMounts(self.source, self.target)
        mounts.mounted = []
        devices = []
        worker = Worker(c, Event(), mounts, current=lambda: list(devices), sleeper=lambda _: None)
        worker.once()
        invalid = disk('sda', 'ntfs')
        sd = disk('sdb', 'exfat')
        devices[:] = [invalid]; worker.once()
        devices.append(sd); worker.once()
        self.assertEqual(c.state['state'], 'ERROR')
        self.assertIn('ext4', c.notice)
        devices.clear(); worker.once()
        devices[:] = [disk('sda')]; worker.once()
        devices.append(sd); worker.once()
        self.assertEqual(c.state['state'], 'SAFE_TO_REMOVE')
        self.assertNotIn('ext4', c.notice)
        self.assertEqual(len(verify(c.state['job'])['files']), 2)

    def test_disconnect_after_queued_power_never_powers_off(self):
        c = self.control
        mounts = FakeMounts(self.source, self.target)
        mounts.mounted = []
        hdd, sd = disk('sda'), disk('sdb', 'exfat')
        devices = []
        original_update = c.update
        def emit(state):
            original_update(state)
            if state['state'] == 'COPYING' and state.get('copied_bytes', 0) and len(devices) == 2:
                c.request_shutdown(); c.confirm_shutdown()
                devices.pop()  # virtual source disappears during the copy
        c.update = emit
        worker = Worker(c, Event(), mounts, current=lambda: list(devices), sleeper=lambda _: None)
        worker.once()
        devices.append(hdd); worker.once()
        devices.append(sd); worker.once()
        self.assertEqual(c.state['state'], 'ERROR')
        self.assertFalse(c.shutdown_pending)
        self.assertFalse(c.state.get('safe_to_remove', False))
        self.assertFalse(c.perform_shutdown(lambda: None, lambda _: None,
                                            lambda: self.fail('powered off after source removal')))
        self.assertTrue((self.source / 'DCIM' / '사진.JPG').is_file())

    def test_recovery_preserves_unrelated_battery_warning(self):
        c = self.control
        c.update({'state': 'ERROR', 'error': 'invalid destination'})
        c.notice = '배터리 보호: UNKNOWN'
        c.update({'state': 'READY'})
        self.assertEqual(c.notice, '배터리 보호: UNKNOWN')


if __name__ == '__main__':
    unittest.main()
