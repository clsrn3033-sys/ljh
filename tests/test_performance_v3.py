import json
from pathlib import Path
import struct
import tempfile
import unittest

from mebs.performance import (BASE_KHZ, EXPLORER_KHZ, VIDEO_KHZ,
                              ClockPolicy, firmware_throttled, validated_limits)
from mebs.performance_validate import validate


class PerformanceV3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cpufreq = self.root/'cpufreq'
        self.cpufreq.mkdir()
        self.policy = self.cpufreq/'policy0'
        self.policy.mkdir()
        for name, value in [('scaling_min_freq', 600000), ('scaling_max_freq', 2000000),
                            ('cpuinfo_max_freq', 2000000), ('scaling_cur_freq', 2000000)]:
            (self.policy/name).write_text(str(value))
        self.record = self.root/'validated.json'
        self.record.write_text(json.dumps({'result':'PASS','hardware_tested':True,
            'full_system_verified':True,
            'board_serial':'12345678abcdef01','validated_khz':[EXPLORER_KHZ,VIDEO_KHZ],
            'duration_seconds':1800,'maximum_temperature_c':70,
            'throttled_or_undervoltage_mask':0}))
        self.time = 0
        self.temp_c = 50
        self.mask = 0

    def manager(self, **overrides):
        params = dict(root=self.cpufreq, validation=self.record,
                      temperature=lambda:self.temp_c, throttled=lambda:self.mask,
                      serial=lambda:'12345678abcdef01', clock=lambda:self.time)
        params.update(overrides)
        return ClockPolicy(**params)

    def cap(self):
        return int((self.policy/'scaling_max_freq').read_text())

    def test_mode_transitions_and_backup_priority(self):
        manager = self.manager()
        self.assertEqual(manager.tick(explorer=True)['mode'],'BASE')
        self.assertEqual(self.cap(),BASE_KHZ)
        self.time = 31
        self.assertEqual(manager.tick(explorer=True)['mode'],'EXPLORER')
        self.assertEqual(self.cap(),EXPLORER_KHZ)
        self.assertEqual(manager.tick(explorer=True,video=True)['mode'],'VIDEO')
        self.assertEqual(self.cap(),VIDEO_KHZ)
        self.assertEqual(manager.tick(explorer=True,video=True,backup=True)['mode'],'BASE')
        self.assertEqual(self.cap(),BASE_KHZ)
        manager.tick()
        self.assertEqual(self.cap(),BASE_KHZ)

    def test_75_and_80_degree_limits_with_cooldown(self):
        manager = self.manager(); manager.tick(); self.time = 31
        self.assertEqual(manager.tick(video=True)['mode'],'VIDEO')
        self.temp_c = 75
        state = manager.tick(video=True)
        self.assertEqual((state['mode'],self.cap()),('BASE',BASE_KHZ))
        self.assertIn('75C',state['reason'])
        self.temp_c = 80
        self.assertIn('80C',manager.tick(video=True)['reason'])
        self.temp_c = 69
        self.assertEqual(manager.tick(video=True)['mode'],'BASE')
        self.time += 31
        self.assertEqual(manager.tick(video=True)['mode'],'VIDEO')

    def test_voltage_and_throttle_fault_latch(self):
        for failure in (0x1,0x4,0x10000,0x40000):
            with self.subTest(mask=failure):
                self.time = 0; self.mask = 0
                (self.policy/'scaling_max_freq').write_text('2000000')
                manager = self.manager(); manager.tick(); self.time = 31
                self.assertEqual(manager.tick(video=True)['mode'],'VIDEO')
                self.mask = failure
                self.assertEqual(manager.tick(video=True)['mode'],'BASE')
                self.assertEqual(self.cap(),BASE_KHZ)
                self.mask = 0; self.time += 100
                self.assertEqual(manager.tick(video=True)['mode'],'BASE')

    def test_unavailable_sensors_or_validation_never_boost(self):
        self.record.unlink()
        manager = self.manager(); manager.tick(); self.time = 31
        self.assertEqual(manager.tick(video=True)['mode'],'BASE')
        self.assertEqual(self.cap(),BASE_KHZ)
        self.record.write_text('{}')
        self.assertEqual(validated_limits(self.record,'12345678abcdef01'),set())
        (self.policy/'scaling_max_freq').write_text('2000000')
        manager = self.manager(throttled=lambda: (_ for _ in ()).throw(OSError('missing vcio')))
        self.assertEqual(manager.tick(video=True)['mode'],'BASE')
        self.assertIn('unavailable',manager.state['reason'])

    def test_no_cpufreq_or_boot_support(self):
        manager = self.manager(root=self.root/'missing')
        self.assertEqual(manager.tick()['mode'],'UNAVAILABLE')
        (self.policy/'cpuinfo_max_freq').write_text('1800000')
        (self.policy/'scaling_max_freq').write_text('1800000')
        manager = self.manager(); manager.tick(); self.time = 31
        self.assertEqual(manager.tick(video=True)['mode'],'BASE')
        self.assertEqual(self.cap(),BASE_KHZ)

    def test_external_tighter_cap_is_not_raised(self):
        manager = self.manager(); manager.tick(); self.time = 31
        manager.tick(video=True)
        (self.policy/'scaling_max_freq').write_text('1200000')
        self.assertEqual(manager.tick(video=True)['mode'],'BASE')
        self.assertEqual(self.cap(),1200000)
        manager.tick(video=True)
        self.assertEqual(self.cap(),1200000)

    def test_mailbox_message_parsing_and_bad_response(self):
        device = self.root/'vcio'; device.write_bytes(b'')
        def reply(_fd, code, buf, _mutate):
            self.assertEqual(code,0xC0086400)
            self.assertEqual(struct.unpack_from('<I',buf,8)[0],0x30080)
            payload=b'throttled=0x50005\0'
            struct.pack_into('<I',buf,4,0x80000000)
            struct.pack_into('<I',buf,16,0x80000000|len(payload))
            buf[24:24+len(payload)]=payload
        self.assertEqual(firmware_throttled(device,ioctl=reply),0x50005)
        with self.assertRaises(OSError):
            firmware_throttled(device,ioctl=lambda *_: None)

    def test_hardware_validator_cannot_run_on_host(self):
        with self.assertRaisesRegex(RuntimeError,'dedicated MEBS Pi image'):
            validate(EXPLORER_KHZ,seconds=1800,root=self.cpufreq,output=self.record)


if __name__ == '__main__':
    unittest.main()
