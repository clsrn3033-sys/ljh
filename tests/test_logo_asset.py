import base64
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zlib
from PIL import Image
from mebs import boot_animation as boot
from mebs.logo_asset import embedded, load, png


class LogoTests(unittest.TestCase):
    def test_real_corrupt_data_falls_back_without_stopping_splash(self):
        with mock.patch.dict('os.environ', {'MEBS_LOGO': '/nonexistent/mebs-test-logo.png'}):
            value = load(boot.LOGO_MASK, boot.LOGO_SIZE, boot.font(116))
        self.assertEqual(value.source, 'text-fallback')
        self.assertTrue(value.mask.getbbox())
        self.assertIn('Embedded:', value.warning)
        for p in (0, 50, 100):
            image = boot.render(p)
            self.assertEqual(image.size, (1280, 720))

    def test_valid_embedded_payload_exact_size(self):
        im=Image.new('1',(16,16),1)
        code=base64.b85encode(zlib.compress(im.tobytes()))
        self.assertEqual(embedded(code,(16,16)).tobytes(),im.convert('L').tobytes())
        for malformed in (code[:-2],base64.b85encode(zlib.compress(b'x')),base64.b85encode(zlib.compress(im.tobytes())+b'junk')):
            with self.assertRaises((ValueError,zlib.error)):
                embedded(malformed,(16,16))

    def test_explicit_png_alpha_and_aspect(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'logo.png'
            im=Image.new('RGBA',(100,20),(255,255,255,0))
            im.paste((255,255,255,255),(10,0,90,20));im.save(p)
            with mock.patch.dict('os.environ',{'MEBS_LOGO':str(p)}):
                result=load('invalid',(650,132),boot.font(116))
            self.assertEqual(result.source,'png')
            self.assertEqual(result.mask.size,(650,132))
            self.assertTrue(result.mask.getbbox())

    def test_invalid_external_logo_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'logo.png';p.write_bytes(b'bad file')
            with mock.patch.dict('os.environ',{'MEBS_LOGO':str(p)}):
                result=load('invalid',(650,132),boot.font(116))
            self.assertEqual(result.source,'text-fallback')
            self.assertIn('PNG:',result.warning)


class HardwareReportTests(unittest.TestCase):
    def test_non_pi_host_is_not_hardware_confirmation(self):
        spec=importlib.util.spec_from_file_location('hw_report',Path(__file__).resolve().parents[1]/'scripts/pi4-hardware-report.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as t:
            result=module.collect(Path(t))
        self.assertFalse(result['is_pi4b'])
        self.assertEqual(result['drm'],[])

    def test_fake_pi_sysfs_reports_bound_driver_names_only(self):
        spec=importlib.util.spec_from_file_location('hw_report',Path(__file__).resolve().parents[1]/'scripts/pi4-hardware-report.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            model=root/'proc/device-tree/model';model.parent.mkdir(parents=True);model.write_text('Raspberry Pi 4 Model B Rev 1.5\x00')
            dev=root/'sys/bus/i2c/devices/1-0040';dev.mkdir(parents=True);(dev/'name').write_text('ina226')
            result=module.collect(root)
        self.assertTrue(result['is_pi4b'])
        self.assertEqual(result['i2c_bound_devices'][0]['name'],'ina226')
        self.assertIn('INA226 shunt resistance and power rating',result['physical_only_unknowns'])
