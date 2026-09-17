# drawing-diagrams: token cost of using the skill — design

Date: 2026-09-17. Status: agreed section by section with the owner in the design session; this file
awaits the owner's review. Branch: `feat/drawing-diagrams-token-cost`.

## Stream slots

- **Path:** full cycle. `workflow.full_cycle` is not declared (the repository has no
  `.agents/team-profile.yaml`); the package default entry "a moved boundary" matches, because chat
  widgets start depending on files published from this repository and fetched through jsDelivr. The
  owner also asked for a spec. The gate judges the diff against this spec.
- **Design review before markup:** not applicable. No visual change is intended; that the look is
  unchanged is checked by the owner's pair review in §6.
- **Evidence:** named per criterion in §9. `completion.evidence_kind` is not declared, so each
  criterion names a command output, a test, or the owner's recorded word.
- **Performance budget:** set after the first end-to-end measurement (stage 1, variant V0 in §6) as
  token numbers per task; not set ahead of it.
- **Decision record:** applies — a new asset delivery contract and a new reference layout that later
  work inherits. `decisions.dir` is not declared; per the owner (2026-09-17) the record is an
  amendment section in `plugins/drawing-diagrams/docs/design.md`, where §5.4 moves that file.
- **Integration:** not declared in a profile. Pushing the branch and opening a pull request are done
  by the owner or on the owner's word.

## 1. Problem and measurements

Measured in the design session from local Claude Code transcripts (`~/.claude/projects`,
2026-07-21 … 2026-09-16). Numbers are tokens unless characters are stated.

- A skill widget as actually sent to `show_widget` (40 widgets, session of 2026-09-13…16): median
  14.2K characters — CSS 4.1K, JS 5.9K, edge JSON 0.7K, diagram markup 2.9K. About 70% is renderer
  assets that are the same for every diagram.
- `render.py --mode widget` emits 27–43K characters for the six examples: CSS 13.2K, because all nine
  ramps are always emitted (`diagrams/assets.py:27-31`), and JS 9.9–11.6K (`template/core.js` plus
  edges).
- Because of that size the model trimmed assets by hand in every iteration: a Python script that
  edits the model, renders, cuts `<style>`/`<script>` and writes `*.slim.html`, then `cat` of
  18–22K characters, then `show_widget`. The script and the widget are paid as output, the read as
  input, and all of it stays in the context.
- About 8K output tokens per widget; widgets were 42% and 53% of all output in two sessions
  (326K of 784K; 55.6K of 104K).
- Every call re-reads the whole context: 0.4–0.95M per call in a long session; one diagram iteration
  (median 8 calls) re-read about 4.2M.
- 37% of `render.py` commands in sessions failed, nearly all on text fit: node text over two lines
  (~25), title wider than the card (~11), edge label does not fit (~13). Only the edge label message
  names a budget in characters (`diagrams/flow.py:453-454`); the title, text, item and key row
  messages give pixels or nothing (`diagrams/flow.py:286`, `:301`, `:309`, `diagrams/schema.py:102`,
  `diagrams/timeline.py:69-72`).
- `reference/model.md` (20.5K characters) was read in 9 of 10 episodes. The schema sample
  `examples/kyc-module.json` is 13K characters (6.5–7.5K tokens measured). In one ordinary update
  the model also read `design.md` and `diagrams/flow.py` to find the node rules.
- Thinking at `xhigh` is 50–67% of the skill's output.

## 2. Goals and non-goals

Goals:

- **G1.** Cut output and context growth per diagram shown in chat, keeping every interaction a
  diagram has today (hover highlight, scenario chips, column toggles, dark theme).
- **G2.** Cut tool calls and failed renders per iteration.
- **G3.** Cut what the model reads to draw a diagram.
- **G4.** Decide by measurement whether a skill-level `effort` or a delegated agent on `sonnet` is
  cheaper at equal quality.

Non-goals:

