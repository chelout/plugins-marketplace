# drawing-diagrams routing and label quality Implementation Plan

> **For agentic workers:** implement task by task, test first, one task per dispatch (team-skills
> `slice-delivery`, or `superpowers:subagent-driven-development` where that is the process in use).
> Steps use checkbox (`- [ ]`) syntax for tracking. Tasks 6, 10, 13, 17 and 22 need the controller
> (branch gates, the owner's pair review, headless Claude runs, the CDN release); every other task
> can be dispatched to a subagent.

**Goal:** Make the renderer draw exactly the crossings it counts, give gutters a capacity, route
against a stated objective, advise verified node moves, and place labels with one model whose drawing
rule lives in Python only.

**Architecture:** `diagrams/router.py` keeps routing, ordering and counting and gains
`route_all` (the routing loop taken out of `flow.plan`), run-keyed slots, the two drawn counters,
gutter capacity, fast `Traffic` and the objective Φ. A new `diagrams/advice.py` searches node moves
and verifies them with `flow.plan`. A new `diagrams/labels.py` holds the occupancy model, the
candidates and the choice; `flow.py` keeps the model checks and emits a label anchor per edge, which
`template/js/flow.js` applies without a rule of its own.

**Tech Stack:** Python 3 standard library (`unittest`, `heapq`, `itertools`, `random` in tests
only), vanilla JS/CSS, headless Chrome through the harness of `tests/test_browser_lines.py`, Codex
gate `codex-gates:codex-review`.

**Spec:** `plugins/drawing-diagrams/docs/specs/2026-09-19-routing-quality-design.md`

**Gate findings carried into implementation:**
`plugins/drawing-diagrams/docs/plans/2026-09-19-routing-quality.gate.md` — where a check there
contradicts a task below, the check wins.

## Global Constraints

- Paths are relative to the repository root; `SKILL` means
  `plugins/drawing-diagrams/skills/drawing-diagrams`, `PLUGIN` means `plugins/drawing-diagrams`.
- Standard library only. Tests run with `cd PLUGIN && python3 -m unittest discover -s tests -v`.
- Tools and tests live outside `SKILL`: `PLUGIN/tools/`, `PLUGIN/tests/`; `tests/support.py` puts
  both on `sys.path`.
- Renderer messages stay in Russian; documents in English.
- No comments in `SKILL/template/js/*.js`: the fragments ship verbatim into every diagram. What a
  line of script is for goes into the Python that mirrors it, the commit and the pull request.
- Every stage is a branch and a pull request of its own, cut from `main`; the branch names are in
  the stage headings. A stage starts when the one before it is merged.
- A stage that changes `SKILL/template/css` or `SKILL/template/js` rebuilds `template/dist`
  (`python3 PLUGIN/tools/assets.py build`, `check`), pins `template/dist/REF`, is merged with a
  merge commit and ends with `tools/assets.py verify-cdn` (`design.md` §13).
- No randomness and no clock in `SKILL/diagrams`; iteration that affects output runs over sorted
  integer keys.
- Before each commit that touches the plugin: `claude plugin validate plugins/drawing-diagrams`
  (the only expected warning is the missing `version`).
- Commit messages follow the history: `type(drawing-diagrams): what changed`, ending with the
  session's `Co-Authored-By:` trailer.
- Golden comparison, used by several tasks. At the merge base and at the head:

  ```bash
  cd plugins/drawing-diagrams && for m in widget page; do python3 -B skills/drawing-diagrams/render.py \
    skills/drawing-diagrams/examples/*.json skills/drawing-diagrams/examples/full/*.json \
    --mode $m --assets inline --out-dir "$GOLD/$m"; done
  ```

  with `GOLD` a directory outside the repository, one per commit; then `diff -r` of the two. "Golden
  identical" below means that diff is empty for all 14 files.

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `PLUGIN/tools/instances.py` | seeded random grids and edges for tests and the benchmark | 0 |
| `PLUGIN/tools/bench_routing.py` | times `flow.plan` on the examples and routing on the dense scenario | 0 |
| `SKILL/diagrams/router.py` | `route_all`; run-keyed `assign_offsets`; `drawn_crossings`, `drawn_overlaps`; capacity; fast `Traffic`; `describe`, `pair`, `phi` | 1–5, 7–12 |
| `SKILL/diagrams/flow.py` | calls `route_all`; reports drawn crossings; room and capacity error; draft metrics for the advice; label anchors | 1, 5, 8, 9, 15, 20, 21 |
| `SKILL/diagrams/advice.py` | moves, their rules, proxy, search, text of the advice | 14–16 |
| `SKILL/diagrams/labels.py` | occupancy rectangles, candidates, conflict predicate, branch and bound | 18–21 |
| `SKILL/render.py` | `--no-advice`; `main` calls the advice once and prints it on stderr | 16 |
| `SKILL/template/js/flow.js` | applies the label anchor `la` | 21 |
| `SKILL/template/dist/*` | rebuilt build and `REF` | 22 |
| `SKILL/reference/flow.md`, `SKILL/SKILL.md` | capacity message, advice, `--no-advice` | 9, 16 |
| `PLUGIN/docs/design.md` | §14 amendment, one paragraph per stage | 5, 9, 13, 16, 22 |
| `PLUGIN/tests/reference.py` | today's routing loop and `Traffic`, kept as oracles | 1, 7, 12 |
| `PLUGIN/tests/test_drawn.py`, `test_drawn_property.py` | counters; the invariant | 2, 3 |
| `PLUGIN/tests/test_crossings.py` | cases A, B, C | 4, 5 |
| `PLUGIN/tests/test_capacity.py`, `test_objective.py`, `test_advice.py`, `test_labels.py` | per stage | 7–12, 14–16, 18–21 |
| `PLUGIN/tests/test_browser_lines.py`, `test_render_cli.py`, `test_label_lines.py` | browser checks at capacity and of label boxes; CLI; label cases kept through the refactor | 9, 16, 18–21 |

---

## Stage 0 — shared tooling

### Task 0: Seeded instances and the routing benchmark

Spec: performance budget slot; §10 "Every stage".

**Files:** Create `PLUGIN/tools/instances.py`, `PLUGIN/tools/bench_routing.py`,
`PLUGIN/tests/test_instances.py`.

**Interfaces:**
- `instances.random_instance(rng, cols, rows, n_nodes, n_edges) -> (cells, edges)`: `cells` maps a
  node id to `(row, col)`, `edges` is a sorted list of `(a, b)` without duplicates, reverses or
  loops. Only `random.Random(seed)` passed in; no module-level randomness.
- `instances.small(seed, count)` and `instances.dense(seed, count)`: generators of
  `(cols, rows, cells, edges)`; small is grids 3–6 × 3–6 with 5–18 nodes and 1–1.5 edges per node,
  dense is grids 4–6 × 4–8 with 15–30 edges.
- `instances.DENSE_SCENARIO = (6, 7, 30, 40)` and `instances.dense_scenario(seed)`.
- `bench_routing.py [--json]`: best of 5 of `flow.plan` per shipped flow-like example and mode; for
  seeds 1–10 of the dense scenario the median and max of routing + `assign_offsets` +
  `crossings` in ms and the median crossings.

- [ ] Test: the same seed gives the same instance twice; no edge repeats or reverses another; every
  node has a distinct cell inside the grid.
- [ ] Implement; `python3 PLUGIN/tools/bench_routing.py` prints numbers within 30 % of the spec's
  baseline on the same machine (examples 2.6–11.2 ms, dense median 265 ms). Record the output in the
  task report: it is the baseline every later stage compares with.
- [ ] Commit `test(drawing-diagrams): seeded routing instances and a routing benchmark`.

Check: `cd PLUGIN && python3 -m unittest discover -s tests -p 'test_instances.py' -v`.

---

## Stage A — what is drawn equals what is counted (branch `fix/drawing-diagrams-drawn-crossings`)

### Task 1: `router.route_all`, the routing loop out of `flow.plan`

Spec: §3.4 (the property test routes "as `flow.plan` does"), §5.3 (stage C replaces this body).

**Files:** Modify `SKILL/diagrams/router.py`, `SKILL/diagrams/flow.py`; create
`PLUGIN/tests/reference.py`, `PLUGIN/tests/test_route_all.py`.

**Interfaces:** `router.route_all(lat, ends, labelled) -> list[path | None]` — `ends[i]` is
`(src_point, dst_point)`, `labelled[i]` a bool. Behaviour is exactly the block of `flow.plan` between
the comments `# routing` and `# where a label goes`: first pass in the given order with accumulating
`Traffic`, an unroutable edge stays `None` and takes no part in the two rip-up passes. `flow.plan`
builds `ends` and `labelled` from `edges`, calls it, and turns a `None` into today's layout error.

- [ ] `tests/reference.py`: today's routing block copied as `reference_route_all(lat, ends,
  labelled)`, an oracle for tasks 1 and 12 (task 7 adds today's `Traffic` to it as `OldTraffic`).
- [ ] Test (red: `route_all` does not exist): `route_all` and the oracle give identical paths for the
  four flow-like examples in both modes and for `instances.small(5, 60)`; a grid where a node walls
  an edge in yields `None` for that edge and paths for the rest.
- [ ] Move the loop; no other change. Golden identical.
- [ ] Commit `refactor(drawing-diagrams): routing loop of flow.plan becomes router.route_all`.

Check: full test suite; golden identical.

### Task 2: `drawn_crossings` and `drawn_overlaps`

Spec: §3.3.

**Files:** Modify `SKILL/diagrams/router.py`; create `PLUGIN/tests/test_drawn.py`.

**Interfaces:** `router.drawn_crossings(paths, offsets, nodes) -> int`,
`router.drawn_overlaps(paths, offsets, nodes) -> int`; `offsets` as `assign_offsets` returns them,
`nodes` a set of lattice points. Shared private helper turns a path into integer points
`(x * BIG + round(2 * ox), y * BIG + round(2 * oy))`, `BIG = 10000` (half-pixel units: pitches of 5 px
give `.5` offsets); an end on a node moves `BIG // 2` towards its neighbour and takes the
neighbour's cross coordinate.

