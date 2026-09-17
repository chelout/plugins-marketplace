#!/usr/bin/env python3
"""Measurements of drawing-diagrams usage from local Claude Code transcripts (~/.claude/projects).

  transcripts.py tokens SESSION.jsonl…   metrics per headless run: the session and its agents
  transcripts.py agents [--out DIR]      model and effort of every dispatched agent
  transcripts.py episodes [--out DIR]    drawing episodes: inline or agent, the render loop
  transcripts.py segments DIR            token usage of drawing episodes, from episodes --out DIR
"""
import argparse
import collections
import glob
import json
import os
import re
import statistics
import sys

HOME = os.path.expanduser('~')
PROJECTS = os.path.join(HOME, '.claude', 'projects')
SKILLS = ('drawing-diagrams', 'drawing-db-schemas')
RENDER_RE = re.compile(r'(?:python3?\s[^\n;|&]*|exec\(open\([^)]*)'
                       r'(?:drawing-(?:diagrams|db-schemas)|\$\{CLAUDE_SKILL_DIR\})/render\.py')
RENDER_PATH = re.compile(r'drawing-(?:diagrams|db-schemas)/render\.py')
SKILLFILE = re.compile(r'skills/drawing-(?:diagrams|db-schemas)/')
AGENT_ID_RE = re.compile(r'agentId: (a[0-9a-f]{8,})')
WF_RE = re.compile(r'wf_[0-9a-f]{8}-[0-9a-f]{3}')
SCRIPT_MODEL_RE = re.compile(r"model[\\\"']*\s*:\s*[\\\"']+([\w.-]+)")
SCRIPT_EFFORT_RE = re.compile(r"effort[\\\"']*\s*:\s*[\\\"']+(\w+)")
DISPATCH_TOOLS = {'Agent', 'Task'}
BUILTIN = {'general-purpose', 'Explore', 'Plan', 'claude-code-guide', 'statusline-setup', 'claude', 'fork'}
FAMILIES = ('fable', 'opus', 'sonnet', 'haiku')
SUBAGENTS = f'{os.sep}subagents{os.sep}'


def records(path, prefilter=None):
    with open(path, errors='ignore') as fh:
        for line in fh:
            if prefilter and not any(p in line for p in prefilter):
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def blocks(rec):
    content = (rec.get('message') or {}).get('content')
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def text_of(block):
    c = block.get('content')
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return '\n'.join(b.get('text', '') for b in c if isinstance(b, dict))
    return ''


def family(model):
    for f in FAMILIES:
        if model and f in model:
            return f
    return model or 'n/a'


def short_project(path):
    rel = os.path.relpath(path, PROJECTS).split(os.sep)[0]
    if 'scratch-workspaces' in rel:
        return 'scratch'
    enc = '-' + HOME.strip(os.sep).replace(os.sep, '-')
    return rel.replace(enc + '-', '').replace(enc, '~')


def dominant(counter):
    return counter.most_common(1)[0][0] if counter else 'n/a'


def fmt_counter(counter):
    return ', '.join(f'{k}×{v}' for k, v in counter.most_common()) or '—'


# ---------- agent definitions ----------

