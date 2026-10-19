"""Register-level simulation and backup-protection regression tests."""
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

from mebs.gpio_virtual import VirtualI2CBus, pinmap, validate
from mebs.ina import INA226, INA231, SensorError, VirtualINARegisters
from mebs.controls import Controls
from mebs.runtime800 import Sensors, Worker
from mebs.sensors import BatteryGuard, Reading, cpu_temperature, voltage_percent
from mebs.settings import SettingsStore
from mebs.hardware_profile import validate_runtime
from mebs.ui800 import render


class INARegisterTests(unittest.TestCase):
    def test_both_models_eleven_voltage_steps_and_power(self):
        for model, driver in [('INA226', INA226), ('INA231', INA231)]:
            bus = VirtualINARegisters(model, .01)
            monitor = driver(bus, .01, model_confirmed=model == 'INA231')
            for i in range(11):
                voltage = 6.4 + i * .2
                bus.inject(voltage, .5)
                m = monitor.sample()
                self.assertAlmostEqual(m.voltage, voltage, places=2)
                self.assertAlmostEqual(m.current_a, .5, places=2)
                self.assertAlmostEqual(m.power_w, voltage*.5, places=2)
                self.assertEqual(m.source, 'SIMULATION')
                self.assertTrue(m.timestamp_utc)
            bus.inject(7.4, -.5)
            self.assertLess(monitor.sample().current_a, 0)

    def test_model_checks_and_calibration(self):
        b=VirtualINARegisters('INA226', .01)
        with self.assertRaises(SensorError):
            INA231(b, .01)
        b.registers[0xFE] = 0
        with self.assertRaises(SensorError):
            INA226(b, .01)
        b.registers[0xFE] = 0x5449
        self.assertGreater(INA226(b,.01,max_current_a=2,program_calibration=True).calibration,0)
        with self.assertRaises(ValueError):
            INA226(b,.1,max_current_a=2,program_calibration=True)

    def test_disconnect_nack_stale_invalid_and_recovery(self):
        b=VirtualINARegisters('INA231', .01)
        m=INA231(b,.01,model_confirmed=True)
        b.inject(7.4,.2)
        b.connected=False
        with self.assertRaises(OSError): m.sample()
        b.connected=True; b.fail_next=True
        with self.assertRaises(OSError): m.sample()
        b.inject(7.4,.2,updated=time.monotonic()-5)
        with self.assertRaises(SensorError): m.sample()
        b.inject(7.4,.2)
        self.assertAlmostEqual(m.sample().voltage,7.4)
        with self.assertRaises(ValueError): b.inject(90,.2)
        with self.assertRaises(ValueError): b.inject(7.4,999)
        b.registers[0x02] = 0x8000
        with self.assertRaises(SensorError): m.sample()

    def test_real_vs_simulation_and_no_device_open(self):
        with tempfile.TemporaryDirectory() as td:
            c=Controls(SettingsStore(Path(td)/'settings.json'))
            config={'sensor_mode':'SIMULATION','simulation_explicit':True,
                    'ina231':{'enabled':True,'shunt_ohms':.01,'model_confirmed':True},
                    'battery_display_simulation':{'enabled':True,'voltage_v':7.4,'current_a':.5}}
            b=VirtualINARegisters('INA231',.01); b.inject(7.4,.2)
            virtual=VirtualI2CBus(); virtual.attach(0x40,b)
            s=Sensors(config,c,bus_factory=lambda _,address:virtual.device(address))
            s.read()
            self.assertEqual(c.reading.sensor_source,'SIMULATION')
            self.assertIsNone(c.display_battery)
            self.assertAlmostEqual(c.reading.power_w,1.48,places=2)
            c.panel=True
            self.assertEqual(render(c).size,(800,480))
            b.inject(8.4,.2); s.read()
            self.assertAlmostEqual(c.reading.voltage,8.4)
            class OneCycle:
                stopped=False
                seconds=None
                def is_set(self): return self.stopped
                def wait(self,seconds): self.seconds=seconds; self.stopped=True
            cycle=OneCycle(); s.run(cycle)
            self.assertEqual(cycle.seconds,1)
            b.connected=False; s.read()
            self.assertIsNone(c.reading.voltage)
            self.assertEqual(c.reading.sensor_source,'N/A')
            with self.assertRaises(ValueError): Sensors({'sensor_mode':'SIMULATION'},c)