- No binding to Artifacts: page output stays self-contained HTML usable in any host.
- No script-free chat widget: the owner needs the same interactivity in chat as on a page.
- No change to how diagrams look.
- No build in GitHub Actions and no npm package (§7).

## 3. Asset delivery

### 3.1 Built assets in the repository

- `template/dist/dg.css` = `template/tokens.css` + `template/core.css` + the CSS of all nine ramps
  (`ramp_css(RAMPS)` in `diagrams/assets.py`). `template/dist/dg.js` = `template/core.js`. Both carry
  every feature: downloading costs no tokens.
- `template/dist/REF` holds the full 40-character SHA of the commit whose tree contains the current
  `dist/*`.
- `plugins/drawing-diagrams/tools/assets.py`, outside the skill directory and not mentioned in
  `SKILL.md`:
  - `build` writes `dist/dg.css` and `dist/dg.js` from the sources;
  - `check` exits non-zero when `dist/*` differs from a fresh build;
  - `verify-cdn` fetches both files from
    `https://cdn.jsdelivr.net/gh/chelout/plugins-marketplace@<REF>/plugins/drawing-diagrams/skills/drawing-diagrams/template/dist/`
    and exits non-zero unless both answer 200 and match the local `dist/*` byte for byte.

### 3.2 `--assets` modes of `render.py`

| Mode | Output | Default for |
|---|---|---|
| `cdn` | `<link rel="stylesheet">` to `dg.css` first, then the `<section class="dg">` markup with its edge JSON, then `<script src>` to `dg.js` last; both URLs pinned to `REF` | `--mode widget` |
| `inline` | assets inside the output: pruned to the diagram in widget mode (§3.3), the full set in page mode as today | `--mode page` |
| `none` | markup only | none; `--no-assets` stays as an alias |

- `cdn` without `template/dist/REF` falls back to `inline` and prints a warning.
- Order: widget scripts run after streaming, while a stylesheet link applies during streaming, so
  cards are styled early. Verified on 2026-09-17 in the desktop app: a widget loading
  `template/core.css` and `template/core.js` from jsDelivr at commit `6f4674a` loaded both, ran the
  script (`window.__dgInit` set) and applied styles inserted by a script.
- Page mode stays inline because the Artifact CSP allows jsDelivr only under `/npm/` (Artifact
  publishing rules of the Claude Code harness), and these files are served under `/gh/`.

### 3.3 Inline widget pruning

The deterministic version of what the model did by hand:

- CSS: tokens and base rules; the ramps used by the model's groups; feature groups only when the
  diagram has the feature — scenario chips (routes present), column toggles (`schema`), swimlane
  lanes, timeline rail, footnotes. Legend and dark theme always.
- JS: omitted when the diagram has no connectors (`timeline`; `blocks` without edges); column toggle
  code only for `schema`; scenario code only when routes are present.
- `template/core.css` and `template/core.js` are split into feature fragments under `template/` to
  allow this; `dist/*` is built from all fragments, so the CDN files stay complete.

### 3.4 Release procedure

1. Change the sources; run `tools/assets.py build` and `tools/assets.py check`.
2. Commit A: sources and the rebuilt `dist/*`.
3. Commit B: `dist/REF` set to the SHA of commit A.
4. Merge with a merge commit, never squash or rebase, so commit A stays reachable from `main`.
5. After the merge run `tools/assets.py verify-cdn`.

## 4. Render loop

Today `render.py` already refuses to render when validation fails (`render.py:72-78`), and the
checks accumulate every error of a run before raising (the `errors` and `layout_errors` lists in
`diagrams/flow.py`, `layout_errors` in `diagrams/timeline.py`). It writes HTML to stdout unless `--out` is given and
prints the ASCII map only with `--check` or `--format ascii` (`render.py:84-91`). `SKILL.md` still
tells the model to run `--check` and then render, as two commands (`SKILL.md:33-34`).

- **R1.** One command per render. `SKILL.md` drops the separate `--check` step; `--check` stays for
  when only the map is wanted.