- [ ] Tests, hand-made, offsets from `assign_offsets` unless stated:
  `SWAP_PATHS` of `tests/test_crossings.py` → 1 crossing, 0 overlaps; `NO_SWAP_PATHS` → 0, 0;
  `[(1,1),(1,5)]` and `[(5,5),(1,5)]` with nodes at their ends → 0 (two sides of one node do not
  meet at its centre); `[(1,1),(1,3),(5,3)]` and `[(3,1),(3,5)]`, nodes at the ends → 1;
  two copies of `[(1,1),(2,1),(2,5),(3,5)]` with all-zero offsets passed by hand → overlaps ≥ 1.
- [ ] Implement; precedent for the segment walk: `router.crossings`.
- [ ] Commit `feat(drawing-diagrams): count the crossings and overlaps actually drawn`.

Check: `cd PLUGIN && python3 -m unittest discover -s tests -p 'test_drawn.py' -v`.

### Task 3: The invariant as a property test, expected to fail

Spec: §3.4, criterion A2.

**Files:** Create `PLUGIN/tests/test_drawn_property.py`.

- [ ] Test `DrawnEqualsCounted`: for `instances.small(20260918, 240)` and
  `instances.dense(20260919, 60)`: `paths = route_all(...)` without the `None`s,
  `offs = assign_offsets(paths, nodes=frozenset(lat.blocked))`; collect every instance where
  `drawn_crossings != crossings` or `drawn_overlaps != 0`; fail with the count and the smallest
  failing instance printed as `paths = [...]`. Decorate it `@unittest.expectedFailure` with a comment
  naming tasks 4 and 5.
