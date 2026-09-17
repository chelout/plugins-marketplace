# drawing-diagrams token cost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks 1–5 and 7–8 can be dispatched to subagents; tasks 6 and 9–14 need the controller (browser, owner words, headless Claude runs).

**Goal:** Cut the tokens a diagram costs: CDN-delivered widget assets with an inline fallback, a one-command render loop with character budgets, a reference split by kind, and a measured decision on skill `effort` versus a delegated agent.

**Architecture:** Styles and scripts become fragments under `template/css` and `template/js`; `diagrams/assets.py` assembles them into the full build (committed under `template/dist`, served by jsDelivr at the commit in `template/dist/REF`) or into the subset one widget needs. `render.py` checks every model before rendering, prints only the fragment on success, and gains `--assets` and `--out-dir`. Measurement and the experiment use `tools/transcripts.py` over headless `claude -p` runs.

**Tech Stack:** Python 3 standard library (`unittest`, `argparse`, `urllib`), vanilla JS/CSS, jsDelivr `/gh/`, Claude Code CLI (`claude -p`, `--plugin-dir`, `--settings`, `--session-id`).

**Spec:** `plugins/drawing-diagrams/docs/specs/2026-09-17-token-cost-design.md`

## Global Constraints

- Paths below are relative to the repository root; `SKILL` means `plugins/drawing-diagrams/skills/drawing-diagrams`.
- Standard library only. Tests run with `cd plugins/drawing-diagrams && python3 -m unittest discover -s tests -v`.
- Tools and tests live outside `SKILL`: `plugins/drawing-diagrams/tools/`, `plugins/drawing-diagrams/tests/`.
- Renderer messages stay in Russian; documents in English.
- CDN base, exactly: `https://cdn.jsdelivr.net/gh/chelout/plugins-marketplace@<REF>/plugins/drawing-diagrams/skills/drawing-diagrams/template/dist/`
- `template/dist/REF` holds the full 40-character SHA of the last commit that changed `template/dist/dg.css` or `template/dist/dg.js`.
- No visual change: page mode keeps the full CSS and JS inline.
- `SKILL.md` stays at most 6.7K characters in total.
- A branch that changes `template/dist` is merged with a merge commit, never squash or rebase.
- Experiment material (briefs, runs, reports, variants) stays in `.experiments/` at the repository root, excluded from git: the benchmark briefs name internal repositories and this repository is public.
- Every commit message ends with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Before each commit that touches the plugin: `claude plugin validate plugins/drawing-diagrams` (the only expected warning is the missing `version`).

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `plugins/drawing-diagrams/tests/support.py` | puts `SKILL` and `tools/` on `sys.path` for tests | 1 |
| `plugins/drawing-diagrams/tools/transcripts.py` | transcript measurements: `agents`, `episodes`, `segments`, `tokens` | 1 |
| `plugins/drawing-diagrams/tools/skill_analytics.py`, `skill_tokens.py` | removed (folded into `transcripts.py`) | 1 |
| `SKILL/template/css/*.css` | CSS fragments: `base`, `schema`, `flow`, `lanes`, `routes`, `foot`, `timeline` | 2 |
| `SKILL/template/js/*.js` | JS fragments: `head`, `flow`, `schema`, `draw`, `routes`, `end` | 2 |
| `SKILL/template/core.css`, `core.js` | removed (split into fragments) | 2 |
| `SKILL/diagrams/assets.py` | assembles full and per-widget assets, CDN links, `REF` | 2 |
| `SKILL/diagrams/{flow,schema,timeline}.py` | `render(..., assets_mode=)`; character budgets in fit messages | 2, 4 |
| `SKILL/diagrams/common.py` | `ModelError.fit`, `fit_chars`, `two_line_chars` | 4 |
| `plugins/drawing-diagrams/tools/assets.py` | `build`, `check`, `verify-cdn` | 3 |
| `SKILL/template/dist/dg.css`, `dg.js`, `REF` | published build and its commit | 3, 9 |
| `SKILL/render.py` | `--assets`, `--no-assets` alias, `--out-dir`, map on layout failure | 5 |
| `SKILL/reference/{common,schema,flow,timeline,output}.md` | reference split by kind, with field tables | 7 |
| `SKILL/reference/model.md` | removed | 7 |
| `SKILL/examples/schema-small.json`, `examples/full/kyc-module.json` | small schema sample; the large one moved | 7 |
| `plugins/drawing-diagrams/docs/design.md` | moved from `SKILL/design.md`; §13 decision record | 7, 14 |
| `SKILL/SKILL.md` | new workflow, cost rules | 8 |
| `plugins/drawing-diagrams/tests/test_*.py` | unit tests per task | 1–5 |

---

### Task 1: Measurement tool `tools/transcripts.py`

Spec: §6 "Measurement tool", criterion 12.

**Files:**
- Create: `plugins/drawing-diagrams/tests/support.py`
- Create: `plugins/drawing-diagrams/tests/test_transcripts.py`
- Rename: `plugins/drawing-diagrams/tools/skill_analytics.py` → `plugins/drawing-diagrams/tools/transcripts.py`
- Delete: `plugins/drawing-diagrams/tools/skill_tokens.py` (after its code is moved)

**Interfaces:**
- Produces: `transcripts.usage_numbers(usage: dict) -> dict` with keys `in, cw, cr, out, think`; `transcripts.api_calls(path: str) -> list[dict]` (keys of `usage_numbers` plus `model, effort, ctx`); `transcripts.render_commands(path: str) -> list[dict]` (the dicts of `parse_render`); `transcripts.run_metrics(session_path: str) -> dict` with keys `calls, agents, in, cw, cr, out, think, peak_ctx, models (Counter), efforts (Counter), renders, renders_failed`; `transcripts.main(argv: list[str]) -> int`. CLI: `transcripts.py tokens SESSION.jsonl…`, `transcripts.py agents [--out DIR]`, `transcripts.py episodes [--out DIR]`, `transcripts.py segments DIR`.

- [ ] **Step 1: Write the test support module**

`plugins/drawing-diagrams/tests/support.py`:

```python
"""Puts the skill directory and the tools directory on sys.path for the tests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "drawing-diagrams"
TOOLS = ROOT / "tools"
for path in (str(TOOLS), str(SKILL)):
    if path not in sys.path:
        sys.path.insert(0, path)
```

- [ ] **Step 2: Write the failing tests**

`plugins/drawing-diagrams/tests/test_transcripts.py`:

```python
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import support  # noqa: F401
import transcripts


def assistant(mid, usage, effort="xhigh", model="claude-opus-5", content=None):
    return {"type": "assistant", "effort": effort,
            "message": {"id": mid, "model": model, "usage": usage, "content": content or []}}


def write(path, recs):
    # Claude Code writes compact JSON; the readers prefilter on '"type":"assistant"'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in recs) + "\n")


class RunMetrics(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.session = root / "run.jsonl"
        render = {"type": "tool_use", "id": "t1", "name": "Bash",
                  "input": {"command": "python3 /x/skills/drawing-diagrams/render.py m.json --mode widget"}}
        write(self.session, [
            # one message written as two records; the first carries a partial usage
            assistant("m1", {"input_tokens": 2, "output_tokens": 2, "cache_creation_input_tokens": 100}),
            assistant("m1", {"input_tokens": 2, "output_tokens": 150, "cache_creation_input_tokens": 100,
                             "cache_read_input_tokens": 1000, "output_tokens_details": {"thinking_tokens": 40},
                             "iterations": [{"input_tokens": 2, "output_tokens": 150, "cache_read_input_tokens": 1000,
                                             "cache_creation_input_tokens": 100}]},
                      effort="high", content=[render]),
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True,
                                                      "content": "Exit code 1\nошибка: узел a: заголовок 30 симв., влезает 19"}]}},
            # zeros at the top level, the real numbers only in iterations
            assistant("m2", {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                             "cache_creation_input_tokens": 0, "cache_creation": {"ephemeral_1h_input_tokens": 275},
                             "iterations": [{"input_tokens": 2, "output_tokens": 327, "cache_read_input_tokens": 988169,
                                             "cache_creation_input_tokens": 275}]}),
            assistant("m3", {"input_tokens": 0, "output_tokens": 0}, model="<synthetic>"),
        ])
        write(root / "run" / "subagents" / "agent-a1.jsonl", [
            assistant("s1", {"input_tokens": 3, "output_tokens": 50, "cache_read_input_tokens": 500},
                      effort="medium", model="claude-sonnet-5"),
        ])

    def test_counts_each_message_once_and_sums_iterations(self):
        calls = transcripts.api_calls(str(self.session))
        self.assertEqual([c["out"] for c in calls], [150, 327])
        self.assertEqual(calls[0]["think"], 40)
        self.assertEqual(calls[0]["ctx"], 2 + 100 + 1000)
        self.assertEqual(calls[0]["effort"], "high")
        self.assertEqual((calls[1]["cr"], calls[1]["cw"]), (988169, 275))

    def test_run_metrics_include_subagents_and_render_failures(self):
        m = transcripts.run_metrics(str(self.session))
        self.assertEqual((m["calls"], m["agents"]), (3, 1))
        self.assertEqual(m["out"], 150 + 327 + 50)
        self.assertEqual(m["peak_ctx"], 2 + 275 + 988169)
        self.assertEqual((m["renders"], m["renders_failed"]), (1, 1))
        self.assertEqual(dict(m["efforts"]), {"high": 1, "xhigh": 1, "medium": 1})
        self.assertEqual(dict(m["models"]), {"claude-opus-5": 2, "claude-sonnet-5": 1})

    def test_tokens_command_prints_one_line_per_run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = transcripts.main(["tokens", str(self.session)])
        self.assertEqual(code, 0)
        line = out.getvalue().strip().splitlines()[-1]
        self.assertIn("run.jsonl", line)
        self.assertIn("out=527", line)
        self.assertIn("renders=1/1", line)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd plugins/drawing-diagrams && python3 -m unittest discover -s tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'transcripts'`.

- [ ] **Step 4: Rename the analytics script and match plugin render paths**

```bash
git mv plugins/drawing-diagrams/tools/skill_analytics.py plugins/drawing-diagrams/tools/transcripts.py
```

In `transcripts.py` replace the module docstring (lines 2–10) with:

```python
"""Measurements of drawing-diagrams usage from local Claude Code transcripts (~/.claude/projects).

  transcripts.py tokens SESSION.jsonl…   metrics per headless run: the session and its agents
  transcripts.py agents [--out DIR]      model and effort of every dispatched agent
  transcripts.py episodes [--out DIR]    drawing episodes: inline or agent, the render loop
  transcripts.py segments DIR            token usage of drawing episodes, from episodes --out DIR
"""
```

Replace the `RENDER_RE` line with:

```python
RENDER_RE = re.compile(r'(?:python3?\s[^\n;|&]*|exec\(open\([^)]*)'
                       r'(?:drawing-(?:diagrams|db-schemas)|\$\{CLAUDE_SKILL_DIR\})/render\.py')
RENDER_PATH = re.compile(r'drawing-(?:diagrams|db-schemas)/render\.py')
SKILLFILE = re.compile(r'skills/drawing-(?:diagrams|db-schemas)/')
```

- [ ] **Step 5: Add the per-run functions**

Insert after `parse_render` in `transcripts.py`:

```python
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
    base = session_path[:-len('.jsonl')]
    return [session_path] + sorted(glob.glob(os.path.join(base, 'subagents', '**', '*.jsonl'), recursive=True))


def run_metrics(session_path):
    """Metrics of one headless run: the session and every agent it dispatched."""
    files = run_files(session_path)
    calls = [c for f in files for c in api_calls(f)]
    renders = [r for f in files for r in render_commands(f)]
    total = lambda k: sum(c[k] for c in calls)
    return {'calls': len(calls), 'agents': len(files) - 1,
            'in': total('in'), 'cw': total('cw'), 'cr': total('cr'), 'out': total('out'), 'think': total('think'),
            'peak_ctx': max((c['ctx'] for c in calls), default=0),
            'models': collections.Counter(c['model'] for c in calls),
            'efforts': collections.Counter(c['effort'] for c in calls),
            'renders': len(renders), 'renders_failed': sum(r['failed'] for r in renders)}
```

- [ ] **Step 6: Move the segment accounting from `skill_tokens.py`**

Copy these functions from `plugins/drawing-diagrams/tools/skill_tokens.py` into `transcripts.py` (after `run_metrics`) unchanged, except for the three edits listed: `is_prompt`, `load_calls`, `classify`, `totals`, `fmt`, `record_growth`. Do not copy `usage_numbers` (Step 5 added the same function) or the module-level constants.
- In `classify`: `RENDER.search` → `RENDER_PATH.search`.
- `def record_growth(calls):` → `def record_growth(calls, growth):` (it appends to the dict it is given).
- In `load_calls`: nothing changes; it already calls `usage_numbers`.

Then add:

```python
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
```

Add `import argparse` and `import statistics` to the imports of `transcripts.py`.

- [ ] **Step 7: Replace `main`**

Replace the whole `main` function of `transcripts.py` with:

```python
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
                  f"renders={m['renders']}/{m['renders_failed']} effort={fmt_counter(m['efforts'])} "
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
```

Delete the old `if __name__ == '__main__': main()` block at the end of the file if it remains.

- [ ] **Step 8: Remove the imported token script**

```bash
git rm plugins/drawing-diagrams/tools/skill_tokens.py
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `cd plugins/drawing-diagrams && python3 -m unittest discover -s tests -v`
Expected: 3 tests, OK.

- [ ] **Step 10: Smoke-run on a real transcript**

Run: `python3 plugins/drawing-diagrams/tools/transcripts.py tokens "$(ls -t ~/.claude/projects/*/*.jsonl | head -1)"`
Expected: one line starting with a `.jsonl` file name and containing `calls=`, `out=`, `renders=`.

- [ ] **Step 11: Commit**

```bash
git add plugins/drawing-diagrams/tests plugins/drawing-diagrams/tools
git commit -m "feat(drawing-diagrams): transcripts.py measures runs per session and agent

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: CSS and JS fragments, `diagrams/assets.py`

Spec: §3.1 (what the full build contains), §3.2 (`inline`, `none`, `cdn` blocks), §3.3 (pruning).

