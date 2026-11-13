"""Rebuild the optional Minecraft runtime without changing the Python bot."""
import hashlib
import io
import os
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.cache' / 'nur-mc-runtime'
VERSION = 'v22.23.5'
ARCHIVE = f'node-{VERSION}-linux-x64.tar.xz'
SHA256 = 'cdeb8670a0c81f51b4dc4ac61919f9b1ad917b304bf8221eb939570663d240f8'


def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    node_dir = RUNTIME / f'node-{VERSION}-linux-x64'
    if not (node_dir / 'bin' / 'node').is_file():
        with urllib.request.urlopen(f'https://nodejs.org/dist/{VERSION}/{ARCHIVE}', timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise RuntimeError('Node archive checksum mismatch')
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:xz') as tar:
            tar.extractall(RUNTIME, filter='data')
    deps = RUNTIME / 'deps'
    deps.mkdir(exist_ok=True)
    for name in ('package.json', 'package-lock.json'):
        shutil.copyfile(Path(__file__).parent / name, deps / name)
    env = {'PATH': str(node_dir / 'bin') + os.pathsep + '/usr/bin:/bin',
           'NPM_CONFIG_CACHE': str(RUNTIME / 'npm-cache'), 'LANG': 'C.UTF-8'}
    if os.environ.get('HOME'): env['HOME'] = os.environ['HOME']
    subprocess.run([str(node_dir / 'bin' / 'npm'), 'ci', '--ignore-scripts',
                    '--omit=dev', '--no-audit', '--no-fund', '--prefix', str(deps)],
                   env=env, check=True, timeout=180)
    print('Minecraft runtime installed')


if __name__ == '__main__': main()
