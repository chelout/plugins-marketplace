#!/usr/bin/env python3
"""Token usage of drawing episodes, imported as-is from the design session of 2026-09-17.

Reads OUT_DIR/drawing_episodes.json and OUT_DIR/agents.json written by skill_analytics.py.
Agents are counted whole; inline sessions only over the segments between user prompts that
contain drawing work. Usage is taken once per message id (the last record) and summed over
usage.iterations.

Usage: skill_tokens.py [OUT_DIR]   (default: out)
"""
import collections
import json
import os
import re
import statistics
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else 'out'
eps = json.load(open(os.path.join(OUT, 'drawing_episodes.json')))
agents = json.load(open(os.path.join(OUT, 'agents.json')))
RENDER = re.compile(r'drawing-(?:diagrams|db-schemas)/render\.py')
SKILLFILE = re.compile(r'skills/drawing-(?:diagrams|db-schemas)/')


def usage_numbers(u):
    its = u.get('iterations') or [u]
    s = lambda k: sum((i.get(k) or 0) for i in its)
    cw = s('cache_creation_input_tokens')
    if not cw and isinstance(u.get('cache_creation'), dict):
        cw = sum(v or 0 for v in u['cache_creation'].values())
    return {'in': s('input_tokens'), 'cw': cw, 'cr': s('cache_read_input_tokens'), 'out': s('output_tokens'),
            'think': (u.get('output_tokens_details') or {}).get('thinking_tokens') or 0}


def is_prompt(rec):
    if rec.get('type') != 'user' or rec.get('isMeta') or rec.get('isCompactSummary'):
        return False
    c = (rec.get('message') or {}).get('content')
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in c):
            return False
        c = ' '.join(b.get('text', '') for b in c if isinstance(b, dict) and b.get('type') == 'text')
    return isinstance(c, str) and bool(c.strip()) and not c.startswith(('<local-command', '<system-reminder>')) and 'Base directory for this skill' not in c


def load_calls(path):
    calls, order, seg, segs = {}, [], -1, []
    for line in open(path, errors='ignore'):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if is_prompt(rec):
            seg += 1
            c = (rec.get('message') or {}).get('content')
            text = c if isinstance(c, str) else ' '.join(b.get('text', '') for b in c if isinstance(b, dict))
            segs.append(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text)).strip()[:48])
            continue
        if rec.get('type') != 'assistant':
            continue
        msg = rec.get('message') or {}
        mid = msg.get('id')
        if mid not in calls:
            calls[mid] = {'seg': max(seg, 0), 'tools': [], 'ts': rec.get('timestamp', '')}
            order.append(mid)
        calls[mid]['usage'] = msg.get('usage') or {}
        for b in msg.get('content') or []:
            if isinstance(b, dict) and b.get('type') == 'tool_use':
                calls[mid]['tools'].append(b)
    out = []
    for mid in order:
        c = calls[mid]
        n = usage_numbers(c['usage'])
        n['ctx'] = n['in'] + n['cw'] + n['cr']
        out.append({**c, **n})
    return out, segs


def classify(tool):
    nm, inp = tool.get('name', ''), tool.get('input') or {}
    s = json.dumps(inp, ensure_ascii=False)
    if nm == 'Skill' and 'drawing' in str(inp.get('skill')): return 'skill-load'
    if nm == 'Bash' and RENDER.search(inp.get('command') or ''): return 'render'
    if nm.endswith('show_widget'): return 'show_widget'
    if nm == 'Artifact': return 'artifact'
    if nm in ('Read',) and SKILLFILE.search(inp.get('file_path') or ''): return 'read-skill-file'
    if nm == 'Bash' and SKILLFILE.search(inp.get('command') or '') and re.search(r'\b(cat|sed|head|tail|rg|grep)\b', inp.get('command') or ''): return 'read-skill-file'
    if nm in ('Write', 'Edit') and str(inp.get('file_path', '')).endswith('.json') and 'grid' in s: return 'model-json'
    return None