**Files:**
- Create: `SKILL/template/css/{base,schema,flow,lanes,routes,foot,timeline}.css` (split of `core.css`)
- Create: `SKILL/template/js/{head,flow,schema,draw,routes,end}.js` (split of `core.js`)
- Delete: `SKILL/template/core.css`, `SKILL/template/core.js`
- Modify: `SKILL/diagrams/assets.py` (whole file)
- Modify: `SKILL/diagrams/flow.py:557-596`, `SKILL/diagrams/schema.py:373-400`, `SKILL/diagrams/timeline.py:97-127` (`render` signature and asset blocks)
- Modify: `SKILL/render.py:95` (call with `assets_mode`)
- Modify: comments naming `core.js` in `SKILL/diagrams/flow.py` and `SKILL/diagrams/common.py`
- Test: `plugins/drawing-diagrams/tests/test_assets.py`

**Interfaces:**
- Consumes: `tests/support.py` (Task 1).
- Produces: `assets.TPL`, `assets.DIST` (`TPL / "dist"`), `assets.CSS_PARTS`, `assets.JS_PARTS`, `assets.css_text(parts=CSS_PARTS, ramps=None) -> str`, `assets.js_text(parts=JS_PARTS) -> str`, `assets.widget_parts(kind, edges, routes, footnotes) -> (list[str], list[str])`, `assets.read_ref() -> str | None`, `assets.cdn_url(ref, name) -> str`, `assets.asset_blocks(assets_mode, mode_name, kind, ramps=None, edges=(), routes=None, footnotes=()) -> (str, str)`; `render(model, mode_name, layout, warnings, assets_mode="inline", draft=False)` in `flow`, `schema`, `timeline`.

- [ ] **Step 1: Write the failing tests**

`plugins/drawing-diagrams/tests/test_assets.py`:

```python
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401
from diagrams import assets

EDGE = [{"a": "a", "b": "b"}]
CDN = "https://cdn.jsdelivr.net/gh/chelout/plugins-marketplace@{}/plugins/drawing-diagrams/skills/drawing-diagrams/template/dist/"


class Fragments(unittest.TestCase):
    def test_full_build_holds_every_fragment_once(self):
        css, js = assets.css_text(), assets.js_text()
        for part in assets.CSS_PARTS:
            self.assertEqual(css.count((assets.TPL / "css" / f"{part}.css").read_text()), 1, part)
        for part in assets.JS_PARTS:
            self.assertEqual(js.count((assets.TPL / "js" / f"{part}.js").read_text()), 1, part)

    def test_widget_parts(self):
        self.assertEqual(assets.widget_parts("timeline", [], None, []), (["base", "timeline"], []))
        self.assertEqual(assets.widget_parts("blocks", [], None, [])[1], [])
        self.assertEqual(assets.widget_parts("schema", [], None, [])[1], ["head", "schema", "draw", "end"])
        self.assertEqual(assets.widget_parts("swimlane", EDGE, {"r": ["a", "b"]}, ["note"]),
                         (["base", "flow", "lanes", "routes", "foot"], ["head", "flow", "draw", "routes", "end"]))

    def test_page_inline_is_the_full_build(self):
        self.assertEqual(assets.asset_blocks("inline", "page", "flow"),
                         ("<style>" + assets.css_text() + "</style>", "<script>" + assets.js_text() + "</script>"))

    def test_widget_inline_keeps_only_what_the_diagram_uses(self):
        before, after = assets.asset_blocks("inline", "widget", "flow", {"teal"}, EDGE)
        self.assertIn(".r-teal", before)
        self.assertNotIn(".r-purple", before)
        self.assertNotIn(".dg-tl{", before)
        self.assertIn("drawKind.flow", after)
        self.assertNotIn("drawKind.schema", after)

    def test_timeline_widget_has_no_script(self):
        before, after = assets.asset_blocks("inline", "widget", "timeline")
        self.assertIn(".dg-tl{", before)
        self.assertEqual(after, "")

    def test_none_is_empty(self):
        self.assertEqual(assets.asset_blocks("none", "widget", "flow", {"teal"}, EDGE), ("", ""))

    def test_cdn_links_pin_ref(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(assets, "DIST", Path(tmp)):
            Path(tmp, "REF").write_text("a" * 40 + "\n")
            before, after = assets.asset_blocks("cdn", "widget", "flow", {"teal"}, EDGE)
        base = CDN.format("a" * 40)
        self.assertEqual(before, f'<link rel="stylesheet" href="{base}dg.css">')
        self.assertEqual(after, f'<script src="{base}dg.js"></script>')

    def test_read_ref_without_file(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(assets, "DIST", Path(tmp)):
            self.assertIsNone(assets.read_ref())

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_every_script_combination_parses(self):
        combos = {tuple(assets.JS_PARTS)}
        for kind in ("schema", "flow", "swimlane", "state", "blocks"):
            for routes in (None, {"r": ["a", "b"]}):
                parts = assets.widget_parts(kind, EDGE, routes, [])[1]
                if parts:
                    combos.add(tuple(parts))
        with tempfile.TemporaryDirectory() as tmp:
            for i, parts in enumerate(sorted(combos)):
                path = Path(tmp, f"{i}.js")
                path.write_text(assets.js_text(parts))
                subprocess.run(["node", "--check", str(path)], check=True)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd plugins/drawing-diagrams && python3 -m unittest discover -s tests -p test_assets.py -v`
Expected: FAIL — `AttributeError: module 'diagrams.assets' has no attribute 'css_text'`.

- [ ] **Step 3: Split `core.css` into fragments**

Run from the repository root:

```bash
python3 - <<'EOF'
from pathlib import Path
tpl = Path("plugins/drawing-diagrams/skills/drawing-diagrams/template")
lines = (tpl / "core.css").read_text().splitlines(keepends=True)
parts = {
    "base": [1, 2, 5, 6, 8, *range(25, 38), 42, 43],
    "schema": [3, 4, 7, *range(9, 25)],
    "flow": [*range(38, 42), *range(44, 50), *range(56, 61), *range(63, 68)],
    "lanes": [50, 51],
    "routes": [52, 53, 54, 55],
    "foot": [61, 62],
    "timeline": list(range(68, 81)),
}
assert len(lines) == 80
assert sorted(n for ns in parts.values() for n in ns) == list(range(1, 81))
(tpl / "css").mkdir(exist_ok=True)
for name, ns in parts.items():
    (tpl / "css" / f"{name}.css").write_text("".join(lines[n - 1] for n in ns))
joined = sorted(l for name in parts for l in (tpl / "css" / f"{name}.css").read_text().splitlines())
print(joined == sorted((tpl / "core.css").read_text().splitlines()))
EOF
```

Expected output: `True`. The order base → schema → flow → lanes → routes → foot → timeline keeps every pair of competing rules in their original relative order (`.dg-c` before `.k-note`, `.k-terminal`, `.k-state`; `.dg-h` before `.dg-node .dg-h` and `.dg-h small`).

- [ ] **Step 4: Split `core.js` into fragments**

Run from the repository root:

```bash
python3 - <<'EOF'
from pathlib import Path
tpl = Path("plugins/drawing-diagrams/skills/drawing-diagrams/template")
L = (tpl / "core.js").read_text().splitlines(keepends=True)
assert len(L) == 92

def lines(a, b):
    return "".join(L[a - 1:b])

def swap(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)

head = swap(lines(1, 15), "var active=null;", "var active=null,drawKind={},ready=[];") + lines(19, 33)
flow = swap(lines(34, 58), "function drawFlow(rr){", "drawKind.flow=function(rr){")
flow = swap(flow, "svg.appendChild(g)})}\n", "svg.appendChild(g)})};\n")
schema = lines(16, 18) + " drawKind.schema=function(rr){var T=tracks();\n" + lines(62, 73) + lines(74, 77) + " ready.push(syncAll);\n"
schema = swap(schema, "mark(g,B,e.b[2],e.be,!!e.d);svg.appendChild(g)})}\n", "mark(g,B,e.b[2],e.be,!!e.d);svg.appendChild(g)})};\n")
draw = (" function draw(){var rr=grid.getBoundingClientRect();svg.setAttribute('viewBox','0 0 '+rr.width+' '+rr.height);"
        "while(svg.firstChild)svg.removeChild(svg.firstChild);\n"
        "  var k=sec.getAttribute('data-kind')==='schema'?'schema':'flow';if(drawKind[k])drawKind[k](rr)}\n") + lines(78, 80)
routes = lines(81, 87)
end = swap(lines(88, 92), " syncAll();draw();", " ready.forEach(function(f){f()});draw();")
(tpl / "js").mkdir(exist_ok=True)
for name, text in (("head", head), ("flow", flow), ("schema", schema), ("draw", draw), ("routes", routes), ("end", end)):
    (tpl / "js" / f"{name}.js").write_text(text)
print("ok")
EOF
```

Expected output: `ok`. What changed against `core.js`: `drawFlow` became `drawKind.flow`; the schema branch of `draw` became `drawKind.schema`; `draw` dispatches on `data-kind`; `syncAll` runs through `ready`. Function declarations inside `init` are hoisted, so the schema fragment's handlers may call `draw`, which the `draw` fragment declares later.

- [ ] **Step 5: Remove the monolithic files**

```bash
git rm -q plugins/drawing-diagrams/skills/drawing-diagrams/template/core.css plugins/drawing-diagrams/skills/drawing-diagrams/template/core.js
```

- [ ] **Step 6: Rewrite `diagrams/assets.py`**

Replace the whole file with:

```python
"""CSS, JS and page wrappers shared by every kind.

Styles and scripts are fragments under template/css and template/js. A page carries all of them;
a chat widget either links to the published build in template/dist (served by jsDelivr at the
commit named in template/dist/REF) or carries only the fragments its diagram uses."""
import hashlib
import json
from pathlib import Path

from .common import RAMPS, esc

TPL = Path(__file__).resolve().parent.parent / "template"
DIST = TPL / "dist"
CSS_PARTS = ("base", "schema", "flow", "lanes", "routes", "foot", "timeline")
JS_PARTS = ("head", "flow", "schema", "draw", "routes", "end")
FLOW_KINDS = ("flow", "swimlane", "state", "blocks")
CDN = ("https://cdn.jsdelivr.net/gh/chelout/plugins-marketplace@{ref}"
       "/plugins/drawing-diagrams/skills/drawing-diagrams/template/dist/{name}")


def ramp_css(ramps):
    if not ramps:
        return ""
    light, dark = [], []
    for r in sorted(ramps):
        s = RAMPS[r]
        light.append(f".dg .r-{r}{{background:{s[0]};color:{s[5]}}}.dg .r-{r} small{{color:{s[4]}}}"
                     f".dg .sw-{r}{{background:{s[0]};border-color:{s[4]}}}.dg .s-{r}{{border-left-color:{s[3]}}}")
        dark.append(f".dg .r-{r}{{background:{s[5]};color:{s[1]}}}.dg .r-{r} small{{color:{s[2]}}}")
    d = "".join(dark)

    def scoped(prefix):
        return d.replace(".dg ", prefix + " .dg ").replace("}.dg", "}" + prefix + " .dg")

    return ("".join(light) + scoped('[data-mode="dark"]') + scoped(':root[data-theme="dark"]')
            + "@media (prefers-color-scheme:dark){" + scoped(':root:not([data-mode]):not([data-theme="light"])') + "}")


def css_text(parts=CSS_PARTS, ramps=None):
    """Tokens, the named fragments in CSS_PARTS order, then the ramps: all nine when `ramps` is None,
    because a second diagram on a page (rendered with --assets none) may use colours the first did not."""
    body = "".join((TPL / "css" / f"{p}.css").read_text() for p in CSS_PARTS if p in parts)
    return (TPL / "tokens.css").read_text() + body + ramp_css(RAMPS if ramps is None else ramps)


def js_text(parts=JS_PARTS):
    return "".join((TPL / "js" / f"{p}.js").read_text() for p in JS_PARTS if p in parts)


def widget_parts(kind, edges, routes, footnotes):
    """(CSS parts, JS parts) of one diagram in a chat widget. A timeline draws nothing by script and a
    flow-like diagram without edges has nothing to draw; a schema needs its toggles either way."""
    css = ["base"]
    if kind == "schema":
        css.append("schema")
    elif kind == "timeline":
        css.append("timeline")
    else:
        css.append("flow")
        if kind == "swimlane":
            css.append("lanes")
        if routes:
            css.append("routes")
        if footnotes:
            css.append("foot")
    if kind == "timeline" or (kind in FLOW_KINDS and not edges):
        return css, []
    js = ["head", "schema" if kind == "schema" else "flow", "draw"]
    if routes:
        js.append("routes")
    return css, js + ["end"]


def style_block(parts=CSS_PARTS, ramps=None):
    return "<style>" + css_text(parts, ramps) + "</style>"


def script_block(parts=JS_PARTS):
    return "<script>" + js_text(parts) + "</script>" if parts else ""


def read_ref():
    """SHA of the commit whose tree holds template/dist, or None before the first release."""
    try:
        ref = (DIST / "REF").read_text().strip()
    except OSError:
        return None
    return ref or None


def cdn_url(ref, name):
    return CDN.format(ref=ref, name=name)


def asset_blocks(assets_mode, mode_name, kind, ramps=None, edges=(), routes=None, footnotes=()):
    """(before, after): what surrounds a diagram's <section>. `cdn` needs read_ref() to be set;
    render.py falls back to `inline` otherwise."""
    if assets_mode == "none":
        return "", ""
    if assets_mode == "cdn":
        ref = read_ref()
        return (f'<link rel="stylesheet" href="{esc(cdn_url(ref, "dg.css"))}">',
                f'<script src="{esc(cdn_url(ref, "dg.js"))}"></script>')
    if mode_name == "page":
        return style_block(), script_block()
    css, js = widget_parts(kind, edges, routes, footnotes)
    return style_block(css, ramps or ()), script_block(js)


def harness(fragment):
    return (TPL / "harness.html").read_text().replace("{{BODY}}", fragment)


def section_id(model):
    return model.get("id") or hashlib.sha1(json.dumps(model, sort_keys=True).encode()).hexdigest()[:8]


def section_open(model, kind, style_vars, labels_js, summary):
    uid = section_id(model)
    return (f'<section class="dg" data-dg="{esc(uid)}" data-kind="{esc(kind)}" data-labels="{labels_js}" '
            f'style="{style_vars}">\n<h2 class="sr">{esc(summary)}</h2>')


def edges_json(edges):
    return ('<script type="application/json" class="dg-edges">'
            + json.dumps(edges, ensure_ascii=False).replace("</", "<\\/") + "</script>")
```

- [ ] **Step 7: Pass the assets mode through the three renderers**

`SKILL/diagrams/flow.py`: change `def render(model, mode_name, layout, warnings, with_assets=True, draft=False):` to `def render(model, mode_name, layout, warnings, assets_mode="inline", draft=False):`. Replace

