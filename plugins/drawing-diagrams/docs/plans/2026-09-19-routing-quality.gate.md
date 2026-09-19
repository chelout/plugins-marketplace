# Plan gate findings carried into implementation

Gate: `codex-gates:codex-review plan`, one pass, 2026-09-19, verdict `changes_requested`, four P1,
one P2, no P0. A document gate does not re-review the plan: every accepted finding below is a check
the implementation must prove. Where a check contradicts a task in `2026-09-19-routing-quality.md`,
the check wins. The branch gate of each stage receives the spec, the plan and this file.

Every finding was checked against the code at `d67f1a5` before it was accepted: `render.produce` and
`render.failure_map` pass `overrides` to `plan`; the lane limit in `flow.plan` is a layout error and
so is downgraded by `draft`; `flow.under_card` leaves out the card the label hangs from
(`c != X // 2`); the label block of `template/js/flow.js` puts a straight vertical label on the right
only and a label over a horizontal second segment at its far end only.

| # | Finding | Decision | Task | What the implementation must prove |
|---|---|---|---|---|
| G1 | Task 12 gives `route_all` a `room` argument but leaves `flow.py` out of its files, so production routing would run with `overflow` identically zero | accepted | 12 (also 9) | Task 12 also modifies `SKILL/diagrams/flow.py`: `flow.plan` passes `Geometry.room` to `route_all` and to `assign_offsets`. Proof: a test through `flow.plan` on a model with a group over capacity, where Φ of the production routing is computed with `room` and its `overflow` term is positive before the descent and not above it after. |
| G2 | `advice.evaluate` and `advice.search` take no `overrides`, while `render.main` forwards `--width`, `--open` and `--types` to `plan`; a label that fits at 680 px fails at 300 px, so advice could call a move free of new errors after checking another geometry | accepted | 15, 16 | `evaluate(model, mode_name, overrides)` and `search(model, mode_name, overrides, …)`; every verifying plan gets the overrides of the render. Proof: a CLI test with a non-default `--width` and a width-sensitive label, where the advice printed is the one found under that width (a move that only fits at the default width is not offered). |
| G3 | The exhaustive search over `lanes` assumes at most seven lanes, but `draft` downgrades the lane limit: a twelve-lane model reaches the trigger and 12! permutations, which the 40-plan allowance does not bound | accepted | 14, 16 | No advice for a model over a limit of its mode (`max_lanes`, `max_cols`, `max_nodes`): the search is skipped and says nothing. `advice.moves` never materialises more than 5 040 lane orders. Proof: a CLI test with a twelve-lane swimlane that returns in under a second with the limit error and no advice, and a unit test of the cap. |
| G4 | Spec §7.1 made every card infinite in its row, which rejects a valid label hanging under its own short source card (`UnderShortCard`: card x = [18, 158], label x = [93, 186.18]) | accepted; the sentence of spec §7.1 was corrected the same day, before the owner's acceptance | 19 | A candidate that hangs from its source card is not tested against that card nor against the lines leaving or entering it within its height; it is tested against the other cards of the row and the lines at their height. Proof: the `UnderShortCard` cases of `tests/test_label_lines.py` are part of the equivalence test of task 19 and stay green through task 20. |
| G5 | Task 20 enables places the script cannot draw until task 21: `ls` and `ly` cannot express "left of a straight vertical line" or "just after the bend" | accepted | 19–21 | Order of work in stage E: task 18, task 19, task 20 commit 1 (the switch, today's candidates), task 21 (anchor producer and consumer, still today's candidates; golden identical apart from `la` replacing `ls`/`ly` in the edge JSON), then task 20 commits 2 and 3 (new candidates, search). Proof: at every commit of the stage the browser test of task 21, once it exists, is green, and no commit offers a candidate the script of that commit cannot draw. |

Goal check after triage: the documents still do what was asked — a spec and a plan of the proposed
improvements, for later implementation. The findings tighten four seams (the room reaching production
routing, the render's overrides reaching the advice, a bound on lane permutations, the label's own
card) and the order of two tasks; no decision of the spec changes.
