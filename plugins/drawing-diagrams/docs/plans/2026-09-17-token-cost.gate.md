# Plan gate findings carried into implementation

Gate: `codex-gates:codex-review plan`, one pass, 2026-09-17, verdict `changes_requested`, six P1, no P0.
A document gate does not re-review the plan: every accepted finding below is a check the implementation
must prove. Where a check contradicts code in `2026-09-17-token-cost.md`, the check wins. The branch gate
receives the spec, the plan and this file.

| # | Finding | Decision | Task | What the implementation must prove |
|---|---|---|---|---|
| G1 | The content gate matches expected items as substrings of all model JSON, so a name mentioned only in a note passes | accepted | 10 (Step 5–6) | `T*.expected.json` lists items per model file. `score.py` looks for them only in structural fields of that model: `schema` — `tables[].name`; `flow`, `swimlane`, `state`, `blocks` — `nodes[].id`, `nodes[].title`, `nodes[].text`, and the `label` of every group named in `lanes`; `timeline` — `entities[].label`, `moments[].title`, `moments[].text`, the values of `moments[].states`. Proof: a hand-made run directory whose schema model names a required table only in `notes` fails the gate. |
| G2 | More crossings than V0 is shown in the report but never enters the stored gate that stage decisions and the review filter read | accepted | 10 (Step 6), 12, 13, 14 | `report.py` computes an effective gate per run — the stored gate plus "crossings not above the V0 run of the same task" — writes it to `results_effective.json`, and Tasks 12–14 and the review page select only by the effective gate. Proof: a fixture where a candidate has gate `ok` and one crossing more than V0 gets a failing effective gate and is absent from `review/index.html`. |
| G3 | The plan turns the 15% re-run trigger into a minimum required saving | accepted | 12 (Step 3), 13 (Step 4), 14 | 15% only triggers the second run. A stage reports the mean of its deciding metric (or cost) for every variant whose effective gate passes, without a minimum saving; the owner chooses among all of them (spec §6 Decision). The effort level of V4 is that of the cheaper of V2 and V3 when its mean `out` is below V1's, otherwise `high`. Proof: the stage lines in `NOTES.md` state means per variant, no threshold. |
| G4 | A successful widget render prints no summary to stderr, while spec §4 R3 puts warnings and the summary there | accepted | 5 | Every successful render that is not `--check` prints one line to stderr: `ок: вид <kind>, <n> узлов, <m> связей, <w> предупреждений` (the `--check` shape), with `записано …` still added for `--out`. Proof: a unit test asserting stdout is exactly the fragment and stderr contains that line. |
| G5 | The experiment records output file bytes, while spec §6 names widget fragment characters | accepted | 10 (Step 6), 11–14 | `score.py` records `widget_fragment_chars = sum(len(p.read_text()) for p in outputs)`; `report.py` shows that column. Bytes may stay as a separate diagnostic. Proof: the key in `results.jsonl` and the column in `report.md`. |
| G6 | A flow model with a non-text layout error and an ordinary validation error prints no map, because the draft re-plan raises too | accepted | 5 | When the draft re-plan raises, `failure_map` falls back to the grid map (`parse_grid` + `ascii_map`) for every kind that has a grid. Proof: a unit test with a five-column grid and a duplicated node id whose stderr contains both `grid шириной 5` and the grid row `a  b  c  d  e`. |

Goal check after triage: the plan still does what was asked — cheaper use of the skill without binding it to
artifacts. The findings tighten the experiment's measurements and the CLI contract; no decision on asset
delivery, the render loop or the reference changes.