- [ ] Run it without the decorator once and record the red run: at the governing base about 1 % of
  small instances fail. If none of these 300 fails, raise `count` until one does and keep that
  count.
- [ ] Commit `test(drawing-diagrams): drawn crossings equal counted ones, expected to fail`.

Check: the suite is green with the decorator; the report carries the red run without it. Under 20 s.

### Task 4: Runs own slots and pair orders

Spec: §3.1, criterion A1 (cases A and C).

**Files:** Modify `SKILL/diagrams/router.py` (`assign_offsets` only),
`PLUGIN/tests/test_crossings.py`.

**Interfaces:** `assign_offsets(paths, step=8, nodes=frozenset())` unchanged outside. Inside: items
are runs `{"i", "r", "lo", "hi", "lo_side", "hi_side"}`, consecutive collinear segments of a path
merged; `slot[(i, r)]`; `firm[(u, v)]`, `loose[(u, v)]` with `u = (i, r)`, `v = (j, r2)` found per
straight piece of a stretch as the run of each path on that line whose interval covers the piece;
the offset of point `m` of path `i` is read from the runs through it.

- [ ] Tests in a new class `RunKeys`, both red at the base:
  case A (three paths of spec §3.1): `drawn_overlaps == 0` and
  `drawn_crossings == crossings == 1`;
  case C (two paths of spec §3.1): `drawn_crossings == crossings == 1`, and on `x = 4` the first path
  lies left of the second at `y = 1` and right of it at `y = 9` (compare `ox`).
- [ ] A path given with collinear consecutive points (`[(1,1),(1,3),(1,5),(3,5)]`) gets one `ox` on
  all of `x = 1`: a test.
- [ ] Implement. `CornerOrder` and `SharedStretch` stay green. Golden identical.
- [ ] Commit `fix(drawing-diagrams): a slot and a pair order belong to a run, not to a path`.

Check: `cd PLUGIN && python3 -m unittest discover -s tests -p 'test_crossings.py' -v`; golden
identical.

### Task 5: Runs that meet end to end; the invariant holds; `flow.plan` reports what is drawn

Spec: §3.2, §3.5, §3.6, criteria A1 (case B), A2, A3, A4.

**Files:** Modify `SKILL/diagrams/router.py`, `SKILL/diagrams/flow.py`,
`PLUGIN/tests/test_crossings.py`, `PLUGIN/tests/test_drawn_property.py`, `PLUGIN/docs/design.md`.

- [ ] Test `EndToEnd` (red): the four paths of spec §3.2 → `drawn_crossings == crossings == 5`.
- [ ] Implement the rule inside the group loop of `assign_offsets` as a third strength `soft`,
  recorded only where the two runs have no firm or loose order; the pick order becomes free under
  (`firm`, `loose`, `soft`), then (`firm`, `loose`), then (`firm`), then `ranked[0]`.
  `CornerOrder.test_a_swap_gives_way_to_an_order_without_one` stays green.
- [ ] Remove `expectedFailure` from `DrawnEqualsCounted`: green on all 300 instances. If an instance
  fails, it becomes a regression case in the task report and the controller decides between
  promoting the rule and the port of spec §8; the task does not decide it.
- [ ] Test: for every flow-like example and mode, `layout["crossings"]` equals `drawn_crossings` of
  `layout["paths"]` with the offsets read back from `layout["edges"][k]["path"]`. Then set it in
  `flow.plan`. The warning text does not change.
- [ ] Docstring of `route`: "+3" for another line's corner.
- [ ] `design.md` §14 "Routing quality (amendment, 2026-09-19)": the invariant, the run as the unit
  of order, the three strengths of order, and the property test as the guard of any later ordering.
- [ ] Commits `fix(drawing-diagrams): order runs that meet end to end in a gutter`,
  `fix(drawing-diagrams): report the crossings that are drawn`,
  `docs(drawing-diagrams): design amendment for drawn crossings`.

Check: full suite under its usual time plus 20 s; golden identical; `bench_routing.py` within budget.

