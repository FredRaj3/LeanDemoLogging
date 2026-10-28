#!/usr/bin/env python3
"""Check the real trace, rejection behavior, and preservation of the original demo."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from render_trace import read_events

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--declaration', required=True, help='full name of the theorem to trace')
parser.add_argument('--file', required=True, help='Lean file that declares it, relative to this project')
args = parser.parse_args()
native = ROOT / 'lean4/build/release/stage1/bin/lean'
standard = Path(subprocess.check_output(['elan', 'which', 'lean'], cwd=ROOT, text=True).strip())
demo = args.file
options = ['-DElab.async=false', '-DstderrAsMessages=false']
clean_env = {k: v for k, v in os.environ.items() if not k.startswith('LEAN_KERNEL_TRACE_')}


def run(command, env=clean_env):
    p = subprocess.run([str(x) for x in command], cwd=ROOT, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    return p


baseline = run([standard, *options, demo])
untraced = run([native, *options, demo])
assert baseline.stdout == untraced.stdout, 'Instrumented compiler changed the demo output'
assert not untraced.stderr, untraced.stderr
run(['python3', 'scripts/trace.py', '--file', demo, '--declaration', args.declaration])
trace = ROOT / 'traces' / f'{args.declaration}.jsonl'
assert trace.with_suffix('.stdout.log').read_text() == baseline.stdout
events = read_events(trace)
assert events[-1]['status'] == 'accepted'
assert [e['name'] for e in events if e['event'] == 'phase'] == ['statement', 'proof', 'comparison']


def top_level(phase):
    return [e for e in events if e['phase'] == phase and e['depth'] == 0 and e['event'] in ('enter', 'return')]


assert top_level('statement')[0]['operation'] == 'check', 'No top-level check of the statement'
assert top_level('proof')[0]['operation'] == 'check', 'No top-level check of the proof'
assert top_level('comparison')[-1].get('result') == 'true', 'Final type comparison did not succeed'
calls = [e for e in events if e['event'] == 'enter']
assert all('purpose' in e for e in calls if e['depth'] == 0), 'A top-level call has no recorded purpose'
labeled = sum('purpose' in e for e in calls)

run(['python3', 'scripts/trace.py', '--file', 'tests/BadApplication.lean',
     '--declaration', 'inj_comp_bad', '--output', 'traces/rejected-application.jsonl'])
bad = read_events(ROOT / 'traces/rejected-application.jsonl')
assert bad[-1]['status'] == 'exception'
assert any(e['event'] == 'return' and e.get('result') == 'false' for e in bad)
message = (ROOT / 'traces/rejected-application.stdout.log').read_text()
assert 'EXPECTED KERNEL REJECTION' in message and '(kernel) application type mismatch' in message
assert 'UNEXPECTED ACCEPTANCE' not in message

# A filter that matches no declaration must produce no kernel events.
unused = ROOT / 'traces/filter-check.jsonl'
unused.write_text('')
run([native, *options, demo], dict(clean_env, LEAN_KERNEL_TRACE_DECL='no_such_theorem', LEAN_KERNEL_TRACE_FILE=str(unused)))
assert unused.read_text() == ''

print(f'PASS: {len(events)} balanced native kernel events; statement, proof and comparison checks; real rejection; declaration filter.')
print('PASS: original and instrumented compiler outputs agree, with logging on and off.')
print(f'INFO: {labeled} of {len(calls)} calls have a recorded purpose.')

originals = json.loads((ROOT / 'traces/original-demo-sha256.json').read_text())
if (ROOT.parent / 'LeanDemo').is_dir():
    for relative, digest in originals.items():
        p = ROOT.parent / relative
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest, f'Original file changed: {relative}'
    print('PASS: all original LeanDemo files match their initial hashes.')
else:
    print('SKIP: no ../LeanDemo folder, so the original-file hash check was not run.')