def totals(calls):
    t = collections.Counter()
    for c in calls:
        for k in ('in', 'cw', 'cr', 'out', 'think'): t[k] += c[k]
    t['calls'] = len(calls)
    ctx = [c['ctx'] for c in calls] or [0]
    t['ctx_start'], t['ctx_med'], t['ctx_max'] = ctx[0], int(statistics.median(ctx)), max(ctx)
    return t


def fmt(t):
    k = lambda v: f'{v/1000:.1f}K' if v < 1_000_000 else f'{v/1e6:.2f}M'
    return (f"вызовов {t['calls']:3d} | выход {k(t['out']):>6} (мышл. {k(t['think']):>6}) | запись кэша {k(t['cw']):>6} | "
            f"чтение кэша {k(t['cr']):>7} | без кэша {k(t['in']):>5} | контекст старт {k(t['ctx_start'])}, медиана {k(t['ctx_med'])}, макс {k(t['ctx_max'])}")


growth = collections.defaultdict(list)


def record_growth(calls):
    for i, c in enumerate(calls[:-1]):
        kinds = [classify(t) for t in c['tools']]
        if len(c['tools']) != 1 or kinds[0] not in ('skill-load', 'read-skill-file'): continue
        g = calls[i + 1]['ctx'] - c['ctx'] - c['out']
        if g > 0:
            inp = c['tools'][0].get('input') or {}
            target = 'SKILL.md body' if kinds[0] == 'skill-load' else re.sub(r'.*skills/drawing-[\w-]+/', '', inp.get('file_path') or inp.get('command') or '')[:40]
            growth[target].append(g)


print('=== АГЕНТЫ (весь транскрипт = задача рисования) ===')
labels = {e['path']: f"#{i} {e['dispatch']['description'][:42]}" for i, e in enumerate(eps, 1) if e['kind'] == 'агент'}
clean = next((a for a in agents if a['dispatch']['description'].startswith('Clean baseline')), None)
if clean: labels[clean['path']] = 'Clean baseline: schema without skill'
for path, label in sorted(labels.items(), key=lambda x: x[1]):
    calls, _ = load_calls(path)
    record_growth(calls)
    t = totals(calls)
    print(f'{label:46} {fmt(t)}')

print('\n=== СЕССИИ: только отрезки между сообщениями пользователя, где была отрисовка ===')
for i, e in enumerate(eps, 1):
    if e['kind'] != 'сессия': continue
    calls, segs = load_calls(e['path'])
    record_growth(calls)
    by_seg = collections.defaultdict(list)
    for c in calls: by_seg[c['seg']].append(c)
    drawing = [s for s, cs in by_seg.items() if any(classify(t) in ('skill-load', 'render', 'model-json', 'read-skill-file') for c in cs for t in c['tools'])]
    all_draw = [c for s in drawing for c in by_seg[s]]
    widget_out = sum(c['out'] for c in all_draw if any(classify(t) == 'show_widget' for t in c['tools']))
    widget_chars = sum(len((t.get('input') or {}).get('widget_code') or '') for c in all_draw for t in c['tools'] if classify(t) == 'show_widget')
    json_out = sum(c['out'] for c in all_draw if any(classify(t) == 'model-json' for t in c['tools']))
    print(f"\n#{i} {e['date']}: отрезков с отрисовкой {len(drawing)} из {len(segs)}; show_widget: выход {widget_out/1000:.1f}K ток., {widget_chars/1000:.1f}K симв. кода; запись модели JSON: выход {json_out/1000:.1f}K")
    print(f"   ИТОГО {fmt(totals(all_draw))}")
    for s in sorted(drawing):
        cs = by_seg[s]
        kinds = collections.Counter(classify(t) for c in cs for t in c['tools'] if classify(t))
        prompt = segs[s] if s < len(segs) else '(до первого сообщения)'
        print(f"   · {cs[0]['ts'][5:16]} «{prompt[:40]}» {fmt(totals(cs))} | {dict(kinds)}")

print('\n=== Реальный вес в токенах (прирост контекста после загрузки/чтения, одиночный вызов) ===')
for k, v in sorted(growth.items(), key=lambda x: -statistics.median(x[1])):
    print(f'  {k:42} n={len(v):2d} медиана {int(statistics.median(v)):6d} ток. (мин {min(v)}, макс {max(v)})')