```python
    parts = []
    if with_assets:
        parts.append(assets.style_block({g["ramp"] for g in groups.values()}))
```

with

```python
    before, after = assets.asset_blocks(assets_mode, mode_name, kind, {g["ramp"] for g in groups.values()},
                                        layout["edges"], layout["routes"], layout["footnotes"])
    parts = [before] if before else []
```

and replace

```python
    if with_assets:
        parts.append(assets.script_block())
```

with

```python
    if after:
        parts.append(after)
```

`SKILL/diagrams/schema.py`: the same signature change; the first block becomes

```python
    before, after = assets.asset_blocks(assets_mode, mode_name, "schema", {g["ramp"] for g in groups.values()},
                                        layout["edges"])
    parts = [before] if before else []
```

and the last one `if after: parts.append(after)` as in `flow.py`.

`SKILL/diagrams/timeline.py`: the same signature change; the first block becomes

```python
    before, after = assets.asset_blocks(assets_mode, mode_name, "timeline")
    parts = [before] if before else []
```

and the last one `if after: parts.append(after)`.

`SKILL/render.py`: in `out = mod.render(model, args.mode, layout, warnings, with_assets=not args.no_assets, draft=draft_used)` replace `with_assets=not args.no_assets` with `assets_mode="none" if args.no_assets else "inline"`.

- [ ] **Step 8: Point comments at the new script file**

```bash
sed -i '' -e 's#template/core\.js#template/js/flow.js#g' -e 's#core\.js#template/js/flow.js#g' \
  plugins/drawing-diagrams/skills/drawing-diagrams/diagrams/flow.py plugins/drawing-diagrams/skills/drawing-diagrams/diagrams/common.py
rg -n 'core\.(js|css)' plugins/drawing-diagrams/skills/drawing-diagrams/diagrams plugins/drawing-diagrams/skills/drawing-diagrams/render.py
```

Expected: `rg` prints nothing.

- [ ] **Step 9: Run the tests and render every example**

Run: `cd plugins/drawing-diagrams && python3 -m unittest discover -s tests -v`
Expected: all tests OK (the node test is skipped only where `node` is missing).

Run from `SKILL`: `for m in examples/*.json; do python3 render.py "$m" --mode page >/dev/null 2>&1 && python3 render.py "$m" --mode widget >/dev/null 2>&1 || echo "FAIL $m"; done`
Expected: no output.

- [ ] **Step 10: Commit**

```bash
claude plugin validate plugins/drawing-diagrams
git add -A plugins/drawing-diagrams/skills/drawing-diagrams plugins/drawing-diagrams/tests
git commit -m "refactor(drawing-diagrams): assets as CSS and JS fragments, widget carries only what it uses

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `tools/assets.py` and the first build of `template/dist`

Spec: §3.1 (`build`, `check`, `verify-cdn`), criteria 1 and 2.

**Files:**
- Create: `plugins/drawing-diagrams/tools/assets.py`
- Create: `SKILL/template/dist/dg.css`, `SKILL/template/dist/dg.js` (generated)
- Test: `plugins/drawing-diagrams/tests/test_assets_tool.py`

**Interfaces:**
- Consumes: `diagrams.assets.css_text`, `js_text`, `DIST`, `read_ref`, `cdn_url` (Task 2).
- Produces: CLI `python3 plugins/drawing-diagrams/tools/assets.py build|check|verify-cdn`; module functions `built() -> dict[str, bytes]`, `build() -> int`, `check() -> int`, `verify_cdn(get=fetch) -> int` where `get(url) -> (status: int, body: bytes)`.

- [ ] **Step 1: Write the failing tests**

`plugins/drawing-diagrams/tests/test_assets_tool.py`:

```python
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import support  # noqa: F401
import assets as tool
from diagrams import assets


