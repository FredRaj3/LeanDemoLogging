#!/usr/bin/env python3
"""Build the locally instrumented Lean without changing the project's toolchain."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('-j', '--jobs', type=int, default=6)
args = parser.parse_args()
cmake = ROOT / '.build-tools/bin/cmake'
if not cmake.exists():
    found = shutil.which('cmake')
    if not found:
        raise SystemExit('Install CMake, or see README.md for the local build-tools setup.')
    cmake = Path(found)
bootstrap = Path(subprocess.check_output(['elan', 'which', 'lean'], cwd=ROOT, text=True).strip()).parent.parent
env = os.environ.copy()
env['PATH'] = str(cmake.parent) + os.pathsep + env['PATH']
env['LAKE_CACHE_DIR'] = str(ROOT / '.build-tools/lake-cache')
subprocess.run(['python3', str(ROOT / 'scripts/instrument.py')], check=True)
configure = [str(cmake), '--preset', 'release',
             f'-DSTAGE1_PREV_STAGE={bootstrap}', f'-DLEANTAR={bootstrap / "bin/leantar"}',
             '-DUSE_LAKE_CACHE=ON']
if os.uname().sysname == 'Darwin':
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    env['SDKROOT'] = sdk
    configure += [f'-DCMAKE_OSX_SYSROOT={sdk}', f'-DCADICAL_EXTRA_CXX_FLAGS=-isysroot {shlex.quote(sdk)}',
                  '-DCMAKE_PREFIX_PATH=/opt/homebrew']
subprocess.run(configure, cwd=ROOT / 'lean4', env=env, check=True)
subprocess.run(['make', '-C', 'build/release', f'-j{args.jobs}'], cwd=ROOT / 'lean4', env=env, check=True)
print('Built:', ROOT / 'lean4/build/release/stage1/bin/lean')
