#!/usr/bin/env python3
"""Render recorded kernel events; never invent or replay checking steps."""
import argparse
from collections import Counter
from html import escape
import json
from pathlib import Path


def read_events(path):
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not events or events[0]['event'] != 'begin':
        raise ValueError('No kernel trace was recorded. Use the instrumented executable.')
    stack = []
    for index, event in enumerate(events, 1):
        assert event['seq'] == index, 'Trace sequence has a gap'
        if event['event'] == 'enter':
            assert event['depth'] == len(stack)
            stack.append(event['call'])
        elif event['event'] == 'return':
            assert stack.pop() == event['call'], 'Unbalanced call/return trace'
            assert event['depth'] == len(stack)
    assert not stack, 'Incomplete trace'
    assert events[-1]['event'] == 'end', 'Missing end of declaration'
    return events


def description(e):
    kind = e['event']
    if kind == 'enter':
        s = f"{e['operation'].upper()} #{e['call']}: {e['expr']}"
        if 'other' in e:
            s += '  =?=  ' + e['other']
        return s
    if kind == 'return':
        return f"RETURN #{e['call']}: {e.get('result', e.get('status', ''))}"
    if kind == 'context':
        s = f"CONTEXT: {e['name']} : {e['type']}"
        return s + (' := ' + e['value'] if 'value' in e else '')
    if kind == 'argument':
        return f"ARGUMENT TYPE: {e['actual']}\nEXPECTED TYPE: {e['expected']}"
    if kind == 'phase':
        return 'PHASE: ' + e['name']
    if kind == 'cache':
        return 'CACHE HIT: ' + e['name']
    if kind == 'begin':
        return 'BEGIN: ' + e['declaration']
    if kind == 'end':
        return 'END: ' + e['status']
    return kind.upper()


def text_view(events):
    lines = []
    for e in events:
        prefix = f"{e['seq']:04d} " + '  ' * e['depth']
        lines.extend(prefix + line for line in description(e).splitlines())
    return '\n'.join(lines) + '\n'


def term(pretty, core=None):
    return ('<span class="term" data-pretty="' + escape(pretty, quote=True) +
            '" data-core="' + escape(core or pretty, quote=True) + '">' + escape(pretty) + '</span>')


PHASES = {
    'declaration': 'Declaration',
    'statement': 'Statement checking',
    'proof': 'Proof checking',
    'comparison': 'Final type comparison',
}


def html_view(events, source=None):
    # One row per recorded event, including returns and declaration boundaries.
    rows = []
    for e in events:
        kind = e['event']
        label = e.get('operation', kind).upper()
        fold = ''
        if kind == 'enter':
            fold = (f'<button class="fold" data-call="{e["call"]}" '
                    'aria-expanded="true" aria-label="Collapse nested events">−</button>')
            body = term(e['expr'], e.get('core'))
            if 'other' in e:
                body += ' <span class="operator">=?=</span> ' + term(e['other'], e.get('other_core'))
        elif kind == 'return':
            body = term(e.get('result', e.get('status', '')), e.get('result_core'))
        elif kind == 'context':
            body = escape(e['name']) + ' : ' + term(e['type'], e.get('type_core'))
            if 'value' in e:
                body += ' := ' + term(e['value'])
        elif kind == 'argument':
            body = ('Actual: ' + term(e['actual']) + '<br>Expected: ' + term(e['expected']))
        elif kind == 'phase':
            body = escape(PHASES.get(e['name'], e['name']))
        elif kind == 'begin':
            body = escape(e['declaration'])
        elif kind == 'end':
            body = escape(e['status'])
        elif kind == 'cache':
            body = escape(e['name'])
        else:
            body = escape(description(e))
        call = f'<span class="call-id">call {e["call"]}</span>' if 'call' in e else ''
        rows.append(
            f'<div class="event" id="event-{e["seq"]}" data-seq="{e["seq"]}" '
            f'data-phase="{escape(e["phase"], quote=True)}" data-kind="{kind}" '
            f'style="--depth:{min(e["depth"], 12)}" tabindex="0">'
            f'<div class="event-head">{fold}<span class="sequence">#{e["seq"]}</span>'
            f'<b>{label}</b>{call}<span class="phase-label">{escape(PHASES.get(e["phase"], e["phase"]))}</span></div>'
            f'<div class="event-body">{body}</div><span class="fold-note" hidden></span></div>')

    data = json.dumps({'events': events, 'source': source}, ensure_ascii=False)
    # JSON is embedded as data, never as executable code (including Lean strings).
    data = data.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    counts = Counter(e['operation'] for e in events if e['event'] == 'enter')
    template = Path(__file__).with_name('trace_view.html').read_text()
    # Substitute in one pass so source text cannot be interpreted as a placeholder.
    from string import Template
    return Template(template).substitute(
        title=escape(events[0]['declaration']),
        status=escape(events[-1]['status']),
        counts=escape(', '.join(f'{n} {op}' for op, n in counts.items())),
        total=len(events), rows='\n'.join(rows), data=data)


def read_source(path):
    metadata_path = path.with_suffix('.metadata.json')
    if not metadata_path.is_file():
        return None
    metadata = json.loads(metadata_path.read_text())
    name = metadata.get('source')
    if not name:
        return None
    if 'source_text' in metadata:
        return {'name': name, 'text': metadata['source_text'], 'captured': True}
    # Older recordings did not capture their source. Label this fallback explicitly.
    source_path = Path(__file__).resolve().parents[1] / name
    if source_path.is_file():
        return {'name': name, 'text': source_path.read_text(), 'captured': False}
    return None


def render(path):
    events = read_events(path)
    path.with_suffix('.txt').write_text(text_view(events))
    path.with_name(path.stem + '.proof.txt').write_text(text_view([e for e in events if e['phase'] == 'proof']))
    path.with_suffix('.html').write_text(html_view(events, read_source(path)))
    return events


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('trace', type=Path)
    args = parser.parse_args()
    events = render(args.trace)
    print(f'Rendered {len(events)} recorded events to {args.trace.with_suffix(".html")}')