class AssetsTool(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dist = Path(tmp.name)
        patcher = mock.patch.object(assets, "DIST", self.dist)
        patcher.start()
        self.addCleanup(patcher.stop)

    def quiet(self, fn, *args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            code = fn(*args)
        return code, err.getvalue()

    def test_check_passes_after_build_and_fails_after_a_change(self):
        self.assertEqual(self.quiet(tool.build)[0], 0)
        self.assertEqual(self.quiet(tool.check)[0], 0)
        (self.dist / "dg.js").write_text("changed")
        code, err = self.quiet(tool.check)
        self.assertEqual(code, 1)
        self.assertIn("dg.js", err)

    def test_verify_cdn_compares_bytes_at_ref(self):
        self.quiet(tool.build)
        (self.dist / "REF").write_text("b" * 40 + "\n")
        local = {name: (self.dist / name).read_bytes() for name in tool.FILES}
        seen = []

        def good(url):
            seen.append(url)
            return 200, local[url.rsplit("/", 1)[1]]

        self.assertEqual(self.quiet(tool.verify_cdn, good)[0], 0)
        self.assertTrue(all("@" + "b" * 40 + "/" in url for url in seen))
        self.assertEqual(self.quiet(tool.verify_cdn, lambda url: (200, b"other"))[0], 1)
        self.assertEqual(self.quiet(tool.verify_cdn, lambda url: (404, b""))[0], 1)

    def test_verify_cdn_needs_ref(self):
        self.quiet(tool.build)
        code, err = self.quiet(tool.verify_cdn, lambda url: (200, b""))
        self.assertEqual(code, 1)
        self.assertIn("REF", err)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd plugins/drawing-diagrams && python3 -m unittest discover -s tests -p test_assets_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'assets'`.

- [ ] **Step 3: Write the tool**

`plugins/drawing-diagrams/tools/assets.py`:

```python
#!/usr/bin/env python3
"""Build and check the published assets of the drawing-diagrams skill. For the plugin's maintainer;
SKILL.md does not mention it.

  assets.py build       write template/dist/dg.css and dg.js from template/css, template/js and the ramps
  assets.py check       exit 1 when template/dist differs from a fresh build
  assets.py verify-cdn  exit 1 unless jsDelivr serves template/dist at template/dist/REF byte for byte

Release: build and check; commit template/dist; write the SHA of that commit into template/dist/REF
and commit it; merge with a merge commit; after the merge run verify-cdn.
"""
import argparse
import sys
import urllib.request
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "drawing-diagrams"
sys.path.insert(0, str(SKILL))

from diagrams import assets  # noqa: E402

FILES = ("dg.css", "dg.js")


def built():
    return {"dg.css": assets.css_text().encode(), "dg.js": assets.js_text().encode()}


def build():
    assets.DIST.mkdir(parents=True, exist_ok=True)
    for name, data in built().items():
        (assets.DIST / name).write_bytes(data)
        print(f"записано {assets.DIST / name} ({len(data)} байт)")
    return 0


def check():
    stale = [name for name, data in built().items()
             if not (assets.DIST / name).exists() or (assets.DIST / name).read_bytes() != data]
    for name in stale:
        print(f"template/dist/{name} не совпадает с исходниками: запустите assets.py build", file=sys.stderr)
    return 1 if stale else 0


def fetch(url):
    with urllib.request.urlopen(url, timeout=20) as resp:
        return resp.status, resp.read()


def verify_cdn(get=fetch):
    ref = assets.read_ref()
    if not ref:
        print("нет template/dist/REF: сборка ещё не выпущена", file=sys.stderr)
        return 1
    bad = 0
    for name in FILES:
        url = assets.cdn_url(ref, name)
        try:
            status, data = get(url)
        except OSError as exc:  # URLError and HTTPError are OSError
            print(f"{url}: {exc}", file=sys.stderr)
            bad += 1
            continue
        local = (assets.DIST / name).read_bytes()
        if status != 200 or data != local:
            print(f"{url}: статус {status}, {len(data)} байт против {len(local)} локально", file=sys.stderr)
            bad += 1
        else:
            print(f"ок {url}")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("build", "check", "verify-cdn"))
    args = ap.parse_args(argv)
    return {"build": build, "check": check, "verify-cdn": verify_cdn}[args.command]()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd plugins/drawing-diagrams && python3 -m unittest discover -s tests -v`
Expected: all tests OK.

- [ ] **Step 5: Build `template/dist` and check it**

Run: `python3 plugins/drawing-diagrams/tools/assets.py build && python3 plugins/drawing-diagrams/tools/assets.py check; echo "exit=$?"`
Expected: two `записано …` lines, then `exit=0`.

- [ ] **Step 6: Commit**

```bash
claude plugin validate plugins/drawing-diagrams
git add plugins/drawing-diagrams/tools/assets.py plugins/drawing-diagrams/tests/test_assets_tool.py plugins/drawing-diagrams/skills/drawing-diagrams/template/dist
git commit -m "feat(drawing-diagrams): tools/assets.py builds and verifies the CDN assets

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Character budgets in text-fit messages

Spec: §4 R2 (which problems are text-fit), R5 (message shapes), criterion 7.

**Files:**
- Line numbers are those of the files before this task; the edits add lines, so find each place by the quoted code rather than by number.
- Modify: `SKILL/diagrams/common.py:66-73` (`ModelError`), append `fit_chars`, `two_line_chars`
- Modify: `SKILL/diagrams/flow.py:7` (import), `:220` (lists), `:284-309` (title, text, items), `:392`, `:421`, `:482` (raises), `:450-455` (label)
- Modify: `SKILL/diagrams/schema.py:100-103` (key row warning)
- Modify: `SKILL/diagrams/timeline.py:6` (import), `:23` (lists), `:66-72` (title, text), `:86-89` (raises)
- Test: `plugins/drawing-diagrams/tests/test_fit_messages.py`

**Interfaces:**
- Consumes: `tests/support.py` (Task 1).
- Produces: `ModelError(errors, layout=(), fit=())` with attribute `fit: list[str]` — every text-fit error is in both `layout` and `fit`; `common.fit_chars(n, need, room) -> int`; `common.two_line_chars(text, width, scale=0.88) -> int`. Task 5 prints the map only when `ModelError.layout` holds a message that is not in `ModelError.fit`.

- [ ] **Step 1: Write the failing tests**

`plugins/drawing-diagrams/tests/test_fit_messages.py`:

```python
import re
import unittest

import support  # noqa: F401
from diagrams import flow, schema, timeline
from diagrams.common import ModelError


def flow_model(nodes, grid, edges=(), kind="flow"):
    return {"kind": kind, "groups": {"g": {"label": "g", "ramp": "teal"}}, "nodes": nodes, "grid": grid,
            "edges": list(edges)}


class FitMessages(unittest.TestCase):
    def failure(self, mod, model):
        with self.assertRaises(ModelError) as ctx:
            mod.plan(model, "widget")
        return ctx.exception

    def message(self, exc, prefix):
        found = [e for e in exc.errors if e.startswith(prefix)]
        self.assertTrue(found, f"no error starting with {prefix!r} in {exc.errors}")
        return found[0]

    def assertBudget(self, message, pattern):
        m = re.search(pattern, message)
        self.assertIsNotNone(m, message)
        self.assertLess(int(m.group(2)), int(m.group(1)), message)

    def test_title(self):
        nodes = [{"id": n, "kind": "terminal", "title": "Очень длинный заголовок узла" if n == "a" else n.upper()}
                 for n in "abcd"]
        exc = self.failure(flow, flow_model(nodes, ["a b c d"]))
        msg = self.message(exc, "узел a:")
        self.assertBudget(msg, r"заголовок (\d+) симв\., влезает (\d+)")
        self.assertIn(msg, exc.fit)
        self.assertIn(msg, exc.layout)

    def test_text(self):
        text = "Длинное описание шага, которое никак не помещается в две строки узкой карточки на четыре колонки"
        nodes = [{"id": n, "title": n.upper(), **({"text": text} if n == "a" else {})} for n in "abcd"]
        exc = self.failure(flow, flow_model(nodes, ["a b c d"]))
        msg = self.message(exc, "узел a:")
        self.assertBudget(msg, r"текст (\d+) симв\., в две строки влезает ~(\d+)")
        self.assertIn(msg, exc.fit)

    def test_block_item(self):
        item = "очень длинный пункт блока, который займёт заметно больше двух строк в карточке шириной в треть виджета"
        nodes = [{"id": n, "title": n.upper(), "items": [item] if n == "a" else []} for n in "abc"]
        exc = self.failure(flow, flow_model(nodes, ["a b c"], kind="blocks"))
        msg = self.message(exc, "узел a:")
        self.assertBudget(msg, r"пункт 1 — (\d+) симв\., влезает ~(\d+)")
        self.assertIn(msg, exc.fit)

    def test_edge_label(self):
        nodes = [{"id": "a?", "title": "Да?"}, {"id": "b", "kind": "terminal", "title": "B"},
                 {"id": "c", "kind": "terminal", "title": "C"}]
        exc = self.failure(flow, flow_model(nodes, ["a? b", "c ."], ["a? -> b : вправо идём", "a? -> c : вниз"]))
        msg = self.message(exc, "связь a? -> b:")
        self.assertBudget(msg, r"подпись 'вправо идём' (\d+) симв\. не помещается .*, влезает ~(\d+)")
        self.assertIn(msg, exc.fit)

    def test_schema_key_row_warning(self):
        tables = [{"id": "t", "name": "t", "group": "g",
                   "columns": [{"name": "external_correlation_identifier", "type": "uuid", "flags": ["PK"]}]}]
        tables += [{"id": x, "name": x, "group": "g", "columns": [{"name": "id", "flags": ["PK"]}]} for x in "uv"]
        _, warnings = schema.plan({"kind": "schema", "groups": {"g": {"label": "g", "ramp": "teal"}},
                                   "tables": tables, "grid": ["t u v"]}, "widget")
        msg = next(w for w in warnings if w.startswith("таблица t.external_correlation_identifier:"))
        self.assertBudget(msg, r"имя (\d+) симв\., влезает ~(\d+)")

    def test_timeline_title_and_text(self):
        model = {"kind": "timeline", "entities": [{"id": "e", "label": "e"}],
                 "moments": [{"id": "m1", "label": "t1", "title": ("Заголовок момента " * 5).strip(),
                              "text": "слово " * 60, "states": {"e": "x"}},
                             {"id": "m2", "label": "t2", "title": "ок", "states": {"e": "y"}}]}
        exc = self.failure(timeline, model)
        titles = [e for e in exc.errors if "заголовок" in e]
        texts = [e for e in exc.errors if "текст" in e]
        self.assertBudget(titles[0], r"момент m1: заголовок (\d+) симв\., влезает (\d+)")
        self.assertBudget(texts[0], r"момент m1: текст (\d+) симв\., в две строки влезает ~(\d+)")
        self.assertEqual(sorted(exc.fit), sorted(titles + texts))


if __name__ == "__main__":
    unittest.main()
```

If `test_edge_label` finds no label message because the router routes `a? -> b` another way, print `exc.errors`, keep the same model shape and move `b` so that the edge leaves sideways into an occupied neighbour (the "у выхода вбок" place, 23 px of room in a widget flow).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd plugins/drawing-diagrams && python3 -m unittest discover -s tests -p test_fit_messages.py -v`
Expected: FAIL — the messages still say `заголовок шире карточки на …px` and `ModelError` has no `fit`.

- [ ] **Step 3: `ModelError.fit` and the budget helpers in `common.py`**

Replace the `ModelError` class with:

```python
class ModelError(Exception):
    """Validation failed. `errors` is the list of messages; `layout` marks the ones --draft may
    downgrade to warnings; `fit` marks the layout errors about a text too long for its place."""

    def __init__(self, errors, layout=(), fit=()):
        super().__init__("\n".join("ошибка: " + e for e in errors))
        self.errors = list(errors)
        self.layout = list(layout)
        self.fit = list(fit)
```

Append at the end of `common.py`:

```python
def fit_chars(n, need, room):
    """Characters of an n-character text that fit `room` px when all n need `need` px."""
    if need <= 0:
        return n
    return max(int(n * room / need), 1)


def two_line_chars(text, width, scale=0.88):
    """About how many characters of `text` fit two word-wrapped lines of `width` px. Wrapping leaves
    the ends of lines short, so a tenth of the room is kept in reserve."""
    return fit_chars(len(text), text_width(text, scale) * 1.05, 2 * width * 0.9)
```

- [ ] **Step 4: Budgets in `flow.py`**

Import line 7 becomes:

```python
from .common import (BASE_MODES, ID_RE, RAMPS, ModelError, esc, fit_chars, label_width, labels_for, text_width,
                     two_line_chars, wrap_lines)
```

Line 220 becomes:

```python
    errors, layout_errors, fit_errors, warnings = [], [], [], []

    def fit_error(msg):
        layout_errors.append(msg)
        fit_errors.append(msg)
```

Replace the title check (lines 284–287):

```python
        need = text_width(n["title"]) * 1.04 + 20 + extra
        if need > card_w:
            fit_error(f"узел {nid}: заголовок {len(n['title'])} симв., влезает "
                      f"{fit_chars(len(n['title']), need - 20 - extra, card_w - 20 - extra)}; "
                      f"сократите заголовок или сузьте grid")
```

Replace the text check (lines 298–301):

```python
        if text:
            if wrap_lines(text, card_w - 20) > 2:
                fit_error(f"узел {nid}: текст {len(text)} симв., в две строки влезает ~{two_line_chars(text, card_w - 20)}; "
                          f"сократите или вынесите в сноску")
```

Replace the item check (lines 307–309):

```python
        for pos, it in enumerate(items, 1):
            if wrap_lines(it, card_w - 30) > 2:
                fit_error(f"узел {nid}: пункт {pos} — {len(it)} симв., влезает ~{two_line_chars(it, card_w - 30)}")
```

Replace the label error (lines 450–455, inside `if spot is None:`):

```python
        if spot is None:
            spot = max(spots, key=lambda s: s["room"])
            room = max(spot["room"], 0)
            fit_error(f"связь {e['a']} -> {e['b']}: подпись {text!r} {len(text)} симв. не помещается {spot['where']}, "
                      f"влезает ~{max(int(room / 7), 1)}; сократите, вынесите в сноску [n] "
                      f"или переставьте узлы так, чтобы линия уходила вниз")
```

In the three raises add the fit list:
- line 392: `raise ModelError(errors + layout_errors, layout=layout_errors, fit=fit_errors)`
- lines 421 and 482: `raise ModelError(layout_errors, layout=layout_errors, fit=fit_errors)`

- [ ] **Step 5: Budget in the schema key row warning**

Replace lines 100–103 of `schema.py`:

```python
                if need > card_w:
                    budget = max(int((card_w - (need - len(name) * ch)) / ch), 1)
                    warnings.append(f"таблица {tid}.{name}: имя {len(name)} симв., влезает ~{budget}; "
                                    f"сузьте grid или сократите имя")
```

- [ ] **Step 6: Budgets in `timeline.py`**

Import line 6 becomes:

```python
from .common import BASE_MODES, ID_RE, ModelError, esc, fit_chars, labels_for, text_width, two_line_chars, wrap_lines
```

Line 23 becomes:

```python
    errors, layout_errors, fit_errors, warnings = [], [], [], []

    def fit_error(msg):
        layout_errors.append(msg)
        fit_errors.append(msg)
```

Replace lines 66–72:

```python
        tag = m.get("tag") or ""
        tag_w = text_width(tag) * 0.9 + 8 if tag else 0
        need = text_width(m["title"]) * 1.04 + 20 + tag_w
        if need > card_w:
            fit_error(f"момент {mid}: заголовок {len(m['title'])} симв., влезает "
                      f"{fit_chars(len(m['title']), need - 20 - tag_w, card_w - 20 - tag_w)}")
        text = m.get("text") or ""
        if text and wrap_lines(text, card_w - 20) > 2:
            fit_error(f"момент {mid}: текст {len(text)} симв., в две строки влезает ~{two_line_chars(text, card_w - 20)}")
```

Lines 86–89 become:

```python
    if errors:
        raise ModelError(errors + layout_errors, layout=layout_errors, fit=fit_errors)
    if layout_errors and not draft:
        raise ModelError(layout_errors, layout=layout_errors, fit=fit_errors)
```

- [ ] **Step 7: Run all tests and render every example**

Run: `cd plugins/drawing-diagrams && python3 -m unittest discover -s tests -v`
Expected: all tests OK.

Run from `SKILL`: `for m in examples/*.json; do python3 render.py "$m" --check >/dev/null 2>&1 || echo "FAIL $m"; done`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
claude plugin validate plugins/drawing-diagrams
git add plugins/drawing-diagrams/skills/drawing-diagrams/diagrams plugins/drawing-diagrams/tests/test_fit_messages.py
git commit -m "feat(drawing-diagrams): text-fit errors name the length and the budget in characters

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `render.py` — assets modes, one-command loop, batch

Spec: §3.2 (modes, fallback, `--no-assets`), §4 R1–R4, criteria 3, 5, 6, 8.

**Files:**
- Modify: `SKILL/render.py` (whole file)
- Test: `plugins/drawing-diagrams/tests/test_render_cli.py`

**Interfaces:**
- Consumes: `assets.read_ref`, `assets.harness`, kinds' `render(..., assets_mode=)` (Task 2); `ModelError.layout`, `ModelError.fit` (Task 4); `diagrams.grid.parse_grid(rows, errors) -> (cells, width, height)`, `diagrams.grid.ascii_map(cells, width, height) -> str` (existing).
- Produces: `render.main(argv: list[str]) -> int`; CLI flags `--assets cdn|inline|none`, `--no-assets`, `--out-dir DIR`, several `MODEL.json` arguments.

- [ ] **Step 1: Write the failing tests**

`plugins/drawing-diagrams/tests/test_render_cli.py`:

```python
import io
import json
import statistics
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import support
import render
from diagrams import assets

REF = "c" * 40
GROUPS = {"g": {"label": "g", "ramp": "teal"}}
GOOD = {"kind": "flow", "id": "good", "groups": GROUPS,
        "nodes": [{"id": "a", "kind": "terminal", "group": "g", "title": "Старт"},
                  {"id": "b", "kind": "terminal", "group": "g", "title": "Финиш"}],
        "grid": ["a", "b"], "edges": ["a -> b"]}
LONG_TITLE = {"kind": "flow", "id": "bad", "groups": GROUPS, "grid": ["a b c d"], "edges": [],
              "nodes": [{"id": n, "kind": "terminal", "title": "Очень длинный заголовок узла" if n == "a" else n.upper()}
                        for n in "abcd"]}
WIDE = {"kind": "flow", "id": "wide", "groups": GROUPS, "grid": ["a b c d e"],
        "nodes": [{"id": n, "kind": "terminal", "title": n.upper()} for n in "abcde"],
        "edges": ["a -> b", "b -> c", "c -> d", "d -> e"]}
EXAMPLES = ("kyc-module", "resolver-rules", "kyc-trace", "verdict-row-lifecycle", "four-blocks", "mark-timeline")


class RenderCli(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.dist = self.tmp / "dist"
        self.dist.mkdir()
        patcher = mock.patch.object(assets, "DIST", self.dist)
        patcher.start()
        self.addCleanup(patcher.stop)

    def model(self, data):
        path = self.tmp / f"{data['id']}.json"
        path.write_text(json.dumps(data, ensure_ascii=False))
        return str(path)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = render.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def publish(self):
        (self.dist / "REF").write_text(REF + "\n")

    def test_widget_defaults_to_cdn_links(self):
        self.publish()
        code, out, _ = self.run_cli(self.model(GOOD))
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith('<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/chelout/'
                                       f'plugins-marketplace@{REF}/'), out[:160])
        self.assertTrue(out.endswith('/template/dist/dg.js"></script>'), out[-160:])
        self.assertNotIn("<style>", out)

    def test_cdn_without_ref_falls_back_to_inline(self):
        code, out, err = self.run_cli(self.model(GOOD))
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("<style>"))
        self.assertIn("нет template/dist/REF", err)

    def test_no_assets_is_assets_none(self):
        self.publish()
        path = self.model(GOOD)
        alias, none = self.run_cli(path, "--no-assets")[1], self.run_cli(path, "--assets", "none")[1]
        self.assertEqual(alias, none)
        self.assertNotIn("<style>", none)
        self.assertNotIn("<link", none)

    def test_page_defaults_to_the_full_inline_build(self):
        self.publish()
        code, out, _ = self.run_cli(self.model(GOOD), "--mode", "page")
        self.assertEqual(code, 0)
        self.assertIn(".dg-tl{", out)
        self.assertIn("drawKind.schema", out)

    def test_text_fit_failure_has_empty_stdout_and_no_map(self):
        code, out, err = self.run_cli(self.model(LONG_TITLE))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("заголовок", err)
        self.assertNotIn("пересечений линий", err)

    def test_layout_failure_prints_the_map(self):
        code, out, err = self.run_cli(self.model(WIDE))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("grid шириной 5", err)
        self.assertIn("пересечений линий", err)

    def test_several_models_need_out_dir(self):
        code, out, err = self.run_cli(self.model(GOOD), self.model(dict(GOOD, id="good2")))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("--out-dir", err)

    def test_batch_writes_every_model(self):
        out_dir = self.tmp / "out"
        code, out, _ = self.run_cli(self.model(GOOD), self.model(dict(GOOD, id="good2")), "--out-dir", str(out_dir))
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p.name for p in out_dir.iterdir()), ["good.html", "good2.html"])
        self.assertEqual(len(out.strip().splitlines()), 2)

    def test_batch_with_failures_writes_nothing_and_reports_all(self):
        out_dir = self.tmp / "out"
        bad1, bad2 = self.model(LONG_TITLE), self.model(WIDE)
        code, out, err = self.run_cli(self.model(GOOD), bad1, bad2, "--out-dir", str(out_dir))
        self.assertEqual((code, out), (1, ""))
        self.assertFalse(out_dir.exists())
        self.assertIn(bad1, err)
        self.assertIn(bad2, err)

    def test_cdn_fragments_of_the_examples(self):
        self.publish()
        sizes = []
        for name in EXAMPLES:
            path = next(support.SKILL.joinpath("examples").rglob(f"{name}.json"))
            code, out, err = self.run_cli(str(path))
            self.assertEqual(code, 0, err)
            sizes.append(len(out))
        print(f"\ncdn widget fragments of the examples: {dict(zip(EXAMPLES, sizes))}, median {statistics.median(sizes)}")
        self.assertLessEqual(statistics.median(sizes), 6000, sizes)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd plugins/drawing-diagrams && python3 -m unittest discover -s tests -p test_render_cli.py -v`
Expected: FAIL — `render.py: error: unrecognized arguments` for the `--assets` and several-model cases, and assertion failures for the rest.

- [ ] **Step 3: Rewrite `render.py`**

Replace the whole file with:

```python
#!/usr/bin/env python3
"""Render diagrams from JSON models. A model's `kind` picks the renderer.

Usage:
    render.py MODEL.json [MODEL.json ...] [--mode widget|page] [--out FILE | --out-dir DIR]
              [--assets cdn|inline|none] [--no-assets] [--check] [--draft]
              [--format html|mermaid|ascii] [--open] [--types] [--width PX] [--harness]

Kinds: schema, flow, swimlane, state, blocks, timeline (reference/common.md).

Every render checks the model first. On errors stdout stays empty, the exit status is 1 and stderr
lists every problem, with the ASCII map when a line or the grid failed rather than the length of a
text. Warnings go to stderr and the output is still produced. --draft turns layout errors into
warnings and stamps the output as a draft.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diagrams import assets  # noqa: E402
from diagrams import flow, schema, timeline  # noqa: E402
from diagrams.common import ModelError  # noqa: E402
from diagrams.grid import ascii_map, parse_grid  # noqa: E402

KINDS = {"schema": schema, "flow": flow, "swimlane": flow, "state": flow, "blocks": flow, "timeline": timeline}
SUFFIX = {"html": ".html", "mermaid": ".mmd", "ascii": ".txt"}


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", nargs="+", help="JSON model; several models need --out-dir")
    ap.add_argument("--mode", choices=("widget", "page"), default="widget",
                    help="widget: 680px fragment for a chat widget; page: 1100px section for a page or artifact")
    ap.add_argument("--format", choices=("html", "mermaid", "ascii"), default="html",
                    help="html for chat and pages; mermaid for markdown in a repository; ascii for the terminal")
    ap.add_argument("--out", help="write the output here instead of stdout")
    ap.add_argument("--out-dir", help="write DIR/<id>.<ext> per model; nothing is written if any model fails")
    ap.add_argument("--assets", choices=("cdn", "inline", "none"),
                    help="cdn: links to the published CSS and JS (widget default); inline: CSS and JS inside "
                         "(page default); none: markup only, for the second and later diagrams of a page")
    ap.add_argument("--no-assets", action="store_true", help="same as --assets none")
    ap.add_argument("--check", action="store_true",
                    help="check only and print the ASCII map (width checks honour --open, --types, --width)")
    ap.add_argument("--draft", action="store_true",
                    help="downgrade layout errors to warnings and stamp the output as a draft")
    ap.add_argument("--open", action="store_true", help="schema: start with all columns visible")
    ap.add_argument("--types", action="store_true", help="schema: show types on key rows too")
    ap.add_argument("--width", type=int, help="total width in px instead of the mode default (680 / 1100)")
    ap.add_argument("--harness", action="store_true",
                    help="widget mode: wrap the fragment into a standalone page for a browser")
    return ap.parse_args(argv)


def resolve_assets(args):
    """The assets mode of this run, and a warning when cdn has to fall back to inline."""
    mode = "none" if args.no_assets else args.assets or ("cdn" if args.mode == "widget" else "inline")
    if mode == "cdn" and assets.read_ref() is None:
        return "inline", "сборка для CDN не выпущена (нет template/dist/REF), CSS и JS встроены"
    return mode, None


def load(path):
    """(model, renderer module); raises ValueError with the message to print."""
    try:
        model = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"ошибка: не читается модель {path}: {exc}")
    if model.get("kind") not in KINDS:
        raise ValueError(f"ошибка: {path}: поле kind обязательно; доступны: {', '.join(KINDS)}")
    return model, KINDS[model["kind"]]


def failure_map(mod, model, mode_name, overrides, exc):
    """The ASCII map of a model that failed on layout rather than on the length of a text, else None."""
    if not any(e not in exc.fit for e in exc.layout):
        return None
    if mod is schema:
        cells, cols, rows = parse_grid(model.get("grid"), [])
        return ascii_map(cells, cols, rows)
    try:
        layout, _ = mod.plan(model, mode_name, overrides, draft=True)
    except ModelError:
        return None
    return mod.ascii(model, layout)


def produce(model, mod, args, overrides, assets_mode):
    """(output text, warnings, layout) of one model; raises ModelError."""
    layout, warnings = mod.plan(model, args.mode, overrides, draft=args.draft)
    if args.check or args.format == "ascii":
        return mod.ascii(model, layout) + "\n", warnings, layout
    if args.format == "mermaid":
        return mod.mermaid(model, layout) + "\n", warnings, layout
    out = mod.render(model, args.mode, layout, warnings, assets_mode=assets_mode, draft=bool(layout.get("draft")))
    return (assets.harness(out) if args.harness else out), warnings, layout


def main(argv=None):
    args = parse_args(argv)
    batch = len(args.model) > 1
    if batch and not args.out_dir:
        print("ошибка: несколько моделей рендерятся только с --out-dir", file=sys.stderr)
        return 1
    if args.out and args.out_dir:
        print("ошибка: --out и --out-dir вместе не используются", file=sys.stderr)
        return 1
    if args.harness and args.mode != "widget":
        print("ошибка: --harness имеет смысл только в режиме widget", file=sys.stderr)
        return 1
    overrides = {}
    if args.open:
        overrides["open"] = True
    if args.types:
        overrides["type_on_keys"] = True
    if args.width:
        overrides["total"] = args.width
    assets_mode, note = resolve_assets(args)
    if note and args.format == "html" and not args.check:
        print("предупреждение: " + note, file=sys.stderr)

    done, failed = [], False
    for path in args.model:
        if batch:
            print(f"== {path}", file=sys.stderr)
        try:
            model, mod = load(path)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            failed = True
            continue
        try:
            out, warnings, layout = produce(model, mod, args, overrides, assets_mode)
        except ModelError as exc:
            print(exc, file=sys.stderr)
            picture = failure_map(mod, model, args.mode, overrides, exc)
            if picture:
                print(picture, file=sys.stderr)
            if args.draft and mod is schema:
                print("черновик: для schema ошибки раскладки нужно исправить, маршрутизатора у схем нет",
                      file=sys.stderr)
            failed = True
            continue
        for w in warnings:
            print("предупреждение: " + w, file=sys.stderr)
        if not args.check and args.format != "ascii" and layout.get("crossings", 0) >= 3:
            print(mod.ascii(model, layout), file=sys.stderr)
        done.append((path, model, out, warnings, layout))
    if failed:
        return 1

    if args.check:
        for path, model, out, warnings, layout in done:
            sys.stdout.write(out)
            n = len(model.get("tables") or model.get("nodes") or model.get("moments") or [])
            print(f"ок: вид {model['kind']}, {n} узлов, {len(layout['edges'])} связей, "
                  f"{len(warnings)} предупреждений", file=sys.stderr)
        return 0
    if args.out_dir:
        target_dir = Path(args.out_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        for path, model, out, _, _ in done:
            target = target_dir / f"{model.get('id') or Path(path).stem}{SUFFIX[args.format]}"
            target.write_text(out)
            print(f"{target} ({len(out)} байт)")
        return 0
    out = done[0][2]
    if args.out:
        Path(args.out).write_text(out)
        print(f"записано {args.out} ({len(out)} байт)", file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run all tests**

Run: `cd plugins/drawing-diagrams && python3 -m unittest discover -s tests -v`
Expected: all tests OK; `test_cdn_fragments_of_the_examples` prints the six sizes and a median of at most 6000.

- [ ] **Step 5: Commit**

```bash
claude plugin validate plugins/drawing-diagrams
git add plugins/drawing-diagrams/skills/drawing-diagrams/render.py plugins/drawing-diagrams/tests/test_render_cli.py
git commit -m "feat(drawing-diagrams): render.py checks, prints only the fragment, links CDN assets, renders batches

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Browser check of inline widgets (controller)

Spec: criterion 4. Needs the in-app Browser tools, so the controller runs it.

**Files:** none committed. Scratch output in `.experiments/harness/`.

- [ ] **Step 1: Exclude the experiment directory from git**

Run: `rg -qx '\.experiments/' "$(git rev-parse --git-common-dir)/info/exclude" || echo '.experiments/' >> "$(git rev-parse --git-common-dir)/info/exclude"`

- [ ] **Step 2: Render harness pages for the six examples in inline widget mode**

```bash
mkdir -p .experiments/harness
for name in kyc-module resolver-rules kyc-trace verdict-row-lifecycle four-blocks mark-timeline; do
  m=$(find plugins/drawing-diagrams/skills/drawing-diagrams/examples -name "$name.json" | head -1)
  python3 plugins/drawing-diagrams/skills/drawing-diagrams/render.py "$m" --mode widget --assets inline --harness \
    --out ".experiments/harness/$name.html" || echo "FAIL $name"
done
python3 -m http.server 8769 -d .experiments/harness >/dev/null 2>&1 & echo "server pid $!"
```

Expected: six `записано …` lines on stderr, no `FAIL`, a pid. Stop the server later with `kill <pid>`, never by process name.

- [ ] **Step 3: Check each page in the in-app browser**

For each `http://localhost:8769/<name>.html`, navigate and run in the page:

```js
(() => { const s = document.querySelector('.dg'); const e = s.querySelector('.dg-edges');
  const edges = e ? JSON.parse(e.textContent).length : 0;
  const drawn = s.querySelectorAll('.dg-svg > g').length;
  const route = s.querySelector('.dg-route'); if (route) route.click();
  const dimmed = s.querySelectorAll('.dg-c.lo').length;
  const toggle = s.querySelector('.dg-toggle'); const card = toggle && toggle.closest('.dg-c');
  const before = card ? card.classList.contains('open') : null; if (toggle) toggle.click();
  const after = card ? card.classList.contains('open') : null;
  return {kind: s.dataset.kind, edges, drawn, route: !!route, dimmed, toggled: toggle ? before !== after : null}; })()
```

Expected per page: `drawn === edges`; when `route` is true, `dimmed > 0`; for `kyc-module`, `toggled === true`; for `mark-timeline`, `edges === 0`. Read the console messages of each page: no errors.

- [ ] **Step 4: Compare the look with commit `6f4674a`**

```bash
ROOT=$(cd "$(git rev-parse --git-common-dir)/.." && pwd)
[ -d "$ROOT/.worktrees/v0" ] || git -C "$ROOT" worktree add --detach "$ROOT/.worktrees/v0" 6f4674a
V0="$ROOT/.worktrees/v0/plugins/drawing-diagrams/skills/drawing-diagrams"
python3 "$V0/render.py" "$V0/examples/resolver-rules.json" --mode widget --harness --out .experiments/harness/v0-resolver-rules.html
python3 "$V0/render.py" "$V0/examples/kyc-module.json" --mode widget --harness --out .experiments/harness/v0-kyc-module.html
```

Take screenshots of `resolver-rules.html` next to `v0-resolver-rules.html` and `kyc-module.html` next to `v0-kyc-module.html`: cards, lines, labels and legend look the same.

- [ ] **Step 5: Stop the server**

Run: `kill <pid from Step 2>`

---

### Task 7: Reference split, field tables, small schema sample, `design.md` move

Spec: §5.1–§5.4, criteria 9 and 13.

**Files:**
- Create: `SKILL/reference/common.md`, `schema.md`, `flow.md`, `timeline.md`, `output.md`
- Delete: `SKILL/reference/model.md`
- Create: `SKILL/examples/schema-small.json`
- Move: `SKILL/examples/kyc-module.json` → `SKILL/examples/full/kyc-module.json`
- Move: `SKILL/design.md` → `plugins/drawing-diagrams/docs/design.md`; append §13

**Interfaces:**
- Consumes: CLI of Task 5 (documented in `reference/common.md`), message shapes of Task 4.
- Produces: the file names Task 8's `SKILL.md` points at: `reference/common.md`, `reference/schema.md`, `reference/flow.md`, `reference/timeline.md`, `reference/output.md`, `examples/schema-small.json`.

- [ ] **Step 1: Split `model.md` with a checked script**

Run from the repository root:

```bash
python3 - <<'EOF'
import re
from pathlib import Path

ref = Path("plugins/drawing-diagrams/skills/drawing-diagrams/reference")
text = (ref / "model.md").read_text()
chunks = re.split(r"(?m)^(?=## )", text)
sec = {c.splitlines()[0][3:].strip(): c for c in chunks[1:]}
names = ["Common top level", "Grid map", "Groups", "Edges", "Labels", "Modes and flags", "Kind `schema`",
         "Verifying the output", "Kind `flow`", "Kind `swimlane`", "Exports", "Kind `state`", "Kind `blocks`",
         "Kind `timeline`"]
assert sorted(sec) == sorted(names), sorted(sec)
used = []


def take(name):
    used.append(name)
    return sec[name]


def body(name):
    return take(name).split("\n", 1)[1]


def swap(s, old, new):
    assert s.count(old) == 1, old
    return s.replace(old, new)


common = """# Model format: common parts

`render.py` checks a JSON model and turns it into HTML. The model holds content and a grid map only;
look, connectors, toggles and legend are the renderer's. `kind` picks the renderer and the file to read
next: `reference/schema.md` for `schema`; `reference/flow.md` for `flow`, `swimlane`, `state` and
`blocks`; `reference/timeline.md` for `timeline`. `reference/output.md` covers looking at a rendered
diagram and exports.

"""
top = take("Common top level")
top = swap(top, "| `kind` | yes | `schema` today; `flow`, `swimlane`, `state`, `timeline`, `blocks` planned |",
           "| `kind` | yes | `schema`, `flow`, `swimlane`, `state`, `blocks` or `timeline` |")
top = swap(top, "| `edges` | no | Connectors, shorthand strings or objects |",
           "| `edges` | no | Connectors; the syntax is in the file of the kind |")
grid = swap(take("Grid map"), "`--check` prints the map back, so a misplaced node is visible before any\nrender.",
            "A layout error prints the map back, and so does `--check`.")
modes = take("Modes and flags")
modes = swap(modes, "| Embed | pass the fragment to `show_widget` as HTML | paste into the page; `--no-assets` for the second diagram |",
             "| Assets (`--assets`) | `cdn` by default: links to the published CSS and JS; `inline` carries only what the diagram uses | `inline` by default: all CSS and JS; `none` for the second and later diagrams of a page |\n"
             "| Embed | pass stdout to `show_widget` unchanged | paste into the page |")
modes = swap(modes, "no icon font, no web font,\nno external resource. The output passes an artifact CSP.",
             "no icon font, no web font.\nWith inline assets the output has no external resource and passes an artifact CSP;\n"
             "with `--assets cdn` a widget loads its CSS and JS from jsDelivr.")
commands = """## Commands

```bash
python3 ${CLAUDE_SKILL_DIR}/render.py model.json --mode widget              # chat: stdout goes to show_widget
python3 ${CLAUDE_SKILL_DIR}/render.py model.json --mode page --out a.html
python3 ${CLAUDE_SKILL_DIR}/render.py a.json b.json --mode page --out-dir out
python3 ${CLAUDE_SKILL_DIR}/render.py model.json --check                     # the map and the checks only
python3 ${CLAUDE_SKILL_DIR}/render.py model.json --format mermaid            # markdown in a repository
```

Every render checks the model. On errors stdout is empty and stderr lists every problem at once. A text
that does not fit names its length and how many characters fit (`заголовок 24 симв., влезает 19`), so
one edit fixes it; a line or grid problem also prints the map. Several models in one call write nothing
when any of them fails. Warnings do not stop the render; treat them as errors unless the user accepts
the trade-off. A chat widget carries one diagram: render every widget separately.
"""
(ref / "common.md").write_text(common + top + grid + take("Groups") + take("Labels") + modes + commands)

schema_fields = """# Kind `schema`

Database tables as cards; foreign keys and logical joins as lines between key rows. Common fields, grid
and groups: `reference/common.md`.

## Fields

| Field | Required | Meaning and limits |
|---|---|---|
| `tables[].id` | yes | lowercase latin, digits, `_`; used in the grid map and edges |
| `tables[].name` | yes | table name in the header |
| `tables[].group` | yes | a key of `groups` |
| `tables[].subtitle` | no | small line under the name |
| `tables[].columns` | yes | list of columns, below |
| `tables[].details` | no | HTML lines shown only when the card is open |
| `tables[].notes` | no | lines always visible under the columns; one or two |
| `columns[].name` | yes | unique in the table; a key row name fits about 20 characters in a 3-column widget |
| `columns[].type` | no | shown on key rows in page mode or with `--types`, on the other rows when open |
| `columns[].flags` | no | subset of `PK`, `FK`, `U`, `N` |
| `columns[].key` | no | icon and key-row marker: connection, tenant, user, profile, attempt, id, check, external, kind, key, link, dot |
| `edges[]` | no | `"a.col -> b.col \\| modifiers"`, see Edges |

"""
schema_body = re.sub(r"(?m)^### ", "## ", body("Kind `schema`"))
schema_body = swap(schema_body, "a key row wider than the card (the name wraps), a table",
                   "a key row wider than the card (the name wraps; the warning names how many characters fit), a table")
(ref / "schema.md").write_text(schema_fields + "## Edges\n" + body("Edges") + schema_body)

flow_fields = """# Kinds `flow`, `swimlane`, `state`, `blocks`

One engine for four kinds: steps and decisions, lanes of participants, states, blocks. Common fields,
grid and groups: `reference/common.md`.

## Fields

| Field | Required | Meaning and limits |
|---|---|---|
| `nodes[].id` | yes | lowercase latin, digits, `_`; a trailing `?` makes a decision |
| `nodes[].kind` | no | `step` (default in flow and swimlane), `decision`, `terminal`, `note`, `state` (default in state), `block` (default in blocks) |
| `nodes[].title` | yes | one line; widget: 22 characters at 3 columns (decision 19), 15 at 4 (decision 12), 9 in a 5-lane swimlane; page: 28 at 4 columns, 16 at 6 |
| `nodes[].text` | no | at most two lines, about twice the title budget; `[n]` at the end references a footnote; not shown on a terminal |
| `nodes[].group` | no | a key of `groups`; in a swimlane the lane gives the colour and a different `group` is an error |
| `nodes[].items` | no | `block` only: at most 5, each at most two lines (44 characters at 3 widget columns) |
| `lanes` | swimlane | group ids, one per grid column, left to right |
| `edges[]` | no | `"a -> b : label [n] \\| dashed"`; a label is at most 3 words or 24 characters |
| `footnotes` | no | texts referenced as `[n]` from labels or node text |
| `routes` | no | `{"name": [ids]}`; every consecutive pair must be an edge |

Limits: widget 4 columns and 16 nodes (blocks 3 and 12, swimlane 5 lanes); page 6 columns and 30 nodes
(blocks 5 and 20, swimlane 7 lanes).

"""
flow_body = body("Kind `flow`")
flow_body = swap(flow_body, "in pixels exactly where `drawFlow` in `template/core.js` draws it: card width",
                 "in pixels exactly where the widget script draws it: card width")
flow_body = swap(flow_body, "keeps 2 px from a card edge. The offsets live in two places, `LABEL_*` in\n"
                            "`diagrams/flow.py` and the label branch of `drawFlow`; change them together.",
                 "keeps 2 px from a card edge.")
flow_body = swap(flow_body, "By default `core.js` centres", "By default the script centres")
flow_body = swap(flow_body, "hands the row to `core.js` as `ly`", "hands the row to the script as `ly`")
flow_body = swap(flow_body, "a title or text that does not fit.",
                 "a title, text, item or label that does not fit (the message names its length and how many\ncharacters fit).")
(ref / "flow.md").write_text(flow_fields + "## Flow\n" + flow_body + "## Swimlane\n" + body("Kind `swimlane`")
                             + "## State\n" + body("Kind `state`") + "## Blocks\n" + body("Kind `blocks`"))

timeline_fields = """# Kind `timeline`

A story over time: a rail of moments, one card per moment, entity states as chips. No grid, no edges,
no groups.

## Fields

| Field | Required | Meaning and limits |
|---|---|---|
| `entities[]` | yes | `{"id", "label"}`; up to four, in the order the chips appear |
| `moments[]` | yes | at least 2; at most 12 in widget mode, 24 in page mode |
| `moments[].id` | yes | lowercase latin, digits, `_` |
| `moments[].label` | no | rail mark (t1, a date), defaults to `id`; about 6 characters in widget mode |
| `moments[].tag` | no | small uppercase word next to the title |
| `moments[].title` | yes | one line: about 70 characters in widget mode, 120 in page mode, less with a tag |
| `moments[].text` | no | at most two lines |
| `moments[].states` | no | `{entity id: value}` for what changed; a value over 28 characters is a warning |

"""
timeline_body = swap(body("Kind `timeline`"), "A story over time. No grid, no edges.\n\n", "")
(ref / "timeline.md").write_text(timeline_fields + "## Model\n" + timeline_body)

output = """# Output: looking at a diagram, exports

Read this only to look at a rendered diagram outside the chat or to export it.

"""
verify = swap(take("Verifying the output"), "it, then pass the plain fragment to `show_widget`.",
              "it, then pass the plain fragment to `show_widget`. A harness page of a widget rendered with\n"
              "`--assets cdn` needs jsDelivr; offline, render it with `--assets inline`.")
(ref / "output.md").write_text(output + verify + take("Exports"))

assert sorted(used) == sorted(names), sorted(set(names) - set(used))
assert len(used) == len(set(used))
(ref / "model.md").unlink()
for f in sorted(ref.glob("*.md")):
    print(f"{f.name:14} {len(f.read_text()):6d}")
EOF
```

Expected: no assertion error; five lines with sizes close to common ≈ 4.5K, schema ≈ 5.8K, flow ≈ 11K, timeline ≈ 2.2K, output ≈ 1.5K characters. Then `rg -n 'core\.js|model\.md|design\.md' plugins/drawing-diagrams/skills/drawing-diagrams/reference` prints nothing.

- [ ] **Step 2: Add the small schema sample and move the large one**

`SKILL/examples/schema-small.json`:

```json
{
  "kind": "schema",
  "id": "schema-small",
  "title": "Заказы и оплаты",
  "summary": "Три таблицы: клиенты из CRM, заказы и оплаты заказов.",
  "groups": {
    "crm": {"label": "CRM, вне модуля", "ramp": "gray", "outside": true},
    "shop": {"label": "заказы", "ramp": "teal"},
    "pay": {"label": "оплаты", "ramp": "purple"}
  },
  "tables": [
    {"id": "customers", "name": "customers", "group": "crm", "subtitle": "клиенты",
     "columns": [{"name": "id", "type": "uuid", "flags": ["PK"], "key": "user"},
                 {"name": "email", "type": "text", "flags": ["U"], "key": "id"},
                 {"name": "created_at", "type": "timestamptz"}],
     "notes": ["источник правды в CRM"]},
    {"id": "orders", "name": "orders", "group": "shop", "subtitle": "заказы",
     "columns": [{"name": "id", "type": "uuid", "flags": ["PK"], "key": "key"},
                 {"name": "customer_id", "type": "uuid", "flags": ["FK"], "key": "user"},
                 {"name": "total", "type": "numeric"},
                 {"name": "status", "type": "text"}],
     "details": ["<code>status</code>: new · paid · cancelled"]},
    {"id": "payments", "name": "payments", "group": "pay", "subtitle": "оплаты",
     "columns": [{"name": "id", "type": "uuid", "flags": ["PK"], "key": "key"},
                 {"name": "order_id", "type": "uuid", "flags": ["FK"], "key": "link"},
                 {"name": "status", "type": "text"}],
     "notes": ["одна успешная оплата на заказ"]}
  ],
  "grid": ["customers  orders  payments"],
  "edges": [
    "orders.customer_id -> customers.id",
    "payments.order_id -> orders.id"
  ]
}
```

```bash
mkdir -p plugins/drawing-diagrams/skills/drawing-diagrams/examples/full
git mv plugins/drawing-diagrams/skills/drawing-diagrams/examples/kyc-module.json plugins/drawing-diagrams/skills/drawing-diagrams/examples/full/kyc-module.json
python3 plugins/drawing-diagrams/skills/drawing-diagrams/render.py plugins/drawing-diagrams/skills/drawing-diagrams/examples/schema-small.json --check
wc -c plugins/drawing-diagrams/skills/drawing-diagrams/examples/schema-small.json
```

Expected: the map on stdout, `ок: вид schema, 3 узлов, 2 связей, 0 предупреждений` on stderr, no `предупреждение` lines, size at most 3000.

- [ ] **Step 3: Move `design.md` and record the decision**

```bash
git mv plugins/drawing-diagrams/skills/drawing-diagrams/design.md plugins/drawing-diagrams/docs/design.md
```

In `plugins/drawing-diagrams/docs/design.md` replace `agent how to use what is built, reference/model.md documents the model.` with `agent how to use what is built, the files under reference/ document the model.`, then append:

```markdown

## 13. Token cost (amendment, 2026-09-17)

Spec: `docs/specs/2026-09-17-token-cost-design.md`. Decided after measuring local transcripts: a chat
widget was about 70% CSS and JS, the model trimmed them by hand on every iteration, and most failed
renders were texts that did not fit.

- Assets are fragments under `template/css` and `template/js`. A page carries all of them inline. A
  chat widget links to the build in `template/dist`, served by jsDelivr at the commit in
  `template/dist/REF`; `--assets inline` carries only the fragments the diagram uses, `none` nothing.
- Release of the build: `tools/assets.py build` and `check`, commit, the SHA of that commit into
  `REF`, commit, merge with a merge commit, then `tools/assets.py verify-cdn`.
- Every render checks the model; on errors stdout is empty, text-fit messages name the length and the
  budget, and the map is printed for layout errors only. Several models render in one call with
  `--out-dir`, all or nothing.
- The reference is split by kind (`common`, `schema`, `flow`, `timeline`, `output`) with a field table
  per kind; this file lives outside the skill directory.
- Skill-level effort and a delegated agent are decided by the experiment of the spec (§6); the outcome
  is recorded below.
```

- [ ] **Step 4: Check references across the plugin**

Run: `rg -n 'reference/model\.md|examples/kyc-module|skills/drawing-diagrams/design\.md' plugins/drawing-diagrams --glob '!docs/specs/**' --glob '!docs/plans/**'`
Expected: matches only in `SKILL/SKILL.md` (Task 8 rewrites it).

Run: `cd plugins/drawing-diagrams && python3 -m unittest discover -s tests -v`
Expected: all tests OK (`test_cdn_fragments_of_the_examples` finds `kyc-module.json` under `examples/full/`).

- [ ] **Step 5: Commit**

```bash
claude plugin validate plugins/drawing-diagrams
git add -A plugins/drawing-diagrams
git commit -m "docs(drawing-diagrams): reference split by kind with field tables, small schema sample, design.md moved

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: `SKILL.md`

Spec: §5.5, criterion 10.

**Files:**
- Modify: `SKILL/SKILL.md` (whole file)

**Interfaces:**
- Consumes: CLI of Task 5; reference and example names of Task 7.

- [ ] **Step 1: Replace `SKILL.md`**

```markdown
---
name: drawing-diagrams
description: Use when asked to draw, show, or review a database schema or ERD, a flowchart or algorithm with decisions, a swimlane of steps by participant, a lifecycle or state machine, a timeline of moments, a composition of blocks, or "what is stored where", for a design doc, chat widget, or HTML artifact; and when an existing diagram (mermaid, any auto-layout ERD or flowchart) came out too small, cramped, or with lines through boxes.
---

# Drawing diagrams

## Overview

A diagram stops being readable the moment an auto-layout engine picks the font size to fit the graph into the container. This skill fixes the font and lets the page grow: nodes are HTML cards on an explicit grid, connectors are an SVG overlay computed from the cards' real geometry, and `render.py` routes lines through the gutters and refuses layouts that would cross a node or truncate text. One core, six kinds: `schema`, `flow`, `swimlane`, `state`, `blocks`, `timeline`.

Core principle: you write a small JSON model (content, a grid map, edges); every visual decision belongs to the renderer. Do not hand-write the HTML, CSS or connector code, and do not use mermaid for the diagram itself.

## When to use

- Any request for an ERD, table map, "какие таблицы", "что где хранится"
- Any request for a flowchart, algorithm, decision tree, "как работает правило", "по шагам"
- A sequence of steps across participants: user, graph, resolver, adapter, vendor
- A lifecycle: states of a row or an attempt and what moves it between them
- A story over time: what a check, a row and an attempt looked like at t1, t2, t3
- A composition: the blocks of a design, who writes and reads each, how a check passes through them
- An auto-layout diagram that is too small, has edges through boxes or labels on lines
- A change under review: render before and after from two models

## Workflow

1. Collect the content. Schema: tables with, per column, name, type, PK/FK/U/N. Flow: steps, decisions with their branches, outcomes. Swimlane: steps in time order with the participant of each. State: states and transitions with their reasons. Timeline: moments, what happened, the state of each entity. Blocks: parts with short facts and the numbered path through them.
2. Pick the kind and the grouping that colours cards: owner, kind of truth, subsystem, participant. At most four groups (five lanes for a swimlane).
3. Read `reference/common.md` and the file of the kind: `reference/schema.md`, `reference/flow.md` (flow, swimlane, state, blocks) or `reference/timeline.md`. A small model per kind is in `examples/`: `schema-small`, `resolver-rules`, `kyc-trace`, `verdict-row-lifecycle`, `four-blocks`, `mark-timeline`. Write the model next to the document it serves. Put nodes that connect next to each other, the main path down the first column, branches to the right.
4. Render with one command; it checks the model first:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/render.py model.json --mode widget
   ```

   On errors stdout is empty and stderr lists every problem: a text that does not fit names its length and how many characters fit; a line or grid problem also prints the map. Fix all of them in one edit and render again. Treat warnings as errors unless the user accepts the trade-off.
5. Embed. Chat: pass stdout to `show_widget` unchanged. Page: `--mode page --out file.html`, or `--out-dir DIR` for several models; `--assets none` for every diagram after the first on the same page. Markdown in a repository: `--format mermaid`.
6. Look at the result outside the chat only when asked or for a new layout: `reference/output.md`.

## Cost

Every tool call re-reads the whole conversation, and every widget stays in it.

1. Show in chat only the diagrams that changed; check intermediate states by the renderer's messages, not by widgets.
2. Keep models next to the document they serve, not in a temporary directory; change them with Edit, never by rewriting the whole file or by patch scripts.
3. One shell call per iteration: for pages, several models in one `--out-dir` call; for chat, every changed widget rendered in the same shell call.
4. Pass the fragment unchanged; never trim its CSS or JS. A widget loads them from jsDelivr; if its cards show without styles or lines, render again with `--assets inline`.
5. Do not read `render.py`, `diagrams/` or `template/`. If the reference lacks something, say so.

## Rules the renderer enforces

- Widget: 680 px; up to 3 columns for a schema, 4 for a flow, 5 lanes; 16 nodes. Page: 1100 px; 4 / 6 / 7 columns; 30 nodes. A title fits one line, text two lines.
- Schema lines attach to key rows; flow lines run through the gutters, never through a node.
- A branch label is at most three words; anything longer is a footnote `[n]`. A decision has at least two labelled exits.

## Common mistakes

| Mistake | What happened | Do instead |
|---|---|---|
| Mermaid because it is quick | Graph scaled to fit 680 px: 6–8 px fonts, edges through boxes; the owner rejected it | Model + `render.py`; mermaid only as `--format mermaid` for markdown |
| Hand-written cards and SVG | 30 KB of fresh CSS/JS every time, text down to 9 px, nothing validated | Model + `render.py` |
| Trimming the widget's CSS/JS by hand | A script and a copy of the fragment paid on every iteration | Pass stdout unchanged |
| Patch scripts for the model | A script per change, the JSON rewritten, extra calls | Edit the model file |
| Reading renderer sources | 25–100K characters of code in the conversation | The reference; say what it lacks |
| Showing unchanged diagrams again | Every widget stays in the context | Show only what changed |
| A line to every table with `connection_id` or `tenant_id` | Parallel dashed lines merge into one bundle | Grey hub, `outside: true`, a note in the card |
| Different colour per node | Colour must encode a category | Group by owner, kind of truth, participant |
| Long labels on lines | They collide with lines and nodes | Short label at the exit, the rest in `footnotes` |
| A node far from what it connects to | Long routes, crossings | Move the node; the map shows it |

## Files

- `render.py` — the renderer
- `reference/` — `common.md`, one file per kind, `output.md`
- `examples/` — one small model per kind
```

- [ ] **Step 2: Check size and content**

Run:

```bash
f=plugins/drawing-diagrams/skills/drawing-diagrams/SKILL.md
wc -c "$f"
rg -c -e '--check' -e 'design\.md' -e 'model\.md' "$f"
rg -n -e '^## Cost' -e 'render.py model.json --mode widget' "$f"
```

Expected: size at most 6700; the `rg -c` line prints nothing (no `--check`, `design.md` or `model.md`); two matching lines for the last command. If the size is over 6700, shorten the Overview paragraphs, never a Cost rule.

- [ ] **Step 3: Commit**

```bash
claude plugin validate plugins/drawing-diagrams
git add plugins/drawing-diagrams/skills/drawing-diagrams/SKILL.md
git commit -m "docs(drawing-diagrams): SKILL.md with one-command rendering and cost rules

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Release commits for `template/dist` (controller)

Spec: §3.4 steps 1–3; criterion 1. Steps 4–5 of §3.4 are the owner's (push, pull request, merge commit, `verify-cdn`).

**Files:**
- Modify: `SKILL/template/dist/dg.css`, `dg.js` (only if a later task changed the sources)
- Create: `SKILL/template/dist/REF`

- [ ] **Step 1: Rebuild and commit the build if it changed**

```bash
python3 plugins/drawing-diagrams/tools/assets.py build
git add plugins/drawing-diagrams/skills/drawing-diagrams/template/dist/dg.css plugins/drawing-diagrams/skills/drawing-diagrams/template/dist/dg.js
git diff --cached --quiet || git commit -m "build(drawing-diagrams): template/dist from the current sources

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
python3 plugins/drawing-diagrams/tools/assets.py check; echo "check exit=$?"
```

Expected: `check exit=0`.

- [ ] **Step 2: Pin `REF` to the last commit that changed the build**

```bash
d=plugins/drawing-diagrams/skills/drawing-diagrams/template/dist
git log -1 --format=%H -- "$d/dg.css" "$d/dg.js" > "$d/REF"
cat "$d/REF"; wc -c < "$d/REF"
git add "$d/REF"
git commit -m "build(drawing-diagrams): pin template/dist/REF

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

Expected: a 40-character SHA and `41` (with the newline).

- [ ] **Step 3: Confirm widget output uses the pin**

Run: `python3 plugins/drawing-diagrams/skills/drawing-diagrams/render.py plugins/drawing-diagrams/skills/drawing-diagrams/examples/resolver-rules.json | head -c 220; echo`
Expected: starts with `<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/chelout/plugins-marketplace@<the SHA of Step 2>/`.

- [ ] **Step 4: Hand over publication**

Tell the owner in the session: the branch is ready to push, with a pull request description carrying the criterion 9 checklist (every `model.md` section and the new file it went to, and the file sizes Task 7 Step 1 printed); the pull request must be merged with a merge commit; after the merge run `python3 plugins/drawing-diagrams/tools/assets.py verify-cdn` (it needs the commit to be on GitHub). Do not push without the owner's word.

---

### Task 10: Experiment harness (controller)

Spec: §6 Harness, Tasks, Metrics, Automatic gate; §10 Q3.

**Files:** nothing committed. Everything under `.experiments/` at the repository root (excluded in Task 6 Step 1) and the detached worktree `.worktrees/v0`.

**Interfaces:**
- Consumes: `tools/transcripts.py` (`run_metrics`, `agents --out`) from Task 1; `render.py --check` from Task 5.
- Produces: `.experiments/run.sh VARIANT TASK N` (one headless run, then scoring), `.experiments/score.py RUN_DIR TASK VARIANT` (appends a JSON line to `.experiments/results.jsonl`), `.experiments/report.py` (writes `.experiments/report.md`), briefs `.experiments/briefs/T1.md`…`T4.md` with `T*.expected.json`, variants `.experiments/variants/v1`, `v2`, `v3`.

All commands below start with these variables in the shell:

```bash
ROOT=$(cd "$(git rev-parse --git-common-dir)/.." && pwd)
EXP="$ROOT/.experiments"
BRANCH="$ROOT/.worktrees/drawing-diagrams-token-cost"
```

- [ ] **Step 1: V0 worktree and variants**

```bash
[ -d "$ROOT/.worktrees/v0" ] || git -C "$ROOT" worktree add --detach "$ROOT/.worktrees/v0" 6f4674a
mkdir -p "$EXP/variants" "$EXP/briefs/raw" "$EXP/runs"
rm -rf "$EXP/variants/v1" "$EXP/variants/v2" "$EXP/variants/v3"
cp -R "$BRANCH/plugins/drawing-diagrams" "$EXP/variants/v1"
cp -R "$EXP/variants/v1" "$EXP/variants/v2"
cp -R "$EXP/variants/v1" "$EXP/variants/v3"
python3 - "$EXP" <<'EOF'
import sys
from pathlib import Path
exp = Path(sys.argv[1])
for variant, level in (("v2", "high"), ("v3", "medium")):
    skill = exp / "variants" / variant / "skills" / "drawing-diagrams" / "SKILL.md"
    text = skill.read_text()
    assert text.count("name: drawing-diagrams\n") == 1
    skill.write_text(text.replace("name: drawing-diagrams\n", f"name: drawing-diagrams\neffort: {level}\n"))
    print(variant, skill.read_text().splitlines()[1:3])
EOF
printf '%s\n' '{"enabledPlugins":{"drawing-diagrams@chelout-plugins":false}}' > "$EXP/settings.json"
```

Expected: `v2 ['name: drawing-diagrams', 'effort: high']` and `v3 ['name: drawing-diagrams', 'effort: medium']`.

- [ ] **Step 2: Verify that a run loads only the variant**

```bash
cd "$EXP" && claude -p "Invoke the skill drawing-diagrams with the Skill tool and reply with the line of its output that starts with 'Base directory', nothing else." \
  --model claude-opus-5 --effort low --plugin-dir "$EXP/variants/v1" --settings "$EXP/settings.json" --allowedTools Skill
```

Expected: one line containing `.experiments/variants/v1/skills/drawing-diagrams`. If it names `plugins/cache/chelout-plugins` instead, the per-run setting does not disable the installed plugin: state in the session that the installed plugin is being disabled for the experiment (owner's permission Q3), run `claude plugin disable drawing-diagrams@chelout-plugins`, repeat this step, and record in `$EXP/NOTES.md` that Task 14 must run `claude plugin enable drawing-diagrams@chelout-plugins`.

- [ ] **Step 3: Extract the 2026-09-11/12 briefs**

```bash
python3 "$BRANCH/plugins/drawing-diagrams/tools/transcripts.py" agents --out "$EXP/analytics" > /dev/null
python3 - "$EXP" <<'EOF'
import json, sys
from pathlib import Path
exp = Path(sys.argv[1])
agents = json.loads((exp / "analytics" / "agents.json").read_text())
wanted = {"T1": "GREEN: schema with the skill", "T2": "Step 2 test: flow and swimlane via skill",
          "T3": "Step 3 test: state and timeline via skill"}
for task, desc in wanted.items():
    row = next(a for a in agents if a["dispatch"]["description"] == desc)
    prompt = None
    for line in open(row["dispatch"]["file"], errors="ignore"):
        if desc not in line or '"name":"Agent"' not in line:
            continue
        for b in json.loads(line)["message"]["content"]:
            if isinstance(b, dict) and b.get("type") == "tool_use" and (b.get("input") or {}).get("description") == desc:
                prompt = b["input"]["prompt"]
    assert prompt, desc
    (exp / "briefs" / "raw" / f"{task}.md").write_text(prompt)
    print(task, len(prompt))
EOF
```

Expected: three lines `T1 1473`, `T2 1724`, `T3 1782`.

- [ ] **Step 4: Normalise the briefs**

```bash
python3 - "$EXP" <<'EOF'
import re, sys
from pathlib import Path
exp = Path(sys.argv[1])
report = "В финальном отчёте: точные команды рендерера и что вывела проверка."
for task in ("T1", "T2", "T3"):
    text = (exp / "briefs" / "raw" / f"{task}.md").read_text()
    text, n = re.subn(r"/private/tmp/\S+?/skill-test/run-[a-z]/", "{RUN_DIR}/", text)
    assert n >= 1, task
    text = text.replace(" (создай каталог run-b)", "").replace(" (создай)", "")
    text = re.sub(r"Используй скилл drawing-db-schemas \([^)]*\)\.", "Используй скилл drawing-diagrams.", text)
    if "Используй скилл drawing-diagrams." not in text:
        text = text.replace("Не спрашивай уточнений", "Используй скилл drawing-diagrams. Не спрашивай уточнений", 1)
    text = re.sub(r"\n\nВ финальном отчёте:.*\Z", "\n\n" + report, text, flags=re.S)
    assert text.count("Используй скилл drawing-diagrams.") == 1 and text.endswith(report), task
    (exp / "briefs" / f"{task}.md").write_text(text + "\n")
    print(task, "ok")
EOF
cat > "$EXP/briefs/T4.md" <<'EOF'
В каталоге {RUN_DIR} лежит модель resolver-rules.json. Внеси три правки и перерендерь схему для показа в чате шириной 680 px в {RUN_DIR}/resolver-rules.html:
1) у узла pick заголовок «Фильтры профилей»;
2) между one? и fire добавь шаг log с заголовком «Запись решения»: связь one? -> log с подписью «да» вместо one? -> fire, затем log -> fire; добавь log в сценарий «Кира: fire» между one? и fire;
3) у узла covered? текст «строка содержит всё».
Используй скилл drawing-diagrams. Не спрашивай уточнений.

В финальном отчёте: точные команды рендерера и что вывела проверка.
EOF
```

Expected: `T1 ok`, `T2 ok`, `T3 ok`. Read the three briefs once: every output path starts with `{RUN_DIR}/`.

- [ ] **Step 5: Expected content per task**

Write `$EXP/briefs/T1.expected.json` … `T4.expected.json` in this shape:

```json
{"models": ["model.json"], "outputs": ["schema.html"], "must_contain": ["<item>", "<item>"]}
```

- T1: `models` `["model.json"]`, `outputs` `["schema.html"]`, `must_contain` = the six table names listed in the T1 brief.
- T2: `models` `["resume.json", "webhook.json"]`, `outputs` `["resume.html", "webhook.html"]`, `must_contain` = the four re-entry outcomes named in scheme A (`approved`, `declined_retry`, `declined_final` and the expiry word used in the brief) and the five participants listed in scheme B.
- T3: `models` `["attempt.json", "kira.json"]`, `outputs` `["attempt.html", "kira.html"]`, `must_contain` = the five attempt states listed in scheme A.
- T4: `{"models": ["resolver-rules.json"], "outputs": ["resolver-rules.html"], "must_contain": ["Фильтры профилей", "\"log\"", "Запись решения", "строка содержит всё"]}`.

- [ ] **Step 6: Runner, scorer and report**

`$EXP/run.sh`:

```bash
#!/usr/bin/env bash
# Usage: run.sh VARIANT TASK N   (VARIANT: v0 v1 v2 v3 v4; N tells repeated runs apart)
# Needs SOURCE_REPO: the repository the T1–T3 briefs name.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
EXP="$ROOT/.experiments"
variant=$1 task=$2 n=$3
case "$variant" in
  v0) plugin="$ROOT/.worktrees/v0/plugins/drawing-diagrams" ;;
  *) plugin="$EXP/variants/$variant" ;;
esac
run_dir="$EXP/runs/$task-$variant-$n"
rm -rf "$run_dir" && mkdir -p "$run_dir"
if [ "$task" = T4 ]; then
  cp "$ROOT/.worktrees/v0/plugins/drawing-diagrams/skills/drawing-diagrams/examples/resolver-rules.json" "$run_dir/"
fi
sid=$(python3 -c 'import uuid; print(uuid.uuid4())')
echo "$sid" > "$run_dir/session_id"
brief=$(sed "s#{RUN_DIR}#$run_dir#g" "$EXP/briefs/$task.md")
(cd "$run_dir" && claude -p "$brief" --model claude-opus-5 --effort xhigh --plugin-dir "$plugin" \
  --settings "$EXP/settings.json" --session-id "$sid" --add-dir "$SOURCE_REPO" \
  --allowedTools "Bash Read Write Edit Glob Grep Skill Agent" --output-format json > "$run_dir/result.json")
python3 "$EXP/score.py" "$run_dir" "$task" "$variant"
```

`$EXP/score.py`:

```python
#!/usr/bin/env python3
"""Score one run: token metrics of the session and its agents, output size, automatic gate.
Usage: score.py RUN_DIR TASK VARIANT. Appends one JSON line to results.jsonl."""
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
PLUGIN = EXP.parent / ".worktrees" / "drawing-diagrams-token-cost" / "plugins" / "drawing-diagrams"
sys.path.insert(0, str(PLUGIN / "tools"))
import transcripts  # noqa: E402

RENDER = PLUGIN / "skills" / "drawing-diagrams" / "render.py"
run_dir, task, variant = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
sid = (run_dir / "session_id").read_text().strip()
session = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))[0]
m = transcripts.run_metrics(session)
expected = json.loads((EXP / "briefs" / f"{task}.expected.json").read_text())

gate, crossings, texts = [], 0, []
for name in expected["models"]:
    path = run_dir / name
    if not path.exists():
        gate.append(f"нет {name}")
        continue
    texts.append(path.read_text().lower())
    r = subprocess.run([sys.executable, str(RENDER), str(path), "--check"], capture_output=True, text=True)
    if r.returncode != 0:
        gate.append(f"{name}: проверка не пройдена")
    if "предупреждение" in r.stderr:
        gate.append(f"{name}: есть предупреждения")
    found = re.search(r"пересечений линий: (\d+)", r.stdout)
    crossings += int(found.group(1)) if found else 0
missing = [s for s in expected["must_contain"] if s.lower() not in "".join(texts)]
if missing:
    gate.append("нет в моделях: " + ", ".join(missing))
outputs = [run_dir / n for n in expected["outputs"]]
gate += [f"нет {p.name}" for p in outputs if not p.exists()]

row = {"task": task, "variant": variant, "run": run_dir.name,
       **{k: m[k] for k in ("calls", "agents", "out", "think", "cw", "cr", "in", "peak_ctx", "renders", "renders_failed")},
       "efforts": dict(m["efforts"]), "models": dict(m["models"]),
       "output_bytes": sum(p.stat().st_size for p in outputs if p.exists()), "crossings": crossings,
       "gate": gate or "ok"}
with open(EXP / "results.jsonl", "a") as fh:
    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
print(json.dumps(row, ensure_ascii=False))
```

`$EXP/report.py`:

```python
#!/usr/bin/env python3
"""report.md from results.jsonl: every run of a task next to its V0 run, deltas in percent."""
import collections
import json
from pathlib import Path

EXP = Path(__file__).resolve().parent
rows = [json.loads(l) for l in (EXP / "results.jsonl").read_text().splitlines() if l.strip()]
cols = ("calls", "out", "think", "cw", "cr", "peak_ctx", "output_bytes", "renders_failed", "crossings")
by_task = collections.defaultdict(list)
for r in rows:
    by_task[r["task"]].append(r)
lines = []
for task in sorted(by_task):
    runs = sorted(by_task[task], key=lambda r: (r["variant"], r["run"]))
    base = next((r for r in runs if r["variant"] == "v0"), None)
    lines += [f"## {task}", "", "| run | " + " | ".join(cols) + " | effort | gate |", "|---" * (len(cols) + 3) + "|"]
    for r in runs:
        cells = [f"{r[c]} ({100 * (r[c] - base[c]) / base[c]:+.0f}%)" if base and r is not base and base[c] else str(r[c])
                 for c in cols]
        gate = "ok" if r["gate"] == "ok" else "; ".join(r["gate"])
        if base and r is not base and r["crossings"] > base["crossings"]:
            gate = ("" if gate == "ok" else gate + "; ") + "пересечений больше, чем у V0"
        lines.append(f"| {r['run']} | " + " | ".join(cells) + f" | {r['efforts']} | {gate} |")
    lines.append("")
(EXP / "report.md").write_text("\n".join(lines))
print("\n".join(lines))
```

```bash
chmod +x "$EXP/run.sh" "$EXP/score.py" "$EXP/report.py"
bash -n "$EXP/run.sh" && python3 -m py_compile "$EXP/score.py" "$EXP/report.py" && echo harness-ok
```

Expected: `harness-ok`.

---

### Task 11: Stage 1 — V0 and V1 on T1–T4 (controller)

Spec: §6 Stages 1, metrics, gate; Stream slots "Performance budget".

**Files:** `.experiments/runs/*`, `results.jsonl`, `report.md`; `plugins/drawing-diagrams/docs/specs/2026-09-17-token-cost-design.md` (budget line).

The deciding metric of this stage is `out` (output tokens, thinking included).

- [ ] **Step 1: Run the eight cells**

```bash
export SOURCE_REPO=<absolute path of the repository the T1–T3 briefs name>
for task in T1 T2 T3 T4; do for v in v0 v1; do "$EXP/run.sh" "$v" "$task" 1; done; done
python3 "$EXP/report.py"
```

Expected: eight JSON lines, then four tables in `report.md`.

- [ ] **Step 2: Apply the gate**

Stage 1 gives a result when every `v1` row has gate `ok` and no "пересечений больше, чем у V0". If a `v1` row fails, stop the experiment: report the failing task and gate message in the session; fixing it is new implementation work, not part of this plan.

- [ ] **Step 3: Apply the 15% rule**

For each task where `out` of `v1` is within 15% of `v0`, run both once more (`run.sh v0 T? 2`, `run.sh v1 T? 2`) and regenerate the report; compare the means of the two runs.

- [ ] **Step 4: Record the performance budget**

In the spec's Stream slots replace the Performance budget sentence with `**Performance budget:** per task, \`out\` and \`cr\` of a later change stay at or below the stage 1 V1 values: T1 <out>/<cr>, T2 <out>/<cr>, T3 <out>/<cr>, T4 <out>/<cr> (report of <date>).` filled from `report.md`, then:

```bash
git -C "$BRANCH" add plugins/drawing-diagrams/docs/specs/2026-09-17-token-cost-design.md
git -C "$BRANCH" commit -m "docs(drawing-diagrams): performance budget from stage 1

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Tell the owner**

Post the four stage 1 tables in the session with one line per task on `out`, `cr` and `output_bytes` against V0.

---

### Task 12: Stage 2 — V2 and V3 on T2 and T4 (controller)

Spec: §6 Stages 2. Runs after Task 11 gave a result. The deciding metric is `out`.

- [ ] **Step 1: Run the four cells**

```bash
for task in T2 T4; do for v in v2 v3; do "$EXP/run.sh" "$v" "$task" 1; done; done
python3 "$EXP/report.py"
```

- [ ] **Step 2: Check that the effort applied**

In each `v2` row `efforts` must include `high`, in each `v3` row `medium`. A variant whose rows show only `xhigh` did not apply the frontmatter; it cannot win, and the session report says so.

- [ ] **Step 3: Decide the stage**

For T2 and T4 compare `v2` and `v3` with the stage 1 `v1` run of the same task. Apply the 15% rule against `v1` (re-run the variant and `v1` with N=2). The stage winner is the variant with gate `ok` on both tasks, applied effort, and mean `out` at least 15% below `v1` on both; if both qualify, the lower mean `out` wins. Otherwise there is no effort winner. Write the result as one line into `$EXP/NOTES.md`: `stage 2: winner v2|v3|none`.

---

### Task 13: Stage 3 — V4 delegated agent on T1 and T4 (controller)

Spec: §6 Stages 3, Outcome. Runs after Task 12 finished. The deciding metric is `cr` (cache read of the session and its agent together).

- [ ] **Step 1: Build the V4 variant**

```bash
rm -rf "$EXP/variants/v4" && cp -R "$EXP/variants/v1" "$EXP/variants/v4"
mkdir -p "$EXP/variants/v4/agents"
```

Set `LEVEL` to the effort of the stage 2 winner (`high` for v2, `medium` for v3), or `high` when there was no winner, and write `$EXP/variants/v4/agents/diagram-renderer.md`:

```markdown
---
name: diagram-renderer
description: Writes or edits a drawing-diagrams model and renders it until the check passes. Dispatched by the drawing-diagrams skill with the content or the change, the model path, the mode and the output path.
model: sonnet
effort: LEVEL
tools: Read, Write, Edit, Glob, Grep, Bash, Skill
---

Load the skill `drawing-diagrams:drawing-diagrams` with the Skill tool first and follow it. Write or edit the model at the path in the brief, render it with the mode and the output path from the brief, and fix every error the renderer reports. Do not show widgets. Reply with the output paths and the renderer's final messages, nothing else.
```

Replace `LEVEL` with the chosen level. In `$EXP/variants/v4/skills/drawing-diagrams/SKILL.md` insert before `## Cost`:

```markdown
## Delegation

Do not write, edit or render models yourself. Dispatch the `drawing-diagrams:diagram-renderer` agent with the content to draw or the change to make (with the file paths it needs), the model path, the mode and the output path. When it returns, report or show the output file it names.

```

- [ ] **Step 2: Run the two cells**

```bash
for task in T1 T4; do "$EXP/run.sh" v4 "$task" 1; done
python3 "$EXP/report.py"
```

Expected: each `v4` row has `agents` ≥ 1 and `models` containing a `sonnet` model; otherwise delegation did not happen, and the session report says so.

- [ ] **Step 3: Compare, converting to cost when token kinds disagree**

Compare `v4` with stage 1 `v1` on T1 and T4, applying the 15% rule on `cr`. If `v4` is lower on `cr` but higher on `out` or `cw` (or the other way round), load the `claude-api` skill for current per-model prices and compute each run's cost per model:

```bash
python3 - "$EXP" <<'EOF'
import collections, glob, json, os, sys
from pathlib import Path
exp = Path(sys.argv[1])
sys.path.insert(0, str(exp.parent / ".worktrees/drawing-diagrams-token-cost/plugins/drawing-diagrams/tools"))
import transcripts
for run in sorted((exp / "runs").glob("T[14]-v[14]-*")):
    sid = (run / "session_id").read_text().strip()
    session = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))[0]
    per = collections.defaultdict(collections.Counter)
    for f in transcripts.run_files(session):
        for c in transcripts.api_calls(f):
            per[c["model"]].update({k: c[k] for k in ("in", "cw", "cr", "out")})
    print(run.name, {m: dict(v) for m, v in per.items()})
EOF
```

Multiply each model's `in`, `cw`, `cr`, `out` by that model's prices from the skill and sum per run.

- [ ] **Step 4: Decide the stage**

`v4` wins when its gate is `ok` on both tasks and it is cheaper than `v1` on both: by at least 15% on `cr` when token kinds agree, by at least 15% in cost when Step 3 converted. Write `stage 3: winner v4|none` into `$EXP/NOTES.md`.

---

### Task 14: Owner review, decision, outcome, cleanup (controller)

Spec: §6 Owner review, Decision, Outcome; criteria 11 and 13.

**Files:**
- Modify (by outcome): `SKILL/SKILL.md`; create `plugins/drawing-diagrams/agents/diagram-renderer.md`
- Modify: `plugins/drawing-diagrams/docs/design.md` (§13 outcome)

- [ ] **Step 1: Build the side-by-side page**

```bash
python3 - "$EXP" <<'EOF'
import json, subprocess, sys
from pathlib import Path
exp = Path(sys.argv[1])
render = exp.parent / ".worktrees/drawing-diagrams-token-cost/plugins/drawing-diagrams/skills/drawing-diagrams/render.py"
rows = [json.loads(l) for l in (exp / "results.jsonl").read_text().splitlines() if l.strip()]
review = exp / "review"
review.mkdir(exist_ok=True)
cells = []
for task in sorted({r["task"] for r in rows}):
    base = next(r for r in rows if r["task"] == task and r["variant"] == "v0")
    for cand in [r for r in rows if r["task"] == task and r["variant"] != "v0" and r["gate"] == "ok"]:
        expected = json.loads((exp / "briefs" / f"{task}.expected.json").read_text())
        for model in expected["models"]:
            pair = []
            for r in (base, cand):
                out = review / r["run"] / model.replace(".json", ".html")
                out.parent.mkdir(exist_ok=True)
                subprocess.run([sys.executable, str(render), str(exp / "runs" / r["run"] / model), "--mode", "page",
                                "--assets", "inline", "--out", str(out)], check=False)
                pair.append(f'<td><iframe src="{r["run"]}/{out.name}" style="width:1120px;height:900px;border:1px solid #ccc"></iframe></td>')
            cells.append(f'<tr><th colspan="2">{task} · {model}: {base["run"]} | {cand["run"]}</th></tr><tr>{"".join(pair)}</tr>')
(review / "index.html").write_text("<table>" + "".join(cells) + "</table>")
print(len(cells), "pairs")
EOF
python3 -m http.server 8770 -d "$EXP/review" >/dev/null 2>&1 & echo "server pid $!"
```

Open `http://localhost:8770/index.html` in the in-app browser and hand it to the owner together with `report.md` and the two stage lines of `NOTES.md`.

- [ ] **Step 2: Record the owner's decision**

Ask the owner which variant to keep. Write their words into `$EXP/NOTES.md` as `decision: v1|v2|v3|v4 — <owner's reason>`. If they choose V4, also ask for the condition under which the skill delegates (for example "when the conversation already showed a diagram" or "always for edits of an existing model") and record it. Stop the review server with `kill <pid>`.

- [ ] **Step 3: Apply the outcome**

- **V2 or V3:** in `SKILL/SKILL.md` replace `name: drawing-diagrams\n` with `name: drawing-diagrams\neffort: <level>\n`.
- **V4:** `mkdir -p plugins/drawing-diagrams/agents && cp "$EXP/variants/v4/agents/diagram-renderer.md" plugins/drawing-diagrams/agents/`; in `SKILL/SKILL.md` insert before `## Cost` a `## Delegation` section with the text of Task 13 Step 1, its first sentence prefixed by the recorded condition (for example `When the conversation already showed a diagram, do not write, edit or render models yourself.`). Check `wc -c` of `SKILL.md` stays at most 6700; shorten the Overview if needed.
- **V1:** no change.

- [ ] **Step 4: Record the outcome in `design.md`**

Append to §13 of `plugins/drawing-diagrams/docs/design.md` one line matching the decision:

- V1: `- Outcome of the experiment (<date>): neither skill-level effort nor delegation paid off at equal quality; the session's effort and model stay.`
- V2/V3: `- Outcome of the experiment (<date>): \`effort: <level>\` in the skill frontmatter; output tokens <n>% lower than without it at equal quality.`
- V4: `- Outcome of the experiment (<date>): the \`diagram-renderer\` agent (\`sonnet\`, \`effort: <level>\`) renders when <condition>; cache reads <n>% lower at equal quality.`

Fill `<date>`, `<level>`, `<n>` and `<condition>` from `report.md` and `NOTES.md`.

- [ ] **Step 5: Commit**

```bash
claude plugin validate plugins/drawing-diagrams
git add -A plugins/drawing-diagrams
git commit -m "feat(drawing-diagrams): apply the effort and delegation experiment outcome

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Clean up**

- If `$EXP/NOTES.md` says the installed plugin was disabled: `claude plugin enable drawing-diagrams@chelout-plugins`, and state it in the session.
- `git -C "$ROOT" worktree remove "$ROOT/.worktrees/v0"`.
- Keep `.experiments/` until the owner says to delete it.
- Deliver the stream report in the session (team-skills `stream-report.md`).
