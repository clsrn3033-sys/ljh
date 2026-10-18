#!/usr/bin/env python3
"""Deterministic asset extraction from the supplied reference, no redesign.

Keep original JPEG byte-for-byte. Crop only the MEBS logotype, retaining tones;
remove near-black JPEG noise. Other reference captions are already runtime text.
"""
import hashlib
import json
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1]
assets = root/'mebs/assets'
original = assets/'mebs-boot-reference.jpg'
box = (315, 195, 978, 335)
with Image.open(original) as source:
    if source.size != (1280, 853):
        raise ValueError('Unexpected reference dimensions; do not guess crop')
    mask = source.crop(box).convert('L').point(lambda p: 0 if p < 12 else p)
mask.save(assets/'mebs-logo-mask.png')
manifest = {'reference':original.name,'reference_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
            'reference_size':[1280,853],'crop_ltrb':box,'transformation':'grayscale mask; values below12=0; no new logo generated',
            'mask':'mebs-logo-mask.png','mask_sha256':hashlib.sha256((assets/'mebs-logo-mask.png').read_bytes()).hexdigest(),
            'reference_credits':'제49기 보도부 이정헌 / Produced by 이정원',
            'runtime_credits':'제49기 보도부 이정헌 / Produced by 이정헌 (user correction)','source':'User attachment 1000065842.jpg'}
(assets/'logo-provenance.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
