#!/usr/bin/env python3
"""Extract signed APT packages locally. Never installs host packages or bypasses trust."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1] / '.local-build'
state = root / 'apt'
for name in ('lists/partial', 'archives/partial', 'empty'):
    (state / name).mkdir(parents=True, exist_ok=True)
(state / 'status').touch()
(state / 'sources.list').write_text('deb [arch=amd64 signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian trixie main\n')
opts = {'Dir::Etc::sourcelist': state / 'sources.list', 'Dir::Etc::sourceparts': state / 'empty',
        'Dir::State::lists': state / 'lists', 'Dir::State::status': state / 'status',
        'Dir::Cache::archives': state / 'archives', 'Debug::NoLocking': 'true',
        'Acquire::Languages': 'none', 'Acquire::AllowInsecureRepositories': 'false',
        'APT::Get::AllowUnauthenticated': 'false', 'APT::Update::Error-Mode': 'any',
        'APT::Sandbox::User': os.environ.get('USER', 'root')}
apt = ['apt-get']
for key, value in opts.items():
    apt += ['-o', f'{key}={value}']
subprocess.run(apt + ['update'], check=True)
subprocess.run(apt + ['--assume-yes', '--download-only', '--no-install-recommends', 'install',
                     'cpio', 'rsync', 'bc', 'bison', 'flex', 'fonts-noto-cjk', 'libdrm-dev', 'libssl-dev', 'libelf-dev'], check=True)
extracted = root / 'sysroot'
extracted.mkdir(exist_ok=True)
manifest = []
for package in sorted((state / 'archives').glob('*.deb')):
    subprocess.run(['dpkg-deb', '-x', str(package), str(extracted)], check=True)
    manifest.append({'file': package.name, 'sha256': hashlib.sha256(package.read_bytes()).hexdigest()})
(root / 'packages.json').write_text(json.dumps(manifest, indent=2) + '\n')
# Executable wrappers use matching loader/libraries. No LD_LIBRARY_PATH for host Python.
bin_dir = root / 'tools/bin'
bin_dir.mkdir(parents=True, exist_ok=True)
loader = extracted / 'usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2'
libs = extracted / 'usr/lib/x86_64-linux-gnu'
for name in ('cpio', 'rsync', 'bc', 'bison', 'flex'):
    binary = extracted / 'usr/bin' / name
    wrapper = bin_dir / name
    wrapper.write_text(f'#!/bin/sh\nexec "{loader}" --library-path "{libs}" "{binary}" "$@"\n')
    wrapper.chmod(0o755)
print('Tools extracted:', bin_dir)
