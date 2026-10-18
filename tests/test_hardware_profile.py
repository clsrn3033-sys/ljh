import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock
from mebs.hardware_profile import validate_runtime
from mebs import boot_animation as boot

ROOT=Path(__file__).resolve().parents[1]


class HardwareProfileTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((ROOT/'buildroot/board/mebs-pi4-dsi/overlay/etc/mebs/hardware.json').read_text())

    def test_unconfirmed_defaults_remain_headless_and_sensors_off(self):
        validate_runtime(self.config)
        self.assertFalse(self.config['ina226']['enabled'])
        self.assertIsNone(self.config['drm_card'])

    def test_3v3_confirmation_required_before_i2c(self):
        self.config['bh1750']['enabled']=True
        with self.assertRaisesRegex(ValueError,'3.3V'):
            validate_runtime(self.config)

    def test_shunt_rating_and_range(self):
        self.config['i2c_logic_3v3_confirmed']=True
        self.config['ina226'].update(enabled=True,shunt_ohms=.01,shunt_power_w=.5,max_current_a=3)
        validate_runtime(self.config)
        self.config['ina226']['max_current_a']=10
        with self.assertRaises(ValueError):validate_runtime(self.config)
        self.config['ina226'].update(max_current_a=3,shunt_power_w=.01)
        with self.assertRaisesRegex(ValueError,'rating'):validate_runtime(self.config)

    def test_reported_full_voltage_not_used_as_bms_threshold(self):
        design=json.loads((ROOT/'hardware/mebs-pi4b-revA.json').read_text())
        self.assertEqual(design['battery']['user_voltage_v'],8.4)
        self.assertIsNone(self.config['battery_thresholds']['block'])
        self.config['battery_thresholds'].update(warn=7.1,block=6.8)
        with self.assertRaisesRegex(ValueError,'Battery/BMS'):
            validate_runtime(self.config)

    def test_touch_and_dsi_not_enabled_by_resolution_alone(self):
        self.config['touch']['device']='/dev/input/event0'
        with self.assertRaisesRegex(ValueError,'touch controller'):
            validate_runtime(self.config)
        self.config['touch']['device']=None
        self.config['drm_card']='/dev/dri/card0'
        with self.assertRaisesRegex(ValueError,'panel'):
            validate_runtime(self.config)

    def test_gpio_cutoff_rejected(self):
        self.config['power_cutoff']['gpio_enabled']=True
        with self.assertRaisesRegex(ValueError,'GPIO'):
            validate_runtime(self.config)

    def test_supplied_logo_original_and_derived_hashes(self):
        manifest=json.loads((ROOT/'mebs/assets/logo-provenance.json').read_text())
        for filename,key in [(manifest['reference'],'reference_sha256'),(manifest['mask'],'mask_sha256')]:
            self.assertEqual(hashlib.sha256((ROOT/'mebs/assets'/filename).read_bytes()).hexdigest(),manifest[key])
        with mock.patch.dict('os.environ',{},clear=True):
            from mebs.logo_asset import load
            logo=load(boot.LOGO_MASK,boot.LOGO_SIZE,boot.font(116))
        self.assertEqual(logo.source,'png')
        self.assertTrue(logo.mask.getbbox())

    def test_logo_is_available_inside_zip_application(self):
        import os
        import subprocess
        import sys
        subprocess.run([sys.executable,str(ROOT/'scripts/build.py')],check=True,capture_output=True)
        env=dict(os.environ)
        env.pop('MEBS_LOGO',None)
        env['MEBS_TEST_ARCHIVE']=str(ROOT/'dist/mebs.pyz')
        code="import os,sys;sys.path.insert(0,os.environ['MEBS_TEST_ARCHIVE']);from mebs.boot_animation import logo_asset;assert logo_asset().source=='png'"
        result=subprocess.run([sys.executable,'-c',code],cwd='/tmp',env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
