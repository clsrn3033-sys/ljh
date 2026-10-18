"""Validated logo input. Corrupt embedded data must never stop the boot UI.

An explicit supplied PNG takes precedence; no guessed reconstruction is shipped.
Fallback is the existing MEBS text, visibly labelled as temporary by callers.
"""
import base64
from importlib import resources
from dataclasses import dataclass
import os
from pathlib import Path
import zlib
from PIL import Image, ImageDraw, ImageFont, ImageOps


@dataclass
class Logo:
    mask: Image.Image
    source: str
    warning: str = ''


def embedded(code, size):
    expected = ((size[0]+7)//8)*size[1]
    compressed = base64.b85decode(code)
    decoder = zlib.decompressobj()
    packed = decoder.decompress(compressed, expected+1)
    if (len(packed) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail):
        raise ValueError('Embedded logo length/checksum/stream mismatch')
    return Image.frombytes('1', size, packed).convert('L')


def png(path, size):
    path = Path(path)
    if path.stat().st_size > 2*1024*1024:
        raise ValueError('Logo PNG exceeds 2 MiB')
    with Image.open(path) as image:
        if image.format != 'PNG' or image.width*image.height > 4_000_000 or getattr(image, 'n_frames', 1) != 1:
            raise ValueError('A single static PNG up to 4 megapixels is required')
        image.load()
        rgba = image.convert('RGBA')
        alpha = rgba.getchannel('A')
        mask = alpha if alpha.getextrema() != (255, 255) else image.convert('L')
        box = mask.getbbox()
        if box is None:
            raise ValueError('Empty logo mask')
        result = ImageOps.contain(mask.crop(box), size, Image.Resampling.LANCZOS)
        canvas = Image.new('L', size)
        canvas.paste(result, ((size[0]-result.width)//2, (size[1]-result.height)//2))
        return canvas


def load(code, size, font):
    errors = []
    selected = os.environ.get('MEBS_LOGO')
    paths = [Path(selected)] if selected else [Path('/etc/mebs/logo.png')]
    for path in paths:
        if not selected and not path.exists():
            continue
        try:
            return Logo(png(path, size), 'png')
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            errors.append('PNG: '+str(exc))
    if not selected:
        try:
            bundled = resources.files('mebs').joinpath('assets', 'mebs-logo-mask.png')
            if bundled.is_file():
                with resources.as_file(bundled) as asset_path:
                    return Logo(png(asset_path, size), 'png', '; '.join(errors))
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            errors.append('Bundled PNG: '+str(exc))
    try:
        return Logo(embedded(code, size), 'embedded', '; '.join(errors))
    except (ValueError, zlib.error) as exc:
        errors.append('Embedded: '+str(exc))
    mask = Image.new('L', size)
    draw = ImageDraw.Draw(mask)
    # Use main project's existing text identity; not a replacement approved logo.
    draw.text((size[0]//2, size[1]//2), 'MEBS', font=font, fill=255, anchor='mm')
    return Logo(mask, 'text-fallback', '; '.join(errors))