### Task 6: Stage A branch gate and hand-over

- [ ] Controller: `codex-gates:codex-review branch` with the spec and this plan; triage; pull request
  on the owner's word.

---

## Stage C1 — fast `Traffic` (branch `perf/drawing-diagrams-fast-traffic`)

### Task 7: Reference counts with `add` and `remove`

Spec: §5.1, criterion C1, part of C2.

**Files:** Modify `SKILL/diagrams/router.py` (`Traffic`, and `route_all` to use `remove`/`add`
instead of rebuilding `Traffic` per edge), `PLUGIN/tests/reference.py`; create
`PLUGIN/tests/test_traffic.py`.

**Interfaces:** `Traffic.add(path)`, `Traffic.remove(path)`, `crosses(nx, ny, vertical) -> bool`,
`shares(x, y, nx, ny) -> bool`, and the mappings `corners`, `exits`, `entries`, `units` (count per
unit edge `(axis, line, k)`). `route` reads membership of `corners` and the booleans exactly as
today; the counts exist for `remove` and for task 9.

- [ ] Test: today's `Traffic` copied into `tests/reference.py` as `OldTraffic`; for
  `instances.small(7, 120)` and `instances.dense(8, 30)`, routing with either class gives identical
  paths edge by edge. The same path added twice: `crosses` and `shares` are `True`, not 2, and one
  `remove` keeps them `True`. `remove` after `add` of every path leaves every mapping empty.
- [ ] Implement. Golden identical. Property test green.
- [ ] `bench_routing.py`: dense median at least three times below the task 0 baseline; record it.
- [ ] Commit `perf(drawing-diagrams): Traffic counts references and can remove a path`.

Check: `cd PLUGIN && python3 -m unittest discover -s tests -p 'test_traffic.py' -v` and
`cd PLUGIN && python3 -m unittest discover -s tests -p 'test_drawn_property.py' -v`; benchmark output.

---

## Stage B — gutter capacity (branch `feat/drawing-diagrams-gutter-capacity`)

### Task 8: Room per lattice line and the adaptive pitch

Spec: §4.1, §4.2, criteria B0, B1.

**Files:** Modify `SKILL/diagrams/router.py`, `SKILL/diagrams/flow.py` (`Geometry`),
`PLUGIN/tests/test_browser_lines.py`; create `PLUGIN/tests/test_capacity.py`.

**Interfaces:**
- `flow.LINE_CLEAR = 4`, `flow.EDGE_CLEAR = 1`. `Geometry.room(axis, line) -> (lower, higher) | None`:
  the usable px on each side of an even line, clearance already taken (`LINE_CLEAR` towards cards,
  `EDGE_CLEAR` towards the grid box), from `gap`, `row_gap`, `margin`, `pad_l`/`pad_r`, and for the
  top and bottom margins from the constants measured below; `None` for odd lines.
- `router.PITCHES = (8, 6, 5)`; `router.fits(w, pitch, room) -> bool` is
  `(w - 1) * pitch / 2 <= min(room)`; `router.capacity(room) -> int` at the smallest pitch.
- `assign_offsets(paths, step=8, nodes=frozenset(), room=None)`: `room` a callable
  `(axis, line) -> pair | None`; with `room` a group takes the first pitch that fits, else the
  smallest. The return value keeps its shape; `schema.plan` keeps calling it without `room`.
- `router.overfull(paths, nodes, room) -> list[(axis, line, [path indices], capacity)]`: the groups
  — the same groups `assign_offsets` forms — that do not fit at the smallest pitch.
  Amended 2026-09-20 (task 9a): the shape is `(axis, line, width, [path indices], capacity)`, `width`
  the number of slots the group is drawn in; the indices name who to move and may be more than the
  width. Task 11's `router.overflow` is built from this shape.

- [ ] Browser measurement first (B0): a page and a widget model with one line along the top margin
  and one along the bottom, in flow and in swimlane; the harness reports the distance from that line
  to the nearest card edge and to the nearest edge that clips or covers it (grid box, section,
  swimlane header). Record the four numbers in the task report; they become
  `flow.TOP_ROOM`/`flow.BOTTOM_ROOM` per mode, named in the `design.md` amendment of task 9.
  Amended 2026-09-20: as measured, the tables are keyed by kind and mode, the bottom one by the
  footnotes as well, and the bound is what clips or covers the line, not the grid box (spec §4.1).
- [ ] Tests: the most lines that fit at pitches 8, 6, 5 are 3, 4, 5 for usable room (10, 10) (`gap`
  28); 2, 2, 3 for (5, 5) (`gap` 18); 2, 2, 3 for a widget side margin, usable (8, 5). Five parallel
  runs in one column gutter take pitch 6 at (12, 12) (`gap` 32) and are `overfull` at (5, 5); three
  runs keep pitch 8 at (10, 10). A chain of four runs that only meet end to end is one group of four
  (spec §4.1) and is `overfull` at (5, 5). `Geometry.room` for every mode of `MODES` against
  hand-computed pairs.
- [ ] Implement. With `room=None` offsets are today's. Golden identical (examples fit at 8 px);
  property test green with and without `room`.
- [ ] Commit `feat(drawing-diagrams): gutters know their room and lines close up to fit`.

Check: `cd PLUGIN && python3 -m unittest discover -s tests -p 'test_capacity.py' -v`; golden identical.