- **R2.** Text-fit problems are: title width, node text lines, block item lines, schema key row
  width, timeline title and text, edge label room. The ASCII map is printed to stderr when the run
  has any other layout error or the crossing warning (three or more crossings); a run whose problems
  are all text-fit prints no map.
- **R3.** On success in widget mode stdout carries only the fragment, ready for `show_widget`;
  warnings and the summary go to stderr.
- **R4.** Batch: `render.py a.json b.json … --out-dir DIR` writes `DIR/<id>.html` per model (`id`
  from the model, otherwise the file stem) and prints one line per model to stdout. If any model
  fails, no file is written and the errors of all models are printed. Several models without
  `--out-dir` is an error.
- **R5.** Every text-fit message names the length and the budget in characters, computed with the
  width estimate the check already uses:
  - node text: `узел open: текст 61 симв., в две строки влезает ~48`;
  - title: `узел close: заголовок 24 симв., влезает 19`;
  - block item: `узел e: пункт 3 — 57 симв., влезает ~44`;
  - schema key row: `таблица outbox.external_correlation_id: имя 23 симв., влезает ~20`;
  - timeline title and text: the same shapes;
  - edge label: today's budget, stated in the same shape.

Not done: a separate `--budgets` pass; moving long labels into footnotes automatically (§7).

## 5. Reference and SKILL.md

### 5.1 Reference split

`reference/model.md` is replaced by:

| File | Content, by today's `reference/model.md` sections | ≈ characters |
|---|---|---|
| `reference/common.md` | intro, common top level, grid map, groups, labels, modes and flags including `--assets`, CLI usage | 3.8K |
| `reference/schema.md` | kind `schema` and its `table.column` edge syntax (today under "Edges") | 4.7K |
| `reference/flow.md` | kinds `flow`, `swimlane`, `state`, `blocks` (one engine) | 10K |
| `reference/timeline.md` | kind `timeline` | 1.3K |
| `reference/output.md` | verifying the output, exports; read only for visual checks or mermaid/ASCII | 1.3K |

Reading per diagram, before the field tables of §5.2: schema about 8.5K characters (−59%), the flow
family about 13.8K (−33%), timeline about 5.1K (−75%).

### 5.2 Field tables

Each kind file opens with one table: every field of a node, table or moment, whether it is required,
and its limit in characters per mode where a limit applies. Today these rules are spread over the
prose of `reference/model.md` and the checks in `diagrams/flow.py:262-309`.

### 5.3 Examples

- `examples/schema-small.json`, at most 3K characters, becomes the schema sample.
- `examples/kyc-module.json` moves to `examples/full/kyc-module.json` and is not offered as a
  sample.

### 5.4 design.md

`skills/drawing-diagrams/design.md` moves to `plugins/drawing-diagrams/docs/design.md`: it is the
owner's record, and `SKILL.md` stops listing it. Specs live in `plugins/drawing-diagrams/docs/specs/`.

### 5.5 SKILL.md

- The workflow follows §4: one render command; the widget fragment from stdout goes to `show_widget`
  unchanged; several changed diagrams for chat are rendered in one shell call; pages via `--out` or
  `--out-dir`; `reference/output.md` only for visual checks.
- A new "Cost" rules block:
  1. Show in chat only the diagrams that changed; check intermediate states by the renderer's
     messages, not by widgets.
  2. Keep models next to the document they serve, not in a temporary directory; change them with
     Edit, never by rewriting the whole file or by patch scripts.
  3. One shell call per iteration: for pages, several models in one `render.py … --out-dir` call;
     for chat, every changed widget rendered in the same shell call.
  4. Pass the fragment unchanged; never trim its CSS or JS.
  5. Do not read `render.py`, `diagrams/` or `template/`; if the reference lacks something, say so.
- The common mistakes table gains rows for hand-trimmed assets, patch scripts, reading renderer
  sources and re-showing unchanged diagrams.
- "Rules the renderer enforces" (1.2K characters today) shrinks to the constraints needed before
  writing a model; the body stays within today's 6.7K characters.

