import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

from PIL import Image

from mebs.explorer_v3 import Browser, ExplorerError, VideoPreview
from mebs.controls import Controls
from mebs.settings import SettingsStore
from mebs.ui_explorer_v3 import ExplorerUI
from mebs.ui_explorer_v3_layout import render
from mebs.runtime800 import publish_status


class ExplorerV3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.source, self.target = base/'camera', base/'disk'
        self.source.mkdir(); self.target.mkdir()
        (self.source/'DCIM').mkdir()
        (self.source/'DCIM'/'촬영 1.xml').write_text('<metadata/>')
        Image.new('RGB', (32, 20), 'cyan').save(self.source/'DCIM'/'photo.jpg')
        self.idle = True
        self.browser = Browser(self.source, self.target, idle=lambda: self.idle, simulation=True)

    def test_listing_preview_sort_and_no_media(self):
        rows = self.browser.listdir('source', 'DCIM', 'size')
        self.assertEqual({r['name'] for r in rows}, {'촬영 1.xml', 'photo.jpg'})
        self.assertEqual(self.browser.thumbnail('source', 'DCIM/photo.jpg').size, (32, 20))
        self.assertGreater(self.browser.capacity('target')['free'], 0)
        with self.assertRaisesRegex(ExplorerError, '미디어 없음'):
            Browser().listdir('source')
        with self.assertRaises(ExplorerError):
            self.browser.listdir('source', '../disk')

    def test_links_are_blocked(self):
        (self.source/'DCIM'/'outside').symlink_to(self.target)
        row = next(x for x in self.browser.listdir('source', 'DCIM') if x['name'] == 'outside')
        self.assertTrue(row['blocked'])
        with self.assertRaises(ExplorerError):
            self.browser.info('source', 'DCIM/outside')

    def test_explicit_copy_hash_no_overwrite_and_restricted_mutations(self):
        with self.assertRaises(ExplorerError):
            self.browser.copy_from_source('DCIM/photo.jpg')
        self.idle = False
        with self.assertRaises(ExplorerError):
            self.browser.copy_from_source('DCIM/photo.jpg', confirm=True)
        self.idle = True
        result = self.browser.copy_from_source('DCIM/photo.jpg', confirm=True)
        dest = Path(result['path'])
        self.assertEqual(hashlib.sha256(dest.read_bytes()).hexdigest(), result['sha256'])
        self.assertEqual(dest.read_bytes(), (self.source/'DCIM'/'photo.jpg').read_bytes())
        with self.assertRaises(ExplorerError):
            self.browser.copy_from_source('DCIM/photo.jpg', confirm=True)
        self.assertEqual(self.browser.move_target('MEBS_FILES/photo.jpg', confirm=True), str(dest.parent/'Archive/photo.jpg'))
        with self.assertRaises(ExplorerError):
            self.browser.delete_target('mebs-backup-old/manifest.json', confirm=True)
        with self.assertRaises(ExplorerError):
            self.browser.delete_target('MEBS_FILES/Archive/photo.jpg')
        self.browser.delete_target('MEBS_FILES/Archive/photo.jpg', confirm=True)
        self.assertFalse((dest.parent/'Archive/photo.jpg').exists())
        self.assertTrue((self.source/'DCIM'/'photo.jpg').exists())

    def test_probe_video_and_restrict_high_profile(self):
        clip = self.source/'DCIM'/'clip.mp4'
        command = ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=64x48:r=10',
                   '-t', '0.3', '-c:v', 'mpeg4', str(clip)]
        subprocess.run(command, check=True, capture_output=True, timeout=20)
        info = self.browser.probe_video('source', 'DCIM/clip.mp4')
        self.assertEqual(info['codec'], 'mpeg4')
        self.assertFalse(info['software_preview'])
        self.assertEqual(self.browser.thumbnail('source', 'DCIM/clip.mp4').mode, 'RGB')
        clip.write_bytes(b'corrupt')
        with self.assertRaises(ExplorerError):
            self.browser.probe_video('source', 'DCIM/clip.mp4')

    def test_sony_fx3_like_4k_422_10bit_is_information_only(self):
        clip = self.source/'DCIM'/'FX3.MOV'
        clip.write_bytes(b'fixture')
        payload = {'streams':[{'codec_type':'video','codec_name':'hevc','profile':'Main 4:2:2 10',
                               'width':3840,'height':2160,'pix_fmt':'yuv422p10le',
                               'avg_frame_rate':'30000/1001','bit_rate':'200000000'}]}
        runner = lambda *_args, **_kw: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr='')
        info = self.browser.probe_video('source','DCIM/FX3.MOV',runner=runner)
        self.assertEqual(info['bit_depth'],10)
        self.assertEqual(info['codec'],'hevc')
        self.assertFalse(info['software_preview'])
        self.assertEqual(info['hardware_acceleration'],'NOT TESTED')

    def test_h264_software_preview_and_shutdown_interlock(self):
        clip = self.source/'DCIM'/'play.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=64x48:r=10',
                        '-t', '1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(clip)],
                       check=True, capture_output=True, timeout=20)
        info = self.browser.probe_video('source', 'DCIM/play.mp4')
        self.assertTrue(info['software_preview'])
        player = VideoPreview(clip)
        player.start()
        deadline = time.monotonic() + 5
        while player.image() is None and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertIsNotNone(player.image())
        player.stop()
        c = Controls(SettingsStore(Path(self.tmp.name)/'settings.json'))
        c.explorer_active = True
        self.assertFalse(c.begin_job())
        c.request_shutdown(); c.confirm_shutdown()
        self.assertFalse(c.shutdown_ready())

    def test_raw_fallback_and_ui_reference_layout(self):
        (self.source/'DCIM'/'sony.ARW').write_bytes(b'not actual raw')
        session = SimpleNamespace(browser=self.browser,
                                  control=SimpleNamespace(reading=SimpleNamespace(cpu_c=None,ram_percent=None,voltage=None)),
                                  close=lambda: None)
        ui = ExplorerUI(session)
        ui.path = Path('DCIM')
        ui.select(next(x for x in ui.browser.listdir('source', 'DCIM') if x['name'] == 'sony.ARW'))
        self.assertIsNone(ui.preview)
        self.assertEqual(render(ui).size, (800, 480))
        self.assertIn('미리보기', ui.notice)

    def test_empty_media_explorer_screen(self):
        control=SimpleNamespace(reading=SimpleNamespace(cpu_c=None,ram_percent=None,voltage=None),state={'demo':True})
        ui=ExplorerUI(SimpleNamespace(browser=Browser(),control=control,close=lambda:None))
        self.assertEqual(render(ui).size,(800,480))
        self.assertEqual(ui.notice,'미디어 없음')

    def test_runtime_status_is_published_atomically(self):
        status = Path(self.tmp.name)/'status.json'
        publish_status(status, json.dumps({'generation':0,'padding':'x'*40000}))
        failures = []
        def writer():
            for generation in range(1,60):
                publish_status(status, json.dumps({'generation':generation,'padding':'x'*40000}))
        thread = threading.Thread(target=writer)
        thread.start()
        while thread.is_alive():
            try:
                value = json.loads(status.read_text())
                if len(value['padding']) != 40000:
                    failures.append('truncated status')
            except (OSError, ValueError) as exc:
                failures.append(str(exc))
        thread.join()
        self.assertEqual(failures, [])
        self.assertEqual(json.loads(status.read_text())['generation'],59)
        self.assertEqual(list(status.parent.glob('.status-*.tmp')),[])


if __name__ == '__main__':
    unittest.main()
