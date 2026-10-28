#!/usr/bin/env python3
"""Check the real trace, rejection behavior, and preservation of the original demo."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from render_trace import read_events

ROOT = Path(__file__).resolve().parents[1]
native = ROOT / 'lean4/build/release/stage1/bin/lean'
standard = Path(subprocess.check_output(['elan', 'which', 'lean'], cwd=ROOT, text=True).strip())
demo = 'LeanDemoLogging/KernelDemo.lean'
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
run(['python3', 'scripts/trace.py'])
assert (ROOT / 'traces/inj_comp.stdout.log').read_text() == baseline.stdout
events = read_events(ROOT / 'traces/inj_comp.jsonl')
assert events[-1]['status'] == 'accepted'
assert [e['name'] for e in events if e['event'] == 'phase'] == ['statement', 'proof', 'comparison']
context = {e['name']: e for e in events if e['phase'] == 'proof' and e['event'] == 'context'}
assert context['h1']['type'] == '((f x) = (f y))', context['h1']
assert context['h2']['type'] == '(x = y)', context['h2']
assert 'h0' in context
assert any(e['event'] == 'enter' and e['operation'] == 'unfold' and e['expr'] == 'Function.Injective' for e in events)
assert any(e['event'] == 'enter' and e['operation'] == 'unfold' and e['expr'] == 'Function.comp' for e in events)

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

originals = json.loads((ROOT / 'traces/original-demo-sha256.json').read_text())
for relative, digest in originals.items():
    p = ROOT.parent / relative
    assert hashlib.sha256(p.read_bytes()).hexdigest() == digest, f'Original file changed: {relative}'
print(f'PASS: {len(events)} balanced native kernel events; h0/h1/h2 types; unfolding; real rejection; declaration filter.')
print('PASS: original and instrumented compiler outputs agree, with logging on and off.')
print('PASS: all original LeanDemo files match their initial hashes.')