def frontmatter(path):
    try:
        text = open(path, errors='ignore').read()
    except OSError:
        return {}
    if not text.startswith('---'):
        return {}
    end = text.find('\n---', 3)
    fm = {}
    for line in text[3:end].splitlines():
        m = re.match(r'^([A-Za-z_-]+):\s*(.*)$', line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"\'')
    return fm


def agent_definitions(cwds):
    defs = collections.defaultdict(set)
    candidates = [(p, None) for p in glob.glob(os.path.join(HOME, '.claude', 'agents', '*.md'))]
    for cwd in cwds:
        candidates += [(p, None) for p in glob.glob(os.path.join(cwd, '.claude', 'agents', '*.md'))]
    # cache/<marketplace>/<plugin>/<version>/agents/<file>.md
    for p in glob.glob(os.path.join(HOME, '.claude', 'plugins', 'cache', '*', '*', '*', 'agents', '*.md')):
        candidates.append((p, p.split(os.sep)[-4]))
    for p, plugin in candidates:
        fm = frontmatter(p)
        name = fm.get('name') or os.path.splitext(os.path.basename(p))[0]
        key = f'{plugin}:{name}' if plugin else name
        defs[key].add((fm.get('model', '—'), fm.get('effort', '—')))
    return defs


def subagent_env_model():
    if os.environ.get('CLAUDE_CODE_SUBAGENT_MODEL'):
        return os.environ['CLAUDE_CODE_SUBAGENT_MODEL']
    try:
        settings = json.load(open(os.path.join(HOME, '.claude', 'settings.json')))
    except (OSError, ValueError):
        return None
    return (settings.get('env') or {}).get('CLAUDE_CODE_SUBAGENT_MODEL')


# ---------- part 1: dispatches and subagents ----------

def scan_dispatches(files):
    index, by_agent = {}, {}
    for path in files:
        for rec in records(path, ('"name":"Agent"', '"name":"Task"', 'agentId: ')):
            for b in blocks(rec):
                if rec.get('type') == 'assistant' and b.get('type') == 'tool_use' and b.get('name') in DISPATCH_TOOLS:
                    inp = b.get('input') or {}
                    index[b.get('id')] = {
                        'file': path,
                        'parent_model': (rec.get('message') or {}).get('model'),
                        'parent_effort': rec.get('effort'),
                        'param_model': inp.get('model'),
                        'subagent_type': inp.get('subagent_type') or 'general-purpose',
                        'background': inp.get('run_in_background'),
                        'description': inp.get('description', ''),
                        'prompt': inp.get('prompt', ''),
                        'cwd': rec.get('cwd'),
                        'date': (rec.get('timestamp') or '')[:10],
                        'version': rec.get('version'),
                    }
                elif rec.get('type') == 'user' and b.get('type') == 'tool_result':
                    m = AGENT_ID_RE.search(text_of(b))
                    if m:
                        by_agent.setdefault(m.group(1), b.get('tool_use_id'))
    return index, by_agent


def own_usage(path):
    """Models and efforts of an agent's own replies, the model it started on, switches and refusals."""
    models, efforts = collections.Counter(), collections.Counter()
    first, last, switches, refusals = None, None, [], 0
    for rec in records(path, ('"type":"assistant"',)):
        if rec.get('type') != 'assistant':
            continue
        msg = rec.get('message') or {}
        model = msg.get('model')
        if not model or model == '<synthetic>':
            continue
        if msg.get('stop_reason') == 'refusal' or 'Usage Policy' in json.dumps(msg.get('stop_details') or ''):
            refusals += 1
        first = first or model
        if last and model != last:
            switches.append(f'{last}→{model}')
        last = model
        models[model] += 1
        efforts[rec.get('effort') or 'n/a'] += 1
    return {'models': models, 'efforts': efforts, 'first': first, 'switches': switches, 'refusals': refusals}


def link_subagent(path, index, by_agent):
    agent_id = os.path.basename(path)[len('agent-'):-len('.jsonl')]
    meta = {}
    meta_path = path[:-len('.jsonl')] + '.meta.json'
    if os.path.exists(meta_path):
        try:
            meta = json.load(open(meta_path))
        except ValueError:
            pass
    tool_use_id = meta.get('toolUseId') or by_agent.get(agent_id)
    return meta, index.get(tool_use_id)


def expected_model(d, defs, env_model):
    st = d['subagent_type']
    if st == 'fork':
        return 'parent', 'fork: parameter ignored'
    if d['param_model']:
        return d['param_model'], 'Agent(model=…)'
    vals = defs.get(st)
    if vals:
        models = {m for m, _ in vals}
        if len(models) > 1:
            return 'ambiguous', 'definition (versions differ)'
        m = next(iter(models))
        if m not in ('—', 'inherit'):
            return m, 'definition model'
        return 'parent', 'definition inherit' if m == 'inherit' else 'definition without model'
    if env_model:
        return env_model, 'CLAUDE_CODE_SUBAGENT_MODEL'
    return 'parent', f'built-in {st}' if st in BUILTIN else 'definition not found'


def expected_effort(d, defs):
    vals = defs.get(d['subagent_type'])
    if vals:
        efforts = {e for _, e in vals}
        if len(efforts) == 1 and next(iter(efforts)) != '—':
            return next(iter(efforts)), 'definition effort'
    return d['parent_effort'] or 'n/a', 'session (parent)'


def workflow_agents(files):
    calls, run_to_call = {}, {}
    for path in files:
        if SUBAGENTS in path:
            continue
        for rec in records(path, ('"name":"Workflow"', 'wf_')):
            for b in blocks(rec):
                if b.get('type') == 'tool_use' and b.get('name') == 'Workflow':
                    script = json.dumps(b.get('input'), ensure_ascii=False)
                    calls[b.get('id')] = {
                        'parent_model': (rec.get('message') or {}).get('model'),
                        'parent_effort': rec.get('effort'),
                        'script_models': sorted(set(SCRIPT_MODEL_RE.findall(script))),
                        'script_efforts': sorted(set(SCRIPT_EFFORT_RE.findall(script))),
                        'date': (rec.get('timestamp') or '')[:10],
                    }
                elif b.get('type') == 'tool_result' and b.get('tool_use_id') in calls:
                    for run in set(WF_RE.findall(text_of(b))):
                        run_to_call.setdefault(run, b.get('tool_use_id'))
    rows = []
    for path in files:
        m = re.search(r'/subagents/workflows/(wf_[^/]+)/agent-[^/]+\.jsonl$', path)
        if not m:
            continue
        usage = own_usage(path)
        if not usage['models']:
            continue
        run = (WF_RE.match(m.group(1)) or m).group(0 if WF_RE.match(m.group(1)) else 1)
        rows.append({'path': path, 'run': run, 'call': calls.get(run_to_call.get(run)), **usage})
    return rows


def part1(files):
    subagent_files = [f for f in files if SUBAGENTS in f]
    index, by_agent = scan_dispatches(files)
    env_model = subagent_env_model()
    linked, unlinked = [], collections.Counter()
    for path in subagent_files:
        meta, d = link_subagent(path, index, by_agent)
        usage = own_usage(path)
        if not usage['models']:
            unlinked['no assistant records'] += 1
            continue
        if not d:
            unlinked[meta.get('agentType') or 'unknown'] += 1
            continue
        linked.append({'path': path, 'dispatch': d, **usage})

    cwds = {r['dispatch']['cwd'] for r in linked if r['dispatch']['cwd']}
    defs = agent_definitions(cwds)

    print('=' * 100)
    print('ЧАСТЬ 1. Все агенты: как получены модель и effort')
    print('=' * 100)
    print(f'транскриптов агентов: {len(subagent_files)}; связаны с вызовом Agent: {len(linked)}; '
          f'не связаны: {sum(unlinked.values())} ({fmt_counter(unlinked)})')
    print(f'CLAUDE_CODE_SUBAGENT_MODEL: {env_model or "не задана"}')
    dates = sorted(r['dispatch']['date'] for r in linked if r['dispatch']['date'])
    if dates:
        print(f'период вызовов Agent: {dates[0]} → {dates[-1]}')

    by_rule = collections.defaultdict(collections.Counter)
    cross = collections.Counter()
    mismatches, switched = [], []
    effort_rows = collections.defaultdict(collections.Counter)
    effort_mism = []
    for r in linked:
        d = r['dispatch']
        exp, rule = expected_model(d, defs, env_model)
        exp_family = family(d['parent_model']) if exp == 'parent' else family(exp)
        ok = family(r['first']) == exp_family
        by_rule[rule]['match' if ok else 'mismatch'] += 1
        r.update(expected=exp, rule=rule, model_ok=ok)
        if not ok:
            mismatches.append(r)
        if r['switches']:
            switched.append(r)
        cross[(family(d['parent_model']), d['param_model'] or '—',
               '*' if d['param_model'] else d['subagent_type'], family(r['first']))] += 1

        exp_e, rule_e = expected_effort(d, defs)
        actual_e = dominant(r['efforts'])
        effort_rows[(rule_e, d['parent_effort'] or 'n/a', family(r['first']))][actual_e] += 1
        r.update(expected_effort=exp_e, effort_rule=rule_e, actual_effort=actual_e)
        if exp_e != 'n/a' and actual_e != 'n/a' and exp_e != actual_e:
            effort_mism.append(r)

    print('\nМодель: правило приоритета → совпала ли стартовая модель агента с ожидаемой (по семейству)')
    print(f'  {"правило":34} {"n":>4} {"совпало":>8} {"нет":>5}')
    for rule, c in sorted(by_rule.items(), key=lambda x: -sum(x[1].values())):
        print(f'  {rule:34} {sum(c.values()):4d} {c["match"]:8d} {c["mismatch"]:5d}')

    print('\nРодитель → Agent(model) → тип (* = любой, параметр решает) → стартовая модель агента')
    for k, v in sorted(cross.items(), key=lambda x: -x[1]):
        print(f'  {v:4d}  родитель={k[0]:7} model={k[1]:7} тип={k[2][:30]:30} → {k[3]}')

    if mismatches:
        print('\nРасхождения стартовой модели с ожиданием')
        for r in mismatches[:20]:
            d = r['dispatch']
            print(f'  {d["date"]} v{d["version"]} {d["subagent_type"][:24]:24} правило={r["rule"]}, '
                  f'родитель={d["parent_model"]}, агент={fmt_counter(r["models"])}')
    if switched:
        print('\nСмена модели по ходу работы агента')
        for r in switched:
            d = r['dispatch']
            print(f'  {d["date"]} {d["subagent_type"][:24]:24} {", ".join(r["switches"])}; '
                  f'отказов по Usage Policy перед сменой: {r["refusals"]}')

    print('\nEffort: откуда должен прийти → что было у агента (преобладающее значение в его ответах)')
    print(f'  {"источник":18} {"effort родителя":16} {"модель агента":14} {"n":>4}  effort агента')
    for key, c in sorted(effort_rows.items(), key=lambda x: -sum(x[1].values())):
        print(f'  {key[0]:18} {key[1]:16} {key[2]:14} {sum(c.values()):4d}  {fmt_counter(c)}')
    print(f'  расхождений effort (ожидали ≠ фактически, оба известны): {len(effort_mism)}')
    for r in effort_mism[:10]:
        d = r['dispatch']
        print(f'    {d["date"]} {d["subagent_type"][:30]:30} ожидали={r["expected_effort"]} ({r["effort_rule"]}), '
              f'агент={fmt_counter(r["efforts"])}')

    used = {r['dispatch']['subagent_type'] for r in linked}
    print('\nОпределения агентов на диске с model/effort, которые реально вызывались:')
    for k in sorted(defs):
        if k in used and any(m != '—' or e != '—' for m, e in defs[k]):
            print(f'  {k}: {sorted(defs[k])}')

    wf = workflow_agents(files)
    print(f'\nАгенты Workflow: {len(wf)}; связаны с вызовом Workflow: {sum(1 for r in wf if r["call"])}')
    tab = collections.Counter()
    for r in wf:
        c = r['call'] or {}
        tab[(c.get('date', '?'), r['run'][:11], family(c.get('parent_model')), c.get('parent_effort') or 'n/a',
             ','.join(c.get('script_models', [])) or '—', ','.join(c.get('script_efforts', [])) or '—',
             family(r['first']), dominant(r['efforts']), 'смена' if r['switches'] else '')] += 1
    print(f'  {"дата":10} {"запуск":11} {"родитель":8} {"p.effort":8} {"model в скрипте":15} '
          f'{"effort в скрипте":16} {"агент":7} {"effort":7} {"":6} n')
    for k, v in sorted(tab.items()):
        print(f'  {k[0]:10} {k[1]:11} {k[2]:8} {k[3]:8} {k[4]:15} {k[5]:16} {k[6]:7} {k[7]:7} {k[8]:6} {v}')
    return linked, wf, index, by_agent


# ---------- part 2: drawing episodes ----------

def parse_render(cmd, result):
    is_err, text = result if result else (None, '')
    exit_code = re.search(r'Exit code (\d+)', text)
    errors = len(re.findall(r'(?m)^\s*ошибка', text))
    return {
        'invocations': cmd.count('render.py'),
        'check': '--check' in cmd,
        'draft': '--draft' in cmd,
        'harness': '--harness' in cmd,
        'mode': (re.search(r'--mode[ =](\w+)', cmd) or [None, None])[1],
        'format': (re.search(r'--format[ =](\w+)', cmd) or [None, None])[1],
        # a pipe (| head, 2>&1 | tail) hides the exit status, so renderer errors count as a failure too
        'failed': bool(is_err) or bool(exit_code and exit_code.group(1) != '0') or errors > 0,
        'errors': errors,
        'warnings': len(re.findall(r'(?m)^\s*предупреждение', text)),
        'has_result': result is not None,
    }


def usage_numbers(u):
    """Input, cache write, cache read, output and thinking tokens of one usage object. Iterations
    are summed when present: some records carry zeros at the top level."""
    its = u.get('iterations') or [u]
    s = lambda k: sum((i.get(k) or 0) for i in its)
    cw = s('cache_creation_input_tokens')
    if not cw and isinstance(u.get('cache_creation'), dict):
        cw = sum(v or 0 for v in u['cache_creation'].values())
    return {'in': s('input_tokens'), 'cw': cw, 'cr': s('cache_read_input_tokens'), 'out': s('output_tokens'),
            'think': (u.get('output_tokens_details') or {}).get('thinking_tokens') or 0}


def api_calls(path):
    """One entry per model response. A message is written as several records; the last one
    carries its final usage."""
    last, order = {}, []
    for rec in records(path, ('"type":"assistant"',)):
        msg = rec.get('message') or {}
        mid = msg.get('id')
        if rec.get('type') != 'assistant' or not mid or msg.get('model') in (None, '<synthetic>'):
            continue
        if mid not in last:
            order.append(mid)
        last[mid] = rec
    calls = []
    for mid in order:
        rec = last[mid]
        n = usage_numbers(rec['message'].get('usage') or {})
        n.update(model=rec['message'].get('model'), effort=rec.get('effort') or 'n/a',
                 ctx=n['in'] + n['cw'] + n['cr'])
        calls.append(n)
    return calls


def render_commands(path):
    """render.py commands of one transcript and how each ended."""
    uses, results, seen = [], {}, set()
    for rec in records(path):
        for b in blocks(rec):
            if (b.get('type') == 'tool_use' and b.get('name') == 'Bash' and b.get('id') not in seen
                    and RENDER_RE.search((b.get('input') or {}).get('command') or '')):
                seen.add(b.get('id'))
                uses.append(b)
            elif b.get('type') == 'tool_result':
                results[b.get('tool_use_id')] = (bool(b.get('is_error')), text_of(b))
    return [parse_render(b['input']['command'], results.get(b.get('id'))) for b in uses]


def run_files(session_path):
    if not session_path.endswith('.jsonl'):
        raise ValueError(f'session path does not end with .jsonl: {session_path}')
    base = session_path[:-len('.jsonl')]
    return [session_path] + sorted(glob.glob(os.path.join(base, 'subagents', '**', '*.jsonl'), recursive=True))


def run_metrics(session_path):
    """Metrics of one headless run: the session and every agent it dispatched.

    renders/renders_failed count Bash calls that invoke render.py, not renderer invocations: a
    compound command can run render.py several times, and failures are counted per Bash call —
    a call that runs the renderer several times and fails once counts once. render_invocations
    sums parse_render(...)['invocations'] across all render calls, so a single Bash call running
    render.py twice counts as two invocations there.
    """
    files = run_files(session_path)
    calls = [c for f in files for c in api_calls(f)]
    renders = [r for f in files for r in render_commands(f)]
    total = lambda k: sum(c[k] for c in calls)
    return {'calls': len(calls), 'agents': len(files) - 1,
            'in': total('in'), 'cw': total('cw'), 'cr': total('cr'), 'out': total('out'), 'think': total('think'),
            'peak_ctx': max((c['ctx'] for c in calls), default=0),
            'models': collections.Counter(c['model'] for c in calls),
            'efforts': collections.Counter(c['effort'] for c in calls),
            'renders': len(renders), 'renders_failed': sum(r['failed'] for r in renders),
            'render_invocations': sum(r['invocations'] for r in renders)}


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
    if nm == 'Bash' and RENDER_PATH.search(inp.get('command') or ''): return 'render'
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


def record_growth(calls, growth):
    for i, c in enumerate(calls[:-1]):
        kinds = [classify(t) for t in c['tools']]
        if len(c['tools']) != 1 or kinds[0] not in ('skill-load', 'read-skill-file'): continue
        g = calls[i + 1]['ctx'] - c['ctx'] - c['out']
        if g > 0:
            inp = c['tools'][0].get('input') or {}
            target = 'SKILL.md body' if kinds[0] == 'skill-load' else re.sub(r'.*skills/drawing-[\w-]+/', '', inp.get('file_path') or inp.get('command') or '')[:40]
            growth[target].append(g)


def segments(out_dir):
    """Token usage of drawing episodes: agents whole, inline sessions per segment with drawing work."""
    eps = json.load(open(os.path.join(out_dir, 'drawing_episodes.json')))
    agents_path = os.path.join(out_dir, 'agents.json')
    agents = json.load(open(agents_path)) if os.path.exists(agents_path) else []
    growth = collections.defaultdict(list)

    print('=== АГЕНТЫ (весь транскрипт = задача рисования) ===')
    labels = {e['path']: f"#{i} {e['dispatch']['description'][:42]}"
              for i, e in enumerate(eps, 1) if e['kind'] == 'агент' and e.get('dispatch')}
    clean = next((a for a in agents if a['dispatch']['description'].startswith('Clean baseline')), None)
    if clean:
        labels[clean['path']] = 'Clean baseline: schema without skill'
    for path, label in sorted(labels.items(), key=lambda x: x[1]):
        calls, _ = load_calls(path)
        record_growth(calls, growth)
        print(f'{label:46} {fmt(totals(calls))}')

    print('\n=== СЕССИИ: только отрезки между сообщениями пользователя, где была отрисовка ===')
    for i, e in enumerate(eps, 1):
        if e['kind'] != 'сессия':
            continue
        calls, segs = load_calls(e['path'])
        record_growth(calls, growth)
        by_seg = collections.defaultdict(list)
        for c in calls:
            by_seg[c['seg']].append(c)
        drawing = [s for s, cs in by_seg.items()
                   if any(classify(t) in ('skill-load', 'render', 'model-json', 'read-skill-file') for c in cs for t in c['tools'])]
        all_draw = [c for s in drawing for c in by_seg[s]]
        widget_out = sum(c['out'] for c in all_draw if any(classify(t) == 'show_widget' for t in c['tools']))
        widget_chars = sum(len((t.get('input') or {}).get('widget_code') or '')
                           for c in all_draw for t in c['tools'] if classify(t) == 'show_widget')
        print(f"\n#{i} {e['date']}: отрезков с отрисовкой {len(drawing)} из {len(segs)}; "
              f"show_widget: выход {widget_out/1000:.1f}K ток., {widget_chars/1000:.1f}K симв. кода")
        print(f"   ИТОГО {fmt(totals(all_draw))}")
        for s in sorted(drawing):
            cs = by_seg[s]
            prompt = segs[s] if s < len(segs) else '(до первого сообщения)'
            print(f"   · {cs[0]['ts'][5:16]} «{prompt[:40]}» {fmt(totals(cs))}")

    print('\n=== Прирост контекста после загрузки или чтения файлов скила ===')
    for k, v in sorted(growth.items(), key=lambda x: -statistics.median(x[1])):
        print(f'  {k:42} n={len(v):2d} медиана {int(statistics.median(v)):6d} ток.')


def episode(path, index, by_agent):
    events, results = [], {}
    for rec in records(path):
        t = rec.get('type')
        if t == 'user':
            content = (rec.get('message') or {}).get('content')
            texts = [content] if isinstance(content, str) else [b.get('text', '') for b in blocks(rec)
                                                                 if b.get('type') == 'text']
            for tx in texts:
                for s in SKILLS:
                    if f'<command-name>/{s}</command-name>' in tx:
                        events.append(('slash', s, rec, None))
            for b in blocks(rec):
                if b.get('type') == 'tool_result':
                    results[b.get('tool_use_id')] = (bool(b.get('is_error')), text_of(b))
        elif t == 'assistant':
            for b in blocks(rec):
                if b.get('type') != 'tool_use':
                    continue
                name, inp = b.get('name', ''), b.get('input') or {}
                if name == 'Skill' and inp.get('skill') in SKILLS:
                    events.append(('skill', inp['skill'], rec, b.get('id')))
                elif name == 'Bash' and RENDER_RE.search(inp.get('command') or ''):
                    events.append(('render', inp['command'], rec, b.get('id')))
                elif name.endswith('show_widget') or (name == 'Artifact' and inp.get('action') in (None, 'publish')):
                    events.append(('embed', name, rec, b.get('id')))

    work = [e for e in events if e[0] in ('skill', 'slash', 'render')]
    if not work:
        return None
    first_ts = min(e[2].get('timestamp') or '' for e in work)
    renders = [parse_render(e[1], results.get(e[3])) for e in events if e[0] == 'render']
    embeds = collections.Counter(e[1].split('__')[-1] for e in events
                                 if e[0] == 'embed' and (e[2].get('timestamp') or '') >= first_ts)
    models = collections.Counter((e[2].get('message') or {}).get('model') for e in work if e[0] != 'slash')
    efforts = collections.Counter(e[2].get('effort') or 'n/a' for e in work if e[0] != 'slash')
    skills = collections.Counter(e[1] for e in work if e[0] in ('skill', 'slash'))
    n_skill = sum(e[0] == 'skill' for e in work)
    n_slash = sum(e[0] == 'slash' for e in work)

    is_agent = SUBAGENTS in path
    dispatch = link_subagent(path, index, by_agent)[1] if is_agent else None
    if not is_agent:
        trigger = ('внутри: /команда' if n_slash else
                   'внутри: модель вызвала Skill' if n_skill else
                   'внутри: render.py без загрузки скила')
    else:
        named = bool(dispatch) and any(s in dispatch['prompt'] for s in SKILLS)
        trigger = ('агент: скил назван в брифе' if named else 'агент: скил не назван в брифе') + \
                  (', Skill вызван' if n_skill else ', Skill не вызван')
    return {
        'path': path, 'project': short_project(path), 'kind': 'агент' if is_agent else 'сессия',
        'date': first_ts[:10], 'trigger': trigger, 'skills': skills, 'n_skill': n_skill, 'n_slash': n_slash,
        'models': models, 'efforts': efforts, 'renders': renders, 'embeds': embeds, 'dispatch': dispatch,
        'versions': collections.Counter(e[2].get('version') for e in work),
    }


def part2(files, index, by_agent):
    episodes, mention_only = [], 0
    for path in files:
        try:
            raw = open(path, errors='ignore').read()
        except OSError:
            continue
        if not any(s in raw for s in SKILLS):
            continue
        ep = episode(path, index, by_agent)
        if ep:
            episodes.append(ep)
        else:
            mention_only += 1
    episodes.sort(key=lambda e: (e['date'], e['kind']))

    print('\n' + '=' * 100)
    print('ЧАСТЬ 2. Эпизоды drawing-diagrams / drawing-db-schemas')
    print('=' * 100)
    print(f'эпизодов: {len(episodes)}; файлов только с упоминанием (без Skill, /команды и render.py): {mention_only}\n')
    for i, e in enumerate(episodes, 1):
        rs = e['renders']
        d = e['dispatch']
        print(f'#{i:<2} {e["date"]} {e["project"][:30]:30} {e["kind"]:6} {e["trigger"]}')
        print(f'     скил: {fmt_counter(e["skills"]) if e["skills"] else "—"}; модель: {fmt_counter(e["models"])}; '
              f'effort: {fmt_counter(e["efforts"])}; версии: {fmt_counter(e["versions"])}')
        if d:
            print(f'     вызов: {d["subagent_type"]}, model={d["param_model"] or "—"}, фон={d["background"]}, '
                  f'родитель {d["parent_model"]}/{d["parent_effort"] or "n/a"}; «{d["description"][:60]}»')
        if rs:
            print(f'     render.py: команд {len(rs)} (запусков {sum(r["invocations"] for r in rs)}), '
                  f'--check {sum(r["check"] for r in rs)}, с ошибкой {sum(r["failed"] for r in rs)}, '
                  f'строк «ошибка» {sum(r["errors"] for r in rs)}, предупр. {sum(r["warnings"] for r in rs)}, '
                  f'--draft {sum(r["draft"] for r in rs)}, --harness {sum(r["harness"] for r in rs)}, '
                  f'режимы {fmt_counter(collections.Counter(r["mode"] or "widget" for r in rs if not r["check"]))}, '
                  f'форматы {fmt_counter(collections.Counter(r["format"] for r in rs if r["format"]))}')
        print(f'     встраивание: {fmt_counter(e["embeds"])}')

    print('\nСводка')
    for k, v in collections.Counter(e['trigger'] for e in episodes).most_common():
        print(f'  {v:3d}  {k}')
    for kind in ('сессия', 'агент'):
        eps = [e for e in episodes if e['kind'] == kind]
        if not eps:
            continue
        m, ef = collections.Counter(), collections.Counter()
        for e in eps:
            m.update(e['models'])
            ef.update(e['efforts'])
        rs = [r for e in eps for r in e['renders']]
        print(f'\n  {kind}: эпизодов {len(eps)}')
        print(f'    модель в работе: {fmt_counter(m)}')
        print(f'    effort в работе: {fmt_counter(ef)}')
        if rs:
            failed = sum(r['failed'] for r in rs)
            print(f'    render.py-команд: {len(rs)} (медиана на эпизод '
                  f'{sorted(len(e["renders"]) for e in eps)[len(eps) // 2]}), с ошибкой {failed} '
                  f'({100 * failed // len(rs)}%)')
        print(f'    встраивание: {fmt_counter(sum((e["embeds"] for e in eps), collections.Counter()))}')
    return episodes


def dump(out_dir, name, rows):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    with open(path, 'w') as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1, default=str)
    print(f'записано {path}', file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('tokens', help='metrics of headless runs, one session file each')
    p.add_argument('sessions', nargs='+')
    for name in ('agents', 'episodes'):
        p = sub.add_parser(name)
        p.add_argument('--out', help='also write JSON dumps to this directory')
    p = sub.add_parser('segments', help='token usage of drawing episodes, from an episodes --out directory')
    p.add_argument('out')
    args = ap.parse_args(argv)

    if args.cmd == 'tokens':
        for path in args.sessions:
            m = run_metrics(path)
            print(f"{os.path.basename(path)}  calls={m['calls']} agents={m['agents']} out={m['out']} "
                  f"think={m['think']} cw={m['cw']} cr={m['cr']} in={m['in']} peak={m['peak_ctx']} "
                  f"renders={m['renders']}/{m['renders_failed']} invocations={m['render_invocations']} "
                  f"effort={fmt_counter(m['efforts'])} "
                  f"model={fmt_counter(m['models'])}")
        return 0
    if args.cmd == 'segments':
        segments(args.out)
        return 0

    files = sorted(glob.glob(os.path.join(PROJECTS, '**', '*.jsonl'), recursive=True))
    strip = lambda row: row.get('dispatch') and row.update(
        dispatch={k: v for k, v in row['dispatch'].items() if k != 'prompt'})
    if args.cmd == 'agents':
        linked, wf, _, _ = part1(files)
        if args.out:
            for row in linked:
                strip(row)
            dump(args.out, 'agents.json', linked)
            dump(args.out, 'workflow_agents.json', wf)
        return 0
    index, by_agent = scan_dispatches(files)
    episodes = part2(files, index, by_agent)
    if args.out:
        for row in episodes:
            strip(row)
        dump(args.out, 'drawing_episodes.json', episodes)
    return 0


if __name__ == '__main__':
    sys.exit(main())
