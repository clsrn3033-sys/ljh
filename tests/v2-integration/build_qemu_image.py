#!/usr/bin/env python3
"""Make a separate QEMU virt raw image from a Pi image, without host mounts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).with_name('run.py')

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pi_images', type=Path)
    parser.add_argument('qemu_image', type=Path)
    args = parser.parse_args()
    images = args.pi_images.resolve()
    output = args.qemu_image.resolve()
    if output.exists() or output.parent.exists() and any(output.parent.iterdir()):
        raise SystemExit('Use a new empty output directory and image path')
    original = sha(images/'sdcard.img')
    spec = importlib.util.spec_from_file_location('integration_run', RUN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='mebs-qemu-build-') as temp:
        adapted = module.prepare_os(images, Path(temp))
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(adapted, output)
    assert sha(images/'sdcard.img') == original
    record = {'pi_image':str(images/'sdcard.img'),'pi_sha256':original,
              'qemu_image':str(output),'qemu_sha256':sha(output),
              'adaptation':'Only OS-owned settings fstab mmcblk0p3 -> vda3 in separate image. Boot via Image kernel and virtio disk.',
              'hardware_tested':False}
    (output.parent/'QEMU_IMAGE_PROVENANCE.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))

if __name__ == '__main__':
    main()
