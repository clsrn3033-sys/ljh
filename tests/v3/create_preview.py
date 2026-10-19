#!/usr/bin/env python3
"""Create one honest 800x480 UI screenshot from disposable directory media."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mebs.explorer_v3 import Browser
from mebs.ui_explorer_v3 import ExplorerUI
from mebs.ui_explorer_v3_layout import render

OUTPUT = ROOT/'docs/v3/explorer-preview.png'


def main():
    with tempfile.TemporaryDirectory(prefix='mebs-v3-preview-') as tmp:
        base = Path(tmp)
        source, target = base/'camera', base/'external'
        source.mkdir(); target.mkdir()
        dcim = source/'DCIM'
        dcim.mkdir()
        picture = Image.new('RGB', (400, 235), '#7ac7e8')
        draw = ImageDraw.Draw(picture)
        draw.rectangle((0, 150, 400, 235), fill='#35678a')
        draw.polygon([(0, 176), (97, 115), (180, 162), (275, 120), (400, 190)], fill='#183956')
        picture.save(dcim/'DSC0001.JPG')
        (dcim/'C0001.XML').write_text('<camera>FX3</camera>')
        (dcim/'C0001.ARW').write_bytes(b'SIMULATED RAW; NOT A CAMERA FILE')
        for index in range(2, 6):
            (dcim/f'C{index:04d}.MP4').write_bytes(b'SIMULATED VIDEO; NOT A CAMERA FILE')
        browser = Browser(source, target, simulation=True)
        control = SimpleNamespace(reading=SimpleNamespace(cpu_c=None, ram_percent=None, voltage=None),
                                  state={'demo': True})
        session = SimpleNamespace(browser=browser, control=control, close=lambda: None)
        ui = ExplorerUI(session)
        ui.path = Path('DCIM')
        ui.select(next(item for item in browser.listdir('source', 'DCIM') if item['name'] == 'DSC0001.JPG'))
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        render(ui).save(OUTPUT)
        print(OUTPUT)


if __name__ == '__main__':
    main()