## 6. Experiment: effort and a delegated agent

Known from transcripts: the Agent tool's `model` parameter was honoured 168 of 168 times; an agent's
effort equalled the session's 274 of 274 times when its definition set none; `effort` is recorded on
every assistant record, so an applied override is observable.

| | Change | Question |
|---|---|---|
| V0 | skill at `6f4674a` | baseline on the current session model; the 2026-09-11/12 runs used another model |
| V1 | §3–§5, session effort | effect of the changes |
| V2 | V1 + `effort: high` in the `SKILL.md` frontmatter | thinking cut at equal quality |
| V3 | V1 + `effort: medium` | one step lower |
| V4 | V1 + plugin agent `diagram-renderer` (`model: sonnet`, `effort` in its definition); the main session writes the brief and shows the fragment | the loop in ~70K context instead of 0.4–1M |

**Tasks.** T1 — a database schema of six tables; T2 — flow and swimlane; T3 — state and
timeline (the briefs of 2026-09-11/12). T4 — edit an existing model: rename a node, add a step,
shorten labels.

**Harness.** Frontmatter `effort` and plugin agents apply only to a plugin Claude Code has loaded, so
each variant runs in a dedicated session with that variant installed from a temporary directory
marketplace pointing at a worktree, with `drawing-diagrams@chelout-plugins` disabled meanwhile (Q3).
All variants get the same brief.

**Stages.** A stage runs only if the previous one gave a result.

1. V0 and V1 on T1–T4 — 8 runs.
2. V2 and V3 on T2 and T4 — 4 runs.
3. V4 on T1 and T4, main session and agent counted together — 2 runs.

One run per cell; a pair within 15% of each other on the deciding metric is run once more.

**Metrics per run:** calls; output and thinking; cache write; cache read; peak context; widget
fragment characters; failed `render.py` commands; applied effort per record.

**Measurement tool:** `plugins/drawing-diagrams/tools/transcripts.py`, outside the skill directory.
It replaces the two scripts imported as-is from the design session (`tools/skill_analytics.py`,
`tools/skill_tokens.py`) with subcommands `agents` (model and effort of each dispatched agent),
`episodes` (skill episodes and their render loop) and `tokens` (usage per run or per drawing
segment). Usage is taken once per message id, from its last record, and summed over
`usage.iterations`, because a message is written as several records and some records carry zeros at
the top level. Render commands are matched under the old `skills/drawing-diagrams/` path and under
the plugin cache path.

**Automatic gate:** the final check has no errors and no warnings; crossings are not above V0 on the
same task; every table or step listed for the task is present (lists written before stage 1).

**Owner review:** variants that pass the gate are shown next to V0 on one local HTML page in page
mode, opened in the in-app browser.

**Decision:** the cheapest variant the owner approves. If variants differ on different token kinds,
they are compared at current prices obtained through the `claude-api` skill at decision time.

**Outcome in the skill:** V2 or V3 → `effort` in the frontmatter; V4 →
`plugins/drawing-diagrams/agents/diagram-renderer.md` and a `SKILL.md` rule for when to delegate,
with the threshold taken from the results; none → V1 stays.

**Cost of the experiment:** 14 runs at the 2026-09-11/12 level (about 27 calls, 35K output and 3.3M
cache read per run) are about 45M cache read and 0.5M output; likely less after §3–§5.

## 7. Rejected alternatives

- Script-free chat widget with connectors computed in Python: loses the interactivity the owner needs
  in chat.
- Routes computed in Python with a thin JS painter: a large rewrite of `diagrams/router.py` and
  `template/core.js` for a smaller gain than CDN delivery.
- Build in GitHub Actions into an `assets` branch, with `ASSETS_REF` and a source-hash guard in
  `render.py`: the owner chose the manual procedure of §3.4.
- An npm package: needs an npm account and a secret, and the files would not live in this
  repository.
- Separate reference files for `swimlane`, `state` and `blocks`: about 0.5K tokens saved for more
  files.