class PinAndGuardTests(unittest.TestCase):
    def test_cpu_temperature_prefers_pi_thermal_then_cpu_hwmon(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); gpu=root/'hwmon0'; cpu=root/'hwmon1'
            gpu.mkdir(); cpu.mkdir()
            (gpu/'name').write_text('amdgpu\n'); (gpu/'temp1_input').write_text('70000\n')
            (cpu/'name').write_text('k10temp\n'); (cpu/'temp1_input').write_text('51875\n')
            thermal=root/'missing-thermal'
            self.assertEqual(cpu_temperature(hwmon_root=root,thermal_path=thermal),51.875)
            thermal.write_text('47000\n')
            self.assertEqual(cpu_temperature(hwmon_root=root,thermal_path=thermal),47.0)

    def test_missing_battery_uses_display_only_simulation(self):
        with tempfile.TemporaryDirectory() as td:
            c=Controls(SettingsStore(Path(td)/'settings.json'),guard=BatteryGuard(block=6.4))
            config={'sensor_mode':'REAL','battery_display_simulation':
                    {'enabled':True,'voltage_v':7.4,'current_a':.5}}
            validate_runtime(config)
            Sensors(config,c).read()
            self.assertIsNone(c.reading.voltage)
            self.assertEqual(c.display_battery.sensor_source,'SIMULATION')
            self.assertAlmostEqual(c.display_battery.voltage,7.4)
            self.assertAlmostEqual(c.display_battery.percent,52.380952,places=4)
            self.assertEqual(c.display_battery.percent_kind,'VOLTAGE_ESTIMATE')
            self.assertFalse(c.begin_job())
            self.assertEqual(c.battery_status(),'UNKNOWN')
            self.assertEqual(render(c).size,(800,480))
            c.reading=Reading(voltage=8.0,sensor_source='SIMULATION',sampled_monotonic=time.monotonic())
            self.assertEqual(c.battery_status(),'UNKNOWN')

            real=VirtualINARegisters('INA226',.01); real.simulation=False
            real.inject(7.8,.3)
            config['ina226']={'enabled':True,'shunt_ohms':.01}
            with mock.patch('mebs.runtime800.I2C',return_value=real):
                Sensors(config,c).read()
            self.assertEqual(c.reading.sensor_source,'REAL')
            self.assertIsNone(c.display_battery)
            self.assertAlmostEqual(c.reading.voltage,7.8)
            self.assertAlmostEqual(c.reading.percent,71.428571,places=4)

    def test_voltage_percent_is_clamped_display_estimate(self):
        self.assertEqual(voltage_percent(6.3),0)
        self.assertEqual(voltage_percent(8.4),100)
        self.assertEqual(voltage_percent(6.0),0)
        self.assertEqual(voltage_percent(8.6),100)
        self.assertAlmostEqual(voltage_percent(7.4),52.380952,places=4)
        self.assertIsNone(voltage_percent(None))
        with self.assertRaises(ValueError): voltage_percent(7.4,8.4,6.3)

    def test_real_profile_requires_confirmed_module_and_pack_path(self):
        config={'sensor_mode':'REAL','i2c_logic_3v3_confirmed':True,
                'ina231':{'enabled':True,'address':0x40,'shunt_ohms':.01,
                          'shunt_power_w':1,'max_current_a':2},
                'battery_thresholds':{'block':6.4},'battery_bms_confirmed':True}
        with self.assertRaisesRegex(ValueError,'INA231 package'):
            validate_runtime(config)
        config['ina231']['model_confirmed']=True
        with self.assertRaisesRegex(ValueError,'VBUS'):
            validate_runtime(config)
        config['battery_pack_vbus_confirmed']=True
        self.assertIs(validate_runtime(config),config)
        config['sensor_mode']='SIMULATION'
        with self.assertRaisesRegex(ValueError,'explicit'):
            validate_runtime(config)

    def test_gpio_mapping_collision_and_isolated_bus(self):
        pins=pinmap()
        self.assertEqual(len(pins),40)
        self.assertEqual({p.physical:p.bcm for p in pins if p.physical in (1,3,5,6,27,28)},
                         {1:None,3:2,5:3,6:None,27:0,28:1})
        self.assertTrue(validate(pins))
        with self.assertRaises(ValueError): validate(pins[:-1])
        bus=VirtualI2CBus(); device=VirtualINARegisters('INA226',.01)
        bus.attach(0x40,device)
        with self.assertRaises(ValueError): bus.attach(0x40,device)
        with self.assertRaises(OSError): bus.device(0x41)

    def test_low_voltage_and_stale_measurement_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            c=Controls(SettingsStore(Path(td)/'settings.json'),guard=BatteryGuard(block=6.4))
            self.assertFalse(c.begin_job())
            c.reading=Reading(voltage=7.4,sensor_source='REAL',sampled_monotonic=time.monotonic())
            self.assertTrue(c.begin_job())
            self.assertFalse(c.battery_stop_required())
            c.reading=Reading(voltage=6.4,sensor_source='REAL',sampled_monotonic=time.monotonic())
            self.assertTrue(c.battery_stop_required())
            c.reading=Reading(voltage=7.4,sensor_source='REAL',sampled_monotonic=time.monotonic()-5)
            self.assertEqual(c.battery_status(),'UNKNOWN')
            self.assertTrue(c.battery_stop_required())


if __name__ == '__main__': unittest.main()
