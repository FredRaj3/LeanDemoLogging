#!/usr/bin/env python3
"""Run the copied demo through the instrumented native kernel."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from render_trace import read_events, render

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--declaration', default='inj_comp')
parser.add_argument('--file', default='LeanDemoLogging/KernelDemo.lean')
parser.add_argument('--output', default='traces/inj_comp.jsonl')
args = parser.parse_args()
lean = ROOT / 'lean4/build/release/stage1/bin/lean'
if not lean.is_file():
    raise SystemExit('Build the instrumented Lean first: python3 scripts/build.py')
trace = ROOT / args.output
trace.parent.mkdir(parents=True, exist_ok=True)
trace.write_text('')
env = dict(os.environ, LEAN_KERNEL_TRACE_DECL=args.declaration, LEAN_KERNEL_TRACE_FILE=str(trace))
command = [str(lean), '-DElab.async=false', '-DstderrAsMessages=false', args.file]
source_text = (ROOT / args.file).read_text()
result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
trace.with_suffix('.stdout.log').write_text(result.stdout)
trace.with_suffix('.stderr.log').write_text(result.stderr)
if result.returncode:
    print(result.stdout + result.stderr)
    raise SystemExit(result.returncode)
events = read_events(trace)
metadata = {'command': command, 'source': args.file, 'source_text': source_text,
            'declaration': args.declaration,
            'lean_version': subprocess.check_output([str(lean), '--version'], text=True).strip(),
            'events': len(events), 'status': events[-1]['status']}
trace.with_suffix('.metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
render(trace)
print(f"Recorded {len(events)} kernel events; declaration {events[-1]['status']}.")
print('Viewer:', trace.with_suffix('.html'))
print('Text:  ', trace.with_suffix('.txt'))
print('Raw:   ', trace)