### Task 9: The router prices a full gutter; the check tells the author

Spec: §4.3, §4.4, criteria B2, B3, B4.

**Files:** Modify `SKILL/diagrams/router.py` (`Lattice`, `route`), `SKILL/diagrams/flow.py`,
`SKILL/reference/flow.md`, `PLUGIN/docs/design.md`, `PLUGIN/tests/test_capacity.py`,
`PLUGIN/tests/test_browser_lines.py`, `PLUGIN/tests/test_render_cli.py`.

**Interfaces:** `Lattice(cols, rows, occupied, capacity=None)`, `capacity` a callable
`(axis, line) -> int | None`; in `route`, a step along a unit edge of an even line whose
`traffic.units` load is already the capacity costs `+20`.

- [ ] Test B4: a hand-made grid with a gutter at capacity and a free detour of cost below 20: the
  next edge takes the detour; without `capacity` it takes the gutter.
- [ ] Test: a model whose gutter cannot fit → `ModelError` with a layout error matching
  `между столбцами \d+ и \d+ линий \d+, помещается \d+`, the map printed, `--draft` renders with
  the warning "черновик: …". Rows ("между рядами") and margins ("по левому полю", "по правому
  полю", "по верхнему полю", "по нижнему полю") each have a case. Amended 2026-09-20: the wording is
  the one spec §4.4 now carries (the noun first; "идут 1 линий" was not Russian), and as built the
  column gutter and the two row margins have model-level cases while "между рядами" and the side
  margins are cases of the message builder; the qa review of the stage accepted that.
- [ ] Browser test: a page model with a group at capacity at each pitch: every path's bounding box
  keeps ≥ 3 px from every card it does not end on and lies inside the grid box.
- [ ] `reference/flow.md`: one row in the errors table. `design.md` §14: the capacity rule.
- [ ] Two stress models under `PLUGIN/tests/models/` (dense widget flow, dense page swimlane) rendered
  before and after for the owner's pair review.
- [ ] Commits `feat(drawing-diagrams): a full gutter costs more than a crossing`,
  `feat(drawing-diagrams): refuse a gutter with more lines than fit`,
  `docs(drawing-diagrams): gutter capacity in the reference and the design`.

Check: full suite with the browser tests; golden identical; benchmark within budget.

### Task 9a: Slots are reused (added 2026-09-20 by the owner's word)

Spec: §4.1a, criterion B5.

**Files:** Modify `SKILL/diagrams/router.py`, `SKILL/diagrams/flow.py`, `PLUGIN/docs/design.md`,
`PLUGIN/tests/test_capacity.py`, `PLUGIN/tests/test_label_lines.py`, the dense models under
`PLUGIN/tests/models/`.

**Interfaces:** the width of a group is its slot count. One place decides order and slots for both
`assign_offsets` and `overfull` (as `_line_groups` is one place for the groups); `overfull` reports
the width the message prints.

- [ ] Tests first: two runs chained through a third that lies above both take one slot and the
  group is two wide; a staircase of orders stays as wide as it is long; runs that meet end to end in
  a gutter never share a slot; `overfull` and the pitch follow the width; the chain-of-four case of
  task 8 is restated under the rule.
- [ ] Implement over the existing order: lowest slot above every earlier run the run lies beside.
  Property test green under all rooms; golden identical.
- [ ] The dense models must again reach the 6 and the 5 px pitch (they were found for the old width);
  fixtures of `tests/test_label_lines.py` that stood on an old width get their premises back, no
  assertion loosened.
- [ ] `design.md` §14: the rule, and the sentences that say a group of `w` runs is `w` slots wide.
- [ ] Commit `feat(drawing-diagrams): runs that never lie side by side share a slot`.

Check: full suite with the browser tests; golden identical; benchmark within budget; the refusal
rates of the controller's experiment reported before and after.

### Task 10: Stage B review and gate (controller)

- [ ] Render the examples and the two stress models of task 9 before and after; owner's pair review
  of line pitch and of the capacity message; record the word (spec Q1 is settled here).
- [ ] `codex-gates:codex-review branch` with the spec and this plan; triage; pull request on the
  owner's word.

---

## Stage C — routing with an objective (branch `feat/drawing-diagrams-routing-objective`)

### Task 11: `describe`, `pair`, `phi`

Spec: §5.2, criterion C2.

**Files:** Modify `SKILL/diagrams/router.py`; create `PLUGIN/tests/test_objective.py`.

**Interfaces:**
- `router.route(..., cost=None)`: when `cost` is a list, the total cost of the returned path is
  appended to it; nothing else about `route` changes.
- `router.describe(lat, path, labelled) -> Info` with `own`, `units`, `inner`, `corners`, `hs`,
  `vs`, `exit`, `entry`, `path`; `own` replays the step rules of `route` without traffic: no turn
  cost on the first step, no empty-cell cost for the target, margin cost on the arriving point, `+8`
  through the top on the first step only, `+4` from below on the last step only, and `+8` for
  `labelled` — which `flow.plan` sets for a label or a footnote — on a first step sideways whose
  next cell is occupied, the target included.
- `router.pair(a, b) -> int` per spec §5.2; `router.overflow(infos, nodes, room) -> int` from
  `router.overfull` (0 when `room` is `None`); `router.phi(infos, nodes, room) -> int`;
  `router.delta(i, new, infos, nodes, room) -> int`.
  Amended 2026-09-20 (spec §5.2, after stage B): `own` also replays the +20 of a step along a line
  whose capacity is 0, read from the lattice; `overflow` sums `width − capacity` over the
  five-tuples of `router.overfull`; and it takes the lattice lines to look at, so that `delta`
  recomputes it on the lines the old and the new path have runs on and nowhere else.

- [ ] Tests on `instances.small(11, 100)`: `own(p)` equals the cost `route` reports for `p` with
  `traffic=None`, and equals it for labelled edges too; `phi` equals a direct count written in the
  test from `segments`, `crossings`, shared unit steps, corner hits, exits and entries; `delta`
  equals `phi(after) − phi(before)` for 200 seeded single-edge replacements, with and without
  `room`. Amended 2026-09-20: `own` is held equal to `route`'s cost on a lattice with
  capacities too, a line that holds nothing among them; the instances with `room` must include
  ones whose `overflow` is not zero before or after the replacement, or the term is not tested;
  and `overflow` restricted to the touched lines equals the difference of two whole-routing sums.
- [ ] Implement. Nothing calls it yet. Golden identical.
- [ ] Commit `feat(drawing-diagrams): a routing objective with an exact single-edge delta`.

Check: `cd PLUGIN && python3 -m unittest discover -s tests -p 'test_objective.py' -v`.

### Task 12: Canonical order, two starts, descent on Φ

Spec: §5.3, §5.4, criterion C3.

**Files:** Modify `SKILL/diagrams/router.py` (`route_all`), `PLUGIN/tests/test_objective.py`,
`PLUGIN/tests/test_route_all.py`.

**Interfaces:** `route_all(lat, ends, labelled, room=None, budget=600, passes=8, trace=None) ->
list[path | None]`. Today's loop lives on only as `reference_route_all` in `tests/reference.py`.

- [ ] Tests: on `instances.small(12, 70) + instances.dense(13, 30)`, Φ of the result is at most Φ of
  the reference loop in ≥ 90 % of the instances, and Φ falls strictly across the accepted changes
  that `trace` records; `ends` shuffled with five seeds give, per (source, target, labelled), the
  same multiset of paths; two calls give identical paths; the descents never make more than `budget`
  calls of `route` (count through a wrapper), while a model of 350 parallel edges still returns a
  path for every routable edge. For the four flow-like examples `crossings` does not rise against
  the reference loop.
- [ ] Implement per spec §5.3: the canonical key is (Manhattan length, source, target, labelled,
  index); both starts complete whatever the budget; the descents get half the budget each, the second
  also what the first left; an unroutable edge stays `None` in both starts and out of the descent.
- [ ] `test_route_all.py`: the identity with the oracle goes (it is now the comparison above); the
  unroutable-edge case stays.
- [ ] `bench_routing.py`: dense median ≤ 300 ms, examples ≤ 25 ms; record.
- [ ] Commit `feat(drawing-diagrams): route against an objective, from two starts, to a fixed point`.

Check: full suite; benchmark output. Golden is expected to differ: list the examples whose routes
changed in the task report.

### Task 13: Stage C review and gate (controller)

- [ ] Render the examples and the two stress models before and after; owner's pair review; record
  the word. `design.md` §14: the objective, the orchestration, the independence from edge order.
- [ ] Branch gate; pull request on the owner's word.

---

## Stage D — rearrangement advice (branch `feat/drawing-diagrams-advice`)

### Task 14: Moves and their rules

Spec: §6 "Moves", "Swimlane", criterion D1.

**Files:** Create `SKILL/diagrams/advice.py`, `PLUGIN/tests/test_advice.py`.

**Interfaces:** `advice.moves(original, current) -> list[Move]` in the order of spec §6, the rules
judged against `original`; `Move` has `kind` (`swap`, `shift`, `lanes`), the node ids or the lane
order, `apply(model) -> model` — a deep copy with a new `grid` (and, for `lanes`, a new `lanes` with
the grid columns permuted the same way), nothing else touched — and `text()` in Russian. Grid
parsing through `grid.parse_grid`; the grid is written back with the token widths of the input.

- [ ] Tests: no sequence of moves turns an edge that runs downward in the original grid upward, even
  through a move that first makes it horizontal; a node without incoming edges stays in row 0; a
  swimlane model with explicit node groups yields only `lanes` moves, each of which plans without a
  group/lane error; a flow model yields swaps inside rows first; `apply` keeps grid width and
  height, leaves its argument untouched (compare a deep copy taken before), and the result plans
  without a placement error; `nodes`, `edges`, `routes` and `footnotes` are equal before and after.
- [ ] Implement. Commit `feat(drawing-diagrams): node moves an advice may propose`.

Check: `cd PLUGIN && python3 -m unittest discover -s tests -p 'test_advice.py' -v`.

### Task 15: Proxy, verification, hill climbing

Spec: §6 "Search", criterion D2.

**Files:** Modify `SKILL/diagrams/advice.py`, `SKILL/diagrams/flow.py` (`plan` with `draft=True`
puts `unroutable`, a count, and `overfull`, the list of task 9, into `layout`),
`PLUGIN/tests/test_advice.py`, `PLUGIN/tools/bench_routing.py` (`--advice`).

**Interfaces:** `advice.evaluate(model, mode_name) -> (score, errors)`: a draft plan of a deep copy;
`score` is `(unroutable, overflow, crossings, length)`, `errors` the set of draft-downgraded
messages.
Amended 2026-09-20 (spec §6 as amended; plan gate findings G2 and G3): `evaluate(model, mode_name,
overrides)` and `search(model, mode_name, overrides, …)` — every verifying plan gets the overrides
`render.main` forwards; `score` is `(overflow, crossings, length)` with `overflow` the slots over
capacity; `flow.plan` with `draft=True` puts `overflow` and `overfull` into `layout` and no
`unroutable`; no advice for a model over a limit of its mode, and the lane permutations are never
materialised beyond what the limit allows. `advice.proxy(model) -> int`. `advice.search(model, mode_name, top=8, max_moves=8,
max_plans=40) -> list[(Move, score_before, score_after)]`, empty when nothing improves.

- [ ] Tests (amended 2026-09-20: the walled-in edge of the first text cannot be built from a model and
  is dropped; a draft plan of `tests/models/overfull-gutter.json` reports its `overflow` and its group):
  on 12 seeded models built from `instances.small` with a naive reading-order grid and ≥ 3
  crossings, `search` returns moves, the final score is lower than the start, equals the score of a
  fresh plan of the advised model, and that plan has no error the start did not have; never more
  than 40 plans (count through a wrapper); the same model twice gives the same moves; a model with
  no improving move gives `[]`; `search` leaves its argument untouched.
- [ ] Implement. `bench_routing.py --advice`: time of `search` on the dense scenario, reported
  against 3 s. Amended 2026-09-20: report it also on the twelve seeded models of the test and on the
  shipped examples, per verifying plan and in all; the number decides whether verifying plans stop at
  the better start (spec §6 as amended), which is the owner's call on the measurement.
- [ ] Commit `feat(drawing-diagrams): advice found by a proxy and verified by the router`.

Check: `cd PLUGIN && python3 -m unittest discover -s tests -p 'test_advice.py' -v`; benchmark output.

### Task 16: Advice on stderr, `--no-advice`, reference

Spec: §6 "Output", criterion D3.

**Files:** Modify `SKILL/render.py` (`main` calls `advice.search` once per model, after
`produce` or after the `ModelError`; `failure_map` and `produce` never do), `SKILL/reference/flow.md`,
`SKILL/SKILL.md` (within its 6.7K character limit), `PLUGIN/docs/design.md`,
`PLUGIN/tests/test_render_cli.py`.

- [ ] CLI tests: a model with ≥ 3 crossings prints the block of spec §6 after the warning, stdout
  still exactly the fragment; `--no-advice` prints none; a model nothing improves prints none; with
  `--out-dir` and several models the advice names its model and the all-or-nothing rule holds; an
  error run prints the advice once, after the errors and the map, and still exits 1; `--check` and
  `--format mermaid|ascii` keep their stdout.
- [ ] Implement. Commit `feat(drawing-diagrams): print verified moves with a crossings warning`.

Check: `cd PLUGIN && python3 -m unittest discover -s tests -p 'test_render_cli.py' -v`; golden
identical on stdout.

### Task 17: Does advice pay? (controller, owner)

Spec: §6 "Measured before it is kept", criterion D4.

- [ ] Reuse the harness of the token cost experiment under `.experiments/` (briefs T1–T4, `run.sh`,
  `score.py`, `report.py`, `tools/transcripts.py`); add two briefs that lead to ≥ 3 crossings on a
  first grid. Variants: advice on, `--no-advice`. Three runs each. Report renders per diagram,
  failed renders, `out`, `cr`, final crossings.
- [ ] Owner's decision recorded in `design.md` §14: keep on, make opt-in, or remove.

---

## Stage E — labels (branch `feat/drawing-diagrams-labels`)

### Task 18: The browser probe records label boxes

Spec: §7.4, criterion E1.

**Files:** Modify `PLUGIN/tests/test_browser_lines.py` (`PROBE` and its readers).

- [ ] The probe adds `getBBox()` of every label text (x, y, width, height, relative to the grid
  box) next to the `x`, `y` it records today; existing assertions keep reading `x`, `y`.
- [ ] Test: for `resolver-rules` in both modes every label has a box, and its width is within 15 %
  of `common.label_width` of its text (this is also the first measurement of how far the glyph
  table is from the browser; record the spread in the task report).
- [ ] Commit `test(drawing-diagrams): the browser probe measures label boxes`.

Check: `cd PLUGIN && python3 -m unittest discover -s tests -p 'test_browser_lines.py' -v`.

### Task 19: The occupancy model beside today's code

Spec: §7.1, criterion E2 (first half).

**Files:** Create `SKILL/diagrams/labels.py`, `PLUGIN/tests/test_labels.py`.

**Interfaces:** `labels.Rect(Y, y0, y1, x0, x1, kind, owner)`;
`labels.occupancy(cells, paths, offsets, geo, occupied) -> list[Rect]`;
`labels.overlaps(a, b, cx, cy) -> bool`; `labels.today(i, e, p, …) -> list[Candidate]` — exactly the
places `flow.label_spots` offers today, in today's order; a `Candidate` holds one rectangle per row
it can fall in (spec §7.1), its preference rank and what `flow.plan` needs to emit it.

- [ ] Equivalence test: for the examples, the models of `tests/test_label_lines.py`, and 100 seeded
  labelled instances, the verdict per label (fits, lies on a line or a label, does not fit, with the
  room in px) computed from `today` + `occupancy` + `overlaps` equals what `flow.plan` reports now.
  Disagreements are listed; each is either a defect of the new model or a documented defect of
  today's code (`placed` is consulted only beside a vertical second segment) with its own test.
- [ ] Commit `feat(drawing-diagrams): label occupancy as rectangles, checked against today's verdicts`.

Check: `cd PLUGIN && python3 -m unittest discover -s tests -p 'test_labels.py' -v` and
`cd PLUGIN && python3 -m unittest discover -s tests -p 'test_label_lines.py' -v`.

### Task 20: Switch, new candidates, branch and bound

Spec: §7.2, §7.3, criteria E2 (second half), E3, E4.

This task is kept whole against the split rule: the switch, the candidates and the search share one
data structure and one test file, and splitting them would leave `flow.plan` calling two placement
paths between tasks. Its three commits are reviewed as three passes.

**Files:** Modify `SKILL/diagrams/labels.py`, `SKILL/diagrams/flow.py` (the label loop calls
`labels.place`; `room_beside`, `band_obstacles`, `under_card`, `label_spots` and the post-check are
removed), `PLUGIN/tests/test_labels.py`, `PLUGIN/tests/test_label_lines.py`.

**Interfaces:** `labels.candidates(i, e, p, …) -> list[Candidate]` per spec §7.2, today's places
among them; `labels.cost(choice) -> (label_pairs, line_owners, ranks)` per spec §7.3;
`labels.greedy(...)` — today's order and first fit, over the same candidates;
`labels.place(labelled_edges, …, nodes=20000) -> list[Choice]`; a `Choice` carries the candidate,
its warnings with their owners, or the error with the room and what is in the way.

- [ ] Commit 1, the switch: `flow.plan` on `labels.place` with `today` candidates only. Every test of
  `test_label_lines.py` green unchanged. Golden identical.
- [ ] Commit 2, candidates: tests — a labelled straight exit down in the last column that fails today
  is placed left of its line; a branch label over a horizontal second segment sits after the bend;
  the error of a label that fits nowhere names the card or the line in the way; a line edge hit in
  three rows counts once.
- [ ] Commit 3, search: on 100 seeded labelled instances `cost(place(...)) <= cost(greedy(...))`;
  with `nodes=1` the result is `greedy`'s; the same input twice gives the same choice.

Check: `cd PLUGIN && python3 -m unittest discover -s tests -p 'test_labels.py' -v` and
`cd PLUGIN && python3 -m unittest discover -s tests -p 'test_label_lines.py' -v`;
golden differs only where a label moved after the bend — list the files.

### Task 21: Python emits the anchor, the script draws it

Spec: §7.4, criterion E5.

**Files:** Modify `SKILL/diagrams/flow.py` (edge JSON: `la` replaces `ls`, `ly`),
`SKILL/template/js/flow.js` (label block), `PLUGIN/tests/test_browser_lines.py`,
`PLUGIN/tests/test_label_lines.py` (the class `ScriptOffsets`, which reads numbers out of the
script, goes).

**Interfaces:** `la: [pt, ref, Y, dx, dy, anchor]`, `ref` one of `"p"`, `"m"`, `"r"` (spec §7.4).

- [ ] Browser test (red first): label models that produce every anchor form — the four straight
  exits, a horizontal second segment to the left and to the right, a vertical one on either side at
  its middle and pinned to a row — plus the examples; every label box of task 18's probe lies inside
  the rectangle Python chose, within 2 px, in both modes.
- [ ] Implement the anchor in `flow.js` without a placement rule or a `LABEL_*` number; no comments
  in the fragment.
- [ ] Size: `dg.js` ≤ 10 811 bytes; median CDN fragment ≤ 5 691 characters
  (`RenderCli.test_cdn_fragments_of_the_examples` prints it).

Check: full suite with browser tests.

### Task 22: Stage E review, release, amendment (controller)

- [ ] Owner's pair review of examples and label stress models. `tools/assets.py build`, `check`,
  commit, `REF`, merge commit, `verify-cdn`. `design.md` §14: the occupancy model, the candidates,
  the anchor contract. Branch gate; pull request on the owner's word.

---

## Criteria to tasks

| Spec §10 | Tasks | | Spec §10 | Tasks |
|---|---|---|---|---|
| A1 | 4, 5 | | C2 | 7, 11 |
| A2 | 3, 5 | | C3 | 12, 13 |
| A3 | 1, 4, 5 | | D1 | 14 |
| A4 | 5 | | D2 | 15 |
| B0 | 8 | | D3 | 16 |
| B1 | 8 | | D4 | 17 |
| B2 | 9 | | E1 | 18 |
| B3 | 8, 9, 10 | | E2 | 19, 20 |
| B4 | 9 | | E3, E4 | 20 |
| C1 | 7 | | E5 | 21 |
| every stage | 0, 5, 9, 13, 16, 22 | | | |

The consistency contract of spec §11 is carried by the same criteria; its last row also by task 0.