- A `--budgets` pre-pass and automatic footnotes: the budget in the error message gives the same on
  the first retry, and automatic footnotes would rewrite the author's text.

## 8. Risks

- **CDN unreachable or blocked:** the widget shows unstyled cards without lines. Mitigation: `SKILL.md`
  says to re-render with `--assets inline`.
- **Stale `REF`** (dist rebuilt, `REF` not updated): widget markup meets older assets. Mitigation:
  release steps 3 and 5; the risk remains if `verify-cdn` is skipped.
- **Squash or rebase merge** leaves commit A unreachable from `main`, and jsDelivr may fail to fetch
  it once the branch is deleted. Mitigation: release step 4.
- **Permanent CDN cache:** jsDelivr caches commit URLs permanently (jsDelivr README, "Caching"), so a
  wrong build cannot be fixed in place; publish a new commit and move `REF`.
- **Effort scope:** for an inline skill the docs say only that `effort` applies "when this skill is
  active"; the experiment reads the applied effort from the records.
- **Noise:** single runs vary; the 15% re-run rule reduces it, not removes it.

## 9. Done when

| # | Criterion | Evidence |
|---|---|---|
| 1 | `tools/assets.py check` exits 0 on the branch | command output |
| 2 | after the merge `tools/assets.py verify-cdn` exits 0 | command output |
| 3 | `--assets cdn` widget fragments of the six examples have a median of at most 6K characters (27–43K today; the diagram markup of the examples alone has a median of about 5K, larger than the 2.9K of the widgets measured in sessions) | size table printed by a unit test over `examples/` |
| 4 | `--assets inline` widget fragments of the six examples draw every edge and keep their interactions | harness pages in the in-app browser: no console errors, connector count equals edge count, a scenario chip and a column toggle work |
| 5 | `--assets` modes: `cdn` output has the stylesheet link first and the script last with `REF` URLs; without `REF` it falls back to `inline` with a warning; `--no-assets` equals `--assets none` | unit tests |
| 6 | a failing model gives empty stdout and exit 1; the map is printed for a non-text-fit layout error and not for text-fit errors; on success widget stdout is only the fragment | unit tests |
| 7 | every text-fit message states length and budget as in §4 R5 | unit tests over fixture models |
| 8 | a batch with one failing model writes no file and reports all errors | unit test |
| 9 | every section of today's `reference/model.md` is in exactly one new reference file; field tables exist for `schema`, the flow family and `timeline`; `examples/schema-small.json` is at most 3K characters and `examples/kyc-module.json` is under `examples/full/` | checklist in the pull request description, `wc -c` output |
| 10 | `SKILL.md` body is at most 6.7K characters, uses one render command in its workflow, contains the cost rules and no longer lists `design.md`; `design.md` is under `plugins/drawing-diagrams/docs/` | `wc -c` and `rg` output |
| 11 | the experiment report has the metric table per stage and the owner's decision | report file and the owner's recorded word |
| 12 | `tools/transcripts.py` counts each message once, sums `usage.iterations`, and prints the §6 metrics per run; the imported `skill_analytics.py` and `skill_tokens.py` are removed | unit test over a fixture transcript; command output over stage 1 runs |
| 13 | the decision record is an amendment section in `plugins/drawing-diagrams/docs/design.md` | `rg` output |

Unit tests use the standard library (`python3 -m unittest`) and live in `plugins/drawing-diagrams/tests/`,
outside the skill directory.

## 10. Resolved questions

Answered by the owner on 2026-09-17.

- **Q1.** The decision record is an amendment section in `plugins/drawing-diagrams/docs/design.md`
  (criterion 13).
- **Q2.** The transcript measurement script lives in the repository as `tools/transcripts.py`
  (§6, criterion 12).
- **Q3.** The experiment harness may change user settings: a temporary directory marketplace and the
  production plugin disabled for the experiment. Each change is stated before it is made, and the
  settings are restored after stage 3 or when the experiment stops.
