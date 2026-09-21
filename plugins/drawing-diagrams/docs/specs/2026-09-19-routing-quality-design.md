# drawing-diagrams: routing and label quality — design

Date: 2026-09-19. Status: accepted by the owner on 2026-09-19, with the defaults of §12. Documents
branch: `docs/drawing-diagrams-routing-quality`; every stage below is implemented on a branch of its
own. Governing base: `main` at `d67f1a50e405d022717b2ba7dcbf82260bbf15ef` (PR #8 merged).

## Stream slots

- **Path:** full cycle. The repository has no `.agents/team-profile.yaml`, so `workflow.full_cycle`
  is the package default; its entry "a moved boundary" matches, because stage E moves the rules of
  where a label is drawn out of `template/js/flow.js` into Python and defines a new Python → JS
  anchor contract. The owner also asked for a spec and a plan (2026-09-19). The gate judges the diff
  of each stage against this spec.
- **Design review before markup:** applies to stage B (line pitch) and stage E (label positions),
  which change how a diagram looks. No `review.design_skill` is declared; the review is the owner's
  pair review of before/after renders of the shipped examples and of the stress models named in §10.
- **Evidence:** named per criterion in §10. `completion.evidence_kind` is not declared, so each
  criterion names a test, a command output, or the owner's recorded word.
- **Performance budget:** measured on 2026-09-19 at the governing base (Apple silicon, CPython 3,
  best of 5) with a scratch generator; task 0 of the plan publishes the generator
  (`tools/instances.py`) and measures the baseline again, and that record is what later stages
  compare with. `flow.plan` on the shipped examples: 2.6–11.2 ms. Dense page scenario (grid 6×7,
  30 nodes, 40 edges, seeds 1–10): routing + offsets + count, median 265 ms, max 302 ms. Budgets:
  every shipped example stays at or below 25 ms; the dense scenario stays at or below 300 ms median
  after every stage; the advice of stage D is bounded by a count of verifying plans, and its time on
  the dense scenario is measured and reported against 3 s. `template/dist/dg.js` is 10 411 bytes and
  grows by at most 400; the median CDN widget fragment of the examples is 5 420 characters and grows
  by at most 5 %.
- **Decision record:** applies — a drawn-crossings invariant, a gutter capacity rule, a routing
  objective and a label anchor contract that later work inherits. `decisions.dir` is not declared;
  per the owner (2026-09-17) the record is an amendment section in
  `plugins/drawing-diagrams/docs/design.md` (§14), written by the stage that introduces each rule.
- **Integration:** not declared in a profile. Pushing a branch and opening a pull request are done
  by the owner or on the owner's word. A stage that changes `template/dist` follows the release
  procedure of `design.md` §13 (merge commit, `REF`, `verify-cdn`).

## 1. Problem and evidence

On 2026-09-18 the engine was compared with published algorithms and open implementations. Every
phase of it is a named problem: `route` is maze routing with bend penalties on a coarse grid (Lee
1961; Wybrow, Marriott, Stuckey, GD 2009), the routing loop is sequential routing with rip-up and
reroute, `assign_offsets` is nudging — metro-line crossing minimisation with the path terminal
property (Bereg, Holroyd, Nachmanson, Pupyrev, "Edge Routing with Ordered Bundles", §6), label
placement is the fixed-position candidate model with a greedy most-constrained-first choice
(Kakoulis, Tollis; Christensen, Marks, Shieber 1995). No library can replace a phase: the Python
side is standard library only, the script is about 10 KB inline, and routing happens before pixel
geometry exists, while libavoid, MSAGL, Graphviz `splines=ortho` and JointJS need node rectangles
first. `elkjs` has no routing-only mode and Graphviz ortho handles neither ports nor edge labels. So
algorithms are taken, not dependencies. Sources are in §13.

What was measured on the engine itself:

- **Drawn crossings differ from counted ones.** Over 1 500 random grids (seed 20260918) the number
  of crossings actually drawn after `assign_offsets` exceeded `router.crossings` in 35.5 % of the
  instances before PR #8 and in 0.9 % after it (13 instances, 23 extra crossings; one instance drew
  fewer). The shipped examples show no difference. Three defects remain, each reproduced at the
  governing base:
  - **A.** In `diagrams/router.py`, `assign_offsets` keys a slot `(axis, line, path)`. A path with
    two runs on one lattice line overwrites its own slot: two lines get the same offset and overlap,
    a crossing is counted and not drawn.
  - **B.** Two runs that meet end to end at a gutter point with their arms pointing opposite ways
    have no order rule. The pair shares no stretch, crosses twice, and `crossings` cannot see it
    (counted 5, drawn 7 in the four-path case).
  - **C.** The orders `firm` and `loose` of `assign_offsets` are keyed `(axis, line, i, j)`. A pair
    with two stretches on one lattice line overwrites its first order with the second (counted 1,
    drawn 3 in the two-path case of §3.1).

  With A and B fixed in a scratch copy — B as the weakest order of §3.2 — 1 500 of 1 500 instances
  agree, and all 14 renders of the shipped examples are byte-identical to today's.
- **A gutter has no capacity.** By `MODES` in `diagrams/flow.py` a column gutter is 28 px in a flow
  widget and holds three lines at the 8 px pitch of `assign_offsets` before a line comes within 4 px
  of a card; the swimlane widget gutter of 18 px holds two. Neither `route` nor any check knows it.
  Graphviz ortho prices a full channel (`CHANSZ`), libavoid shrinks the pitch.
- **Routing has no objective.** The "rip up and reroute" loop of `flow.plan` accepts every reroute.
  Against an explicit sum of the router's own weights, 19–37 % of the reroutes that change a path
  make the sum worse, the second pass is worse than the first in 10–25 % of the instances, blind
  iteration cycles in 35–40 % of medium and large ones, and shuffling the edges in the JSON changes
  2.4–6.3 routes. `Traffic.crosses` and `Traffic.shares` scan every segment on every step;
  dictionary counters give identical paths 3.4–5.6 times faster.
- **"Rearrange the nodes" names no node.** A cheap geometric proxy that picks eight moves, each then
  verified by the real router, matched brute force over all single moves in six of six comparisons
  at 0.08–0.8 s per move, and took random starts from 2–19 crossings to 0–3 in three to eight
  moves. A layered auto-layout prototype lost to the author's grid on all three real examples by
  line length: it does not know which branch of a decision is the main path. Single-attempt LLM
  drawings without crossings succeed in under 2 % of cases at 11–12 edges (PlanarBench, 2026), so
  the quality of the feedback sets the number of iterations.
- **Labels have few places and many special cases.** Four of five path shapes offer a single place
  (`flow.label_spots`), which is why the history is a series of geometric special cases
  (`room_beside`, `band_obstacles`, `under_card`, a separate post-check in `flow.plan`). A label
  over a horizontal second segment sits at its far end (`lx=rt?p2.x-6:p2.x+6` in
  `template/js/flow.js`); ISO 5807, ELK `TAIL`, yFiles `PLACE_AT_SOURCE` and Graphviz `taillabel`
  put a branch label at the source. The drawing rules exist twice, in `flow.js` and as the `LABEL_*`
  constants of `diagrams/flow.py` ("keep the two in step"). The text already has a halo (`.dg-svg
  text` in `template/css/flow.css`: `paint-order:stroke`), so a label on a line stays readable
  today.

The first item was re-measured by the author of this spec on the governing base. The numbers of the
other items come from the research prototypes; the stage that relies on them measures them again
(§10 C1, C3, D2). The design was then put to the gate as a question (design ask, answer digest
`a8d4a970…cb2dddf`); its claims were checked against the code, and what survived is §11.

## 2. Goals and non-goals

Goals:

- **G1.** What the renderer reports is what it draws: no crossing or overlap that `assign_offsets`
  could have avoided, guarded by a test that does not depend on the ordering algorithm.
- **G2.** A gutter never silently overflows onto cards; the author is told which gutter, how many
  lines and how many fit.
- **G3.** Routing minimises a stated objective, terminates, and its routes do not depend on the
  order of edges in the JSON.
- **G4.** A crossings warning names moves that the router has verified.
- **G5.** Label placement is one model with several candidates per label, a branch label sits at its
  source, and the drawing rule lives in one place.

Non-goals:

- No automatic node placement: the author's grid stays the layout (`design.md` §3). Stage D only
  advises.
- No third-party layout or routing library, in Python or in the script.
- No routing or label placement in the browser: errors reach the author before anything is shown.
- No order of a group chosen for its width: slots are reused over the order §3 decides (§4.1a,
  taken on 2026-09-20; until then this list ruled slot reuse out altogether), and an order that
  would make a group narrower is left to the objective of stage C.
- No capacity for lines through cell centres or through banded rows, where `rowY` and `clampY` of
  `flow.js` compress offsets; the browser tests keep their tolerance there.
- No independence of offsets, label choice, warning order or the anonymous section id
  (`assets.section_id`) from the order of edges; G3 promises routes only.
- No label-aware rip-up and no table of label room per exit side in `route`; the `+8` rule stays.
- No change to `schema` routing beyond what `assign_offsets` changes for every caller.
- No replacement of the ordering of PR #8 by a full port of the ordered-bundles algorithm; §8 says
  when that becomes the next step.

## 3. Stage A — what is drawn equals what is counted

### 3.1 Runs own slots and orders

A **run** is a maximal straight piece of one path on one lattice line; consecutive collinear
segments of a path are one run, and a zero-length segment (two equal consecutive points, which
`schema.plan` produces) stays a run of its own, as today. `assign_offsets` groups and orders runs,
and keys both the slot and the pair orders by run, not by path:

- `slot[(i, r)]` for run `r` of path `i`;
- `firm[(u, v)]` and `loose[(u, v)]` for runs `u`, `v` of two different paths: a straight piece of a
  stretch belongs to exactly one run of each path, the one on its line whose interval covers it.

Every original point keeps its index and knows its runs: `ox` comes from the vertical run that
contains the point — the run of the segment ending at it, else of the one starting at it — `oy` from
the horizontal one, `0.0` where there is none. The signature `assign_offsets(paths, step=8,
nodes=frozenset())` and the shape of the result, one `(ox, oy)` per point, do not change, so
`flow.label_spots`, `flow.band_obstacles`, `flow.under_card`, the output loop of `flow.plan`,
`schema.plan.cross_count` and the `offs[1][0]` of `schema.plan` read it as today.

Regression cases (lattice points; nodes are the path ends):

- A: `[(9,1),(8,1),(8,4),(7,4),(7,5),(5,5)]`, `[(7,3),(7,5),(8,5),(8,8),(7,8),(7,9)]`,
  `[(7,3),(7,5),(5,5)]` — today paths 0 and 1 both get `ox = 0.0` on `x = 7`.
- C: `[(3,1),(4,1),(4,3),(2,3),(2,5),(6,5),(6,7),(4,7),(4,9),(5,9)]` and
  `[(5,1),(4,1),(4,3),(6,3),(6,4),(0,4),(0,7),(4,7),(4,9),(3,9)]` — `stretches` gives `(-2, -2)` on
  `x = 4, y ∈ [1, 3]` and `(2, 2)` on `y ∈ [7, 9]`; today both runs of the first path get `+4`.

### 3.2 Runs that meet end to end in a gutter

Two runs `u`, `v` of one group with `u.hi == v.lo` at a point that is not a node, whose arms there
point to opposite sides (`u.hi_side != v.lo_side`, both non-zero): the run whose arm points to the
lower coordinate takes the lower slot. It is applied on each lattice line through the point by that
line's own group, so each corner moves towards its own arms.

The rule is the **weakest** order, a third strength `soft` beside `firm` and `loose`: the group loop
looks for a run free under all three, then under `firm` and `loose`, then under `firm`, then takes
`ranked[0]` as today. It is recorded only where the two runs have no firm or loose order — which is
always, since two runs that meet end to end share no piece of a stretch. It can still close a cycle
with firm or loose orders through a third run. No run of such a cycle is ever free under all three
strengths, so once the runs of the cycle are what remains to place, the pick order falls to `firm`
and `loose`, and the soft order is the one dropped; a run outside the cycle is placed before that
with the soft order honoured. So the rule never displaces a firm or a loose order, and that step of
the pick order is what the guarantee rests on. Measured in a scratch copy: both regression cases
pass and 1 500 of 1 500 instances agree; the invariant cannot see a displaced loose order, so a
hand-made case guards this rule. This is the end-to-end case of `segCmp` in Graphviz
`lib/ortho/ortho.c`, re-implemented from its description; no code is copied.

Regression case B: `[(1,3),(1,4),(2,4),(2,6),(6,6),(6,9),(7,9)]`,
`[(7,5),(4,5),(4,4),(2,4),(2,3),(1,3)]`, `[(1,7),(2,7),(2,3),(3,3)]`,
`[(5,3),(4,3),(4,4),(0,4),(0,11),(1,11)]` — today counted 5, drawn 7.

### 3.3 `drawn_crossings` and `drawn_overlaps`

Two functions in `router.py`. What they count is the displaced orthogonal centreline, per pair of
segments, in integer half-pixel units:

- Every point becomes `(x * BIG + round(2 * ox), y * BIG + round(2 * oy))` with `BIG = 10000`. An
  end that lies on a node is pulled half a lattice step towards its neighbour and takes the
  neighbour's cross coordinate, as `anchor()` in `flow.js` does, so lines that enter one node from
  different sides do not meet at its centre.
- `drawn_crossings(paths, offsets, nodes)` counts strict crossings of a vertical segment of one path
  with a horizontal segment of another.
- `drawn_overlaps(paths, offsets, nodes)` counts pairs of collinear segments of different paths on
  one coordinate whose interiors overlap.

The mapping from lattice to pixels in `flow.js` (`bx`, `by`, `rowY`) is monotone per coordinate, so
a strict crossing here is a crossing in pixels. Rounded corners, arrowheads, clipping, and lines
that `clampX`, `clampY` or a banded row merge into one coordinate are not modelled; they stay the
subject of `tests/test_browser_lines.py`.

### 3.4 The invariant and its test

For every set of paths the router can produce, with `offs = assign_offsets(paths, nodes=nodes)`:

> `drawn_crossings(paths, offs, nodes) == crossings(paths)` and
> `drawn_overlaps(paths, offs, nodes) == 0`.

A property test routes seeded random instances as `flow.plan` does (at least 300 instances from the
published generator, fixed seeds, under 20 s) and asserts the invariant, printing the smallest
failing instance as paths. It depends on `route_all`, `assign_offsets`, `crossings` and the two
counters only, so it guards any later ordering algorithm as well. A failure is a defect of the
renderer, never a message to the author.

### 3.5 What `flow.plan` reports

`layout["crossings"]` and the warning "пересечений линий: N" use `drawn_crossings`. With the
invariant they are the same number; without it the author is told what the reader sees.

### 3.6 Docstring

`route` says "+4" for passing through another line's corner; the code and the tests use `+3`. The
docstring is corrected.

## 4. Stage B — gutter capacity

### 4.1 Model

Capacity applies to even lattice lines: inner gutters and the outer margins. Its unit is the
**group** of `assign_offsets` — the runs on one line that overlap or meet end to end in a gutter —
because a group of `w` runs is drawn `w` slots wide whatever its load at any one point.

For a group of `w` runs at pitch `s` the outermost line lies `(w − 1) · s / 2` from the lattice
line. The group fits when that line keeps `LINE_CLEAR = 4` px from the nearest card edge and
`EDGE_CLEAR = 1` px from the edge of the grid box. The room on each side comes from `Geometry` and
the mode tables (`MODES`, `BASE_MODES`): `gap / 2` in a column gutter, `row_gap / 2` in a row
gutter, and in the left and right margins `Geometry.margin` towards the cards and `pad − margin`
towards the box. At `gap` 28 that is 3, 4 and 5 lines at 8, 6 and 5 px; at `gap` 18, 2, 2 and 3; in
a widget side margin (12 px and 6 px), 2, 2 and 3.

The top and bottom margins are not like the side ones — `.dg-grid` in `template/css/base.css` pads
8 px vertically, so `by` of `flow.js` puts an unoffset margin line 4 px (widget) or 10 px (page)
outside the grid box, above it and below it. Their room was an assumption of this design until the
first task of the stage measured it in the browser harness (2026-09-19), and the measurement
replaced it: the bound of such a line is not the grid box, which does not clip (`.dg-svg` is
`overflow:visible`), but what actually clips or covers it. Above the box that is the section's top
edge in a widget and the title in a page, so a flow's top margin holds no line at all; a swimlane's
top margin lies a row gap under the lane headers and holds 4 lines (widget) or 6 (page). Below the
box it is the first content after the grid — the footnote list when the model has one, else the
legend's text — so the bottom margin holds 3 lines in a widget and 1 in a page, 2 and 0 under
footnotes. `flow.TOP_ROOM` and `flow.BOTTOM_ROOM` carry the measured px and a browser test holds
them against the page. More vertical padding in `.dg-grid` would give these margins real room; it
is a template change with a CDN release behind it and is the owner's to take, not this stage's.

### 4.1a Slots are reused (amendment, 2026-09-20, by the owner's word)

The first measurement of the capacity check showed the unit above to be wasteful, not wrong. On 500
seeded grids the check refused 99 (flow widget), 127 (flow page), 231 (swimlane widget) and 111
(swimlane page) plans, almost all of them on column gutters, and 57–76 % of the refused groups
would fit by the load at their busiest point: a chain of six runs was drawn six slots wide with two
lines side by side anywhere.

So the width of a group is the number of slots it is drawn in, not the number of its runs. The
order of a group is decided as in §3; then each run, in that order, takes the lowest slot above
every earlier run it **lies beside** — shares a stretch with, or meets end to end in a gutter.
Two runs that never lie beside each other may share a slot. Every pair that does lie beside each
other keeps the relative order it had, and only such pairs can cross or overlap, which is why the
invariant of §3.4 holds unchanged; the property test is the guard, as for any ordering. The pitch
of §4.2, the check of §4.4 and its message, and `overfull` all use that width.

Measured with a prototype before it was specified: the invariant held in the 900 surveys of the
property test and in 2 000 routings of another generator, all 14 renders stayed byte-identical, and
the refusals fell to 54, 86, 173 and 75. The bound by the busiest point is 29, 56, 130 and 47; the
rest is held by the orders of §3, and an order chosen for width is left to the objective of stage C.

### 4.2 Adaptive pitch

`assign_offsets` takes the room per line as an optional argument and picks, per group, the first
pitch of `8, 6, 5` px that fits, else the smallest. Without the argument — `schema.plan` passes none
— offsets are today's. The offsets already reach the script as pixels in `path[i][2..3]`, so
`flow.js` does not change. Groups that fit at 8 px, every group of the shipped examples among them,
keep today's offsets.

### 4.3 Router cost

`Traffic` counts runs per unit edge of an even line. A step along a unit edge whose load is already
the capacity at the smallest pitch costs `+20`, more than a crossing. This is a heuristic of the
proposer: it makes overflow rare and guarantees nothing; §4.4 is the guarantee.

### 4.4 Check and message

A group that does not fit at 5 px is a layout error (it prints the map, `--draft` downgrades it):
"между столбцами 2 и 3 линий 5, помещается 3: a -> d, c -> b, …; освободите ячейку рядом или
переставьте узлы". Rows and margins are named the same way ("между рядами", "по левому полю"). Per
Q1 of §12 it is an error. The noun comes first in the genitive plural, as in the renderer's other
messages ("узлов 17"), because the first wording of this design, "идут 5 линий", is not Russian for
1 to 4 lines; columns and rows count from zero, as those messages count them; the count is the
width of the group, the list names at most four edges; and where the line holds nothing (§4.1) the
advice is to move the nodes so the edges run elsewhere, since no freed cell would help.

## 5. Stage C — routing with an objective

### 5.1 Fast `Traffic`

`Traffic` keeps reference counts (points strictly inside horizontal and vertical segments, unit
edges, corners, exits, entries) with `add` and `remove`. `crosses`, `shares` and corner membership
stay booleans for `route`: two earlier lines on one step cost one surcharge, as today. Same
interface, identical paths; it ships first and alone, and the golden outputs do not move.

### 5.2 Objective

```
Φ(P)   = Σ own(p) + Σ_{p<q} pair(p, q) + 20 · overflow(P)
own(p) = the cost `route` gives p with no traffic: steps, turns after the first step, empty cells
         other than the target, margin steps, +8 leaving through the top on the first step, +4
         entering from below on the last, +8 for a labelled edge — a label or a footnote — whose
         first step goes sideways towards an occupied neighbour cell
pair   = 10·(perpendicular crossings + shared_swaps) + shared unit steps
       + 3·(inner points of one on corners of the other, both ways)
       + 3·[same exit side of one node] + 3·[same entry side of one node]
overflow = Σ over the groups of §4.1 of max(0, w − capacity)               (0 before stage B)
```

`own` is defined by replaying `route`'s step rules, and a test holds it equal to the cost `route`
itself reports. `pair` is a different thing from `route`'s traffic surcharges and is meant to be: it
charges per pair where `route` charges per step, it counts `shared_swaps`, which `route` cannot see,
and its corner term is symmetric where `route`'s is one-way. `route` stays the proposer; Φ decides.
Φ is pairwise additive apart from `overflow`, which is recomputed for the lattice lines the old and
the new path touch.

Amended 2026-09-20, after stage B landed, which this section was written before:

- `own` replays one price more. `route` charges +20 for a step along a line that holds nothing (a
  flow's top margin, a page's bottom margin under footnotes, a line squeezed by empty rows) with or
  without traffic, so `own` carries it and stays equal to the cost `route` reports on the lattice
  `flow.plan` builds. The +20 of a line that is full because of the lines on it depends on traffic
  and is no part of `own`: Φ sees fullness through `overflow`.
- `overflow` counts slots: Σ max(0, width − capacity) over the groups `router.overfull` names, with
  the width of §4.1a.
- The width of a group depends on the orders of its runs, so `overflow` cannot be read off a table
  of loads. ΔΦ recomputes it on the lattice lines where the old or the new path has a run, from the
  groups, orders and slots of those lines alone — the pair orders of the paths that have runs there
  — and never from the whole routing: the descent asks once per proposal, and a whole-routing
  `overfull` costs a scan of every pair of paths.

### 5.3 Orchestration

1. Canonical order: edges sorted by (Manhattan length, source point, target point, labelled), the
   model index only between edges equal in all four — which are the same routing problem.
   Amended 2026-09-20 (task 12): the long edges come first. This text gave the key and not its
   direction; measured against the old loop on the 100 instances of C3, long-first is at or under
   its Φ on 93 (no room) and 97 (room) of them, short-first on 90 and 95.
2. Two starts, always completed: greedy in canonical order with accumulating traffic, and every edge
   routed alone.
3. Descent from each start: for each edge in order, remove it, reroute it against the rest, accept
   the new path only if ΔΦ < 0, put the kept path back. Repeat until a pass changes nothing, at most
   eight passes. The descents share a budget of 600 `route` calls, half each, the second taking what
   the first left; when it runs out the current routing, which is always complete, is kept.
4. The lower Φ wins; on a tie the fewer crossings, then the lower Σ own — the routing whose lines
   are each nearer their own best — and the first start only when all three tie. (Amended
   2026-09-20, twice. Crossings come first because a tie of Φ can hide one: a fixture of
   `tests/test_label_lines.py` ties at Φ 82 with one routing crossing once and the other not at
   all, the crossing paid for by 6 of `own` and 4 of `pair`, and Σ own alone picked the crossing. The first text gave
   the tie to the first start. On the shipped `verdict-row-lifecycle` the two descents end at Φ 60:
   the greedy one sends `none -> declined_retry` out through the bottom of its card and along the
   gutter under the label of `none -> approved`, which draws a label warning; the other one, which
   is also what the old loop drew, leaves through the side. Φ knows nothing of labels until
   stage E, and Σ own is 53 against 52. Over 600 plans of 300 seeded labelled models the rule moves
   neither the label warnings, 1 148, nor the crossings, 5 466.)

Φ falls strictly with every accepted change, so the loop ends and cannot cycle, and the result is
never worse than the better start. Pair moves (rip up two crossing edges and try both orders) are
left out: they cost four `route` calls per crossing pair for about 2 % of Φ.

### 5.4 Determinism

No `random`, no clock in the logic, integer costs, iteration over sorted integer keys only. Two runs
on one model give identical output. The same model with `edges` shuffled gives the same route for
every (source, target, labelled); label choice and the section id may still follow the model order
(§2). Amended 2026-09-20: offsets follow the canonical order as the routes do, apart from edges that are
the same routing problem, whose order stays the model's. They have to: the width of a group depends on
the order the paths are placed in, so a routing is placed in the order the search priced it in
(`router.place`), or Φ would price one drawing and the page show another. The first text let offsets
follow the model order; the branch gate of stage C found what that costs.

## 6. Stage D — rearrangement advice

Triggered by `render.main`, once per model, when a plan has an unroutable edge, a group over
capacity, or three or more crossings; never from inside `flow.plan` and never from
`render.failure_map`, which plans again. `flow.plan(…, draft=True)` exposes what the search needs in
`layout`: `unroutable` (a count — today a draft plan drops such edges and reports the crossings of
the rest) and `overfull` (the groups of §4.4). The score of a grid is the tuple (unroutable,
overflow, crossings, total length), compared lexicographically (amended below: no `unroutable`).

Amended 2026-09-20, after stages A to C landed, which this section was written before:

- **No `unroutable`.** A grid of cards cannot wall an edge in: cards sit on odd lattice points and
  the gutters between them are never blocked, so `route` always finds a way (found in stage A; the
  "нет маршрута" branch of `flow.plan` is kept as a guard and cannot be reached from a model). The
  trigger is a group over capacity or three or more crossings, and the score is the tuple
  (overflow, crossings, total length). `overflow` is what Φ counts: the slots over capacity of the
  groups `router.overfull` names (§4.1a, §5.2). `flow.plan(…, draft=True)` puts that number and the
  groups into `layout`; nothing else of `layout` changes.
- **What a verifying plan costs.** A plan now routes with the search of §5.3: a few ms on the
  shipped examples, about 200 ms on the dense scenario, so 40 verifying plans there are about 8 s
  against the 3 s this design asked the advice to be reported against. The stage measures it on
  the dense scenario and on models of the size authors write; if the measurement says so, the
  first lever is a verifying plan that stops at the better start (`route_all(budget=0)`), with the
  advised grid planned in full once at the end, and the owner rules on the number.
- **The capacity error gets its move.** The advice answers the error of §4.4 as well as the
  crossings warning: "переставьте узлы" is then a verified move, not a wish.
- **What the author is asked to do** (amended 2026-09-21, after the stage's gate and qa review). The
  search climbs on the whole score, length included, because a move that only shortens the lines
  can open the way to one that removes a crossing. The author is not asked for the cosmetic ones,
  though: the advised sequence ends with the last move that lowers overflow or crossings, and the
  moves after it are dropped (on 9 of the 12 seeded models of D2 a sequence ended in up to three
  moves reading "0 → 0"). Every step of the block names the term of the score it moved, so a step
  inside the sequence that only shortens the lines says so instead of printing a count that stands
  still.
- **No new warning either.** A move is dropped if its plan carries a layout error the start did not
  have — the first text — or more warnings than the start, the crossings warning aside: `SKILL.md`
  tells the author to treat a warning as an error, and on 2 of the 12 seeded models the advice
  handed over a grid with an empty-row warning the author's own grid did not have.
- **A lane order is printed with its lanes.** A `lanes` move changes `lanes` and `grid` together, so
  the block prints both; pasting the grid alone would hand cards to other lanes.
- **The downward rule is the one above, not a stricter one.** A move may lay the two cards of a
  downward edge in one row; what it may not do is put the target above the source, and judging
  every produced grid against the original's downward edges is what keeps a later move from
  turning that row upward. (Task 14 first read it strictly, target below source; the branch gate
  showed what that costs: on the first seeded model (0, 1, 102) where the spec's rule reaches
  (0, 0, 90).)

- **Moves:** swap two nodes, or move a node into an empty cell, inside the existing grid size; every
  move is applied to a deep copy of the original model (`flow.plan` writes `_note` and `_text` into
  nodes) and changes `grid` only. Tried in order of how little they disturb the reading: inside one
  row, then to the adjacent row, then the rest. A move is dropped if it puts the target of an edge
  that runs downward in the **original** grid above its source, or takes a node without incoming
  edges out of the first row; both rules hold for the whole sequence of moves, not per move.
- **Swimlane:** nodes never move on their own (a column is a lane, a row is a moment); the only move
  is a permutation of `lanes` that moves the grid columns with them, searched exhaustively (5! or 7!
  proxy scores).
- **Search:** a proxy ranks the moves — 10 · crossings of straight lines between cell centres,
  6 · nodes lying on the straight line of an edge in one row or column, 3 · edges going up, plus
  Manhattan length; the best eight are verified by a draft plan, and the best one is taken if its
  score is strictly lower and its plan reports no error the start did not have. Hill climbing for at
  most eight moves and at most 40 verifying plans in all. Ties go to the earlier node in the model.
- **Output:** stderr, after the warning or the error, as advice and never as a change to the model;
  stdout, exit codes, `--check`, `--format` and the all-or-nothing of `--out-dir` stay as they are:

  ```
  совет: пересечений 5 → 1 за 2 хода (проверено трассировкой)
    1. поменять местами wait и declined (ряд 3): 5 → 2
    2. перенести retry в пустую ячейку [4, 2]: 2 → 1
  grid:
    "start  .      ."
    …
  ```

  Nothing is printed when no move improves the score. `--no-advice` suppresses the search (Q2).
- **Measured before it is kept:** whether it saves tokens is unknown. The experiment of §10 D4
  repeats the method of the token cost design (headless runs, `tools/transcripts.py`), and the owner
  decides on its report.

## 7. Stage E — labels

### 7.1 One occupancy model

Every drawn object yields rectangles `(Y, y0, y1, x0, x1, kind, owner)`: `Y` a lattice row, `y`
relative to the base of that row as `base()` in `flow.js` computes it, `x` in px from `Geometry`;
`kind` is `CARD`, `LINE`, `LABEL` or `BOUND`. Card heights are unknown in Python, and the model
keeps that uncertainty instead of guessing: a card is `(-∞, +∞)` in its row; a vertical run yields
one rectangle per row it passes, half a row at its ends; a horizontal run yields its offset ± 1,
widened by the clamp tolerance in a banded row; a label whose place depends on heights — beside the
middle of a vertical second segment, or under a short card — yields a rectangle in every row it can
fall in. A candidate that hangs from its own source card — a straight exit down or up — is not
tested against that card, which it lies below or above by construction, nor against the lines that
leave or enter the card within its height; it is tested against the other cards of the row and the
lines drawn at their height, as `under_card` does today. One predicate tests two rectangles of one
row for overlap with a clearance. `half`, `reach`, `horizontal`, `under_card` and the post-check of
a label over a horizontal second segment become values of `y0`, `y1`, not branches of the checking
code.

Amended 2026-09-21, after stages A to D. The lines of the model are the offsets `router.place`
answers (§5.4), so they stand at the pitch of their group: 8, 6 or 5 px (§4.2). At the two tighter
pitches the neighbour of a label's own line lies inside `LINE_REACH` of the middle of the text, and
the model says so as today's check does since stage B; what takes a label out of such a group is
the choice of §7.3, not a shorter reach. A row of the grid that holds no card has, inside the drawn
extent, a band of invented tracks (`design.md` §14, stage B): its rectangles are relative to the
same `base()`, and the lattice the model covers ends with the last occupied row, as the paths do.
`BOUND` is what today's code keeps a text inside: the left edge and `Geometry.total` across, and
the side of a line in an outermost lattice column that faces out of the grid box.

Amended 2026-09-21, with the model built (task 19) and read against the browser. Three readings
the sentences above left open are settled as the model has them.

- The clamp tolerance sits on the text, not on the line. The script clamps the lines of a banded
  row and a text drawn from a point of that row together, so only their order survives: a text on
  the base of a banded row covers the whole row, and a text above its own line at a sideways exit
  covers everything above that line's top edge. Both answer as today's code does.
- In a row a vertical second segment ends in, the text at the middle of the segment lies past the
  bend drawn there, half a lattice row away, and covers the row past that line and no more. Today's
  code reads such a row the other way round — every line that crosses it counts wherever it stops,
  no line along it counts wherever it runs. This is the one class in which the fit verdicts of the
  two differ: 5 of 100 seeded instances move a label, the examples and the label cases none. The
  model's reading is the stage's.
- The check of a label over a horizontal second segment tests the text's own rectangle. Today's
  tests the whole segment, and the browser says what that is worth: over the 171 such labels of
  the seeded corpus it warns of 133 lines of which 7 run through the drawn text, and misses 35 of
  the 42 that do; the rectangle warns of 36, of which 32 do. Over all 442 labels today's code
  raises 58 false alarms and misses 20 struck labels; the model 11 and 10.
- Amended again the same day, after the second round of the branch gate: a vertical run that ends
  at a bend ends where the bend is drawn — the offset of that point — and not at the base of the
  row. "Half a row at its ends" read a run turning 12 px above the middle of a gutter as reaching
  the middle, which invents a line through a text standing there and hides one from a text standing
  past the base; 634 of the 1 168 such ends of the seeded corpus are drawn off the base. Where the
  row is banded, or the run ends on a card, the height is unknown and the half row stays.

### 7.2 Candidates

All of today's places stay candidates, in today's order of preference, and new ones are added:

| Shape of the route | Candidates, preferred first |
|---|---|
| straight down or up | right of the line, left of the line (new) |
| straight sideways | above its line, below its line (new) |
| second segment horizontal | above it just after the bend (new), below it just after the bend (new), above it at its far end |
| second segment vertical | beside its middle right, left; then, per row the segment passes, pinned to that row right, left, rows by distance from the middle |

"Just after the bend": the text starts `LABEL_BEND` px past the bend and grows away from the source.
It moves the label of every horizontal second segment, short or long (Q4).

Amended 2026-09-21: "above" and "below" a horizontal second segment are read from the segment as it
is drawn, not from the base of its row. Today's script hangs the text 9 px over `base(Y)` whatever
the segment's own offset, so a segment drawn 9 px or more above the base runs through its own
label: 8 of the 171 such labels of the seeded corpus, read off the browser, and 15 more have the
line on their baseline. With the new places of this table every place over or under a horizontal second segment
is anchored to the drawn `y` of the segment (`ref` `"p"`, §7.4), today's far end among them.

### 7.3 Choice

A candidate that overlaps a card or the bounds is dropped; if none is left, the error names the room
as today, and the card or the line in the way. The cost of a choice of candidates is the tuple
(pairs of chosen labels that overlap, line owners overlapped, sum of preference ranks), compared
lexicographically; a line edge counts once per candidate however many of its rectangles are hit, and
a label's own supporting segment is not counted. Labels whose candidates can overlap form
components; each is solved by branch and bound in most-constrained-first order. The starting bound
is today's greedy choice over the same candidates under the same cost, which is always complete; the
search has 20 000 nodes per plan, spent on components in model order, and returns the best complete
choice found, so the result is never worse than greedy and is deterministic. Warnings keep their
wording.

Amended 2026-09-21, after stage D: and their number. `advice.evaluate` (§6) counts the warnings of
a plan and drops a move that leaves the author with more of them, so a label raises what it raises
today: one warning when it lies on a line or on a label, one per line that crosses a label over a
horizontal second segment, one per pair of labels in one place. A new place follows the family it
belongs to — after the bend is over a horizontal second segment, the other new places are beside a
line. A model that warned once per owner overlapped would change which moves the advice offers.

Amended 2026-09-21, before the search (task 20 commit 3), on what the browser showed after the
candidates landed. The cost reads every place against every rectangle it shares a row with; the
families of today's code differ in how a warning is worded, not in what is looked at. Today a label
on a horizontal second segment is measured against no line along its row and against no label, and
only a label beside a vertical second segment against the labels placed before it: of the 9 labels
of the seeded hundred a line or a label runs through while the plan says nothing, 8 are of that
family. So a label on a horizontal second segment that lies on a line along its row or on another
label raises the one "ляжет на другую линию или подпись" it would raise anywhere else, beside one
"пересечёт" per line that crosses it; a pair of labels that overlap in the choice the search
returns is told about once, on the later of the two in the model's order, as the same place when
it is the same place. The count of warnings can therefore grow where today's code looked away,
and criterion E6 is where each such instance is named.

### 7.4 Python emits the anchor, the script draws it

Each labelled edge carries `la: [pt, ref, Y, dx, dy, anchor]` instead of `ls` and `ly`. `x` is the
drawn `x` of point `pt` of the path (0, 1 or 2) plus `dx`. `y` is `dy` plus the reference `ref`:
`"p"` the drawn `y` of that point, `"m"` the middle of the second segment, `"r"` `base(Y)` of
lattice row `Y` (`Y` is `0` otherwise). "Drawn" means after `rowY`, `clampX`, `clampY` and
`anchor()`. `anchor` is `start` or `end`. These cover every place of today — the four straight
exits, a horizontal second segment either way, a vertical one on either side at its middle or pinned
to a row — and the new ones of §7.2. The label block of `flow.js` applies the anchor and holds no
placement rule; the `LABEL_*` numbers live in Python only. The probe of the browser harness, which
records the `x`, `y` of a label today, records its box, and a test compares the box with the
rectangle Python chose.

Assumption: a fragment with `la` is drawn by the script built with it. A chat widget pins its build
by `template/dist/REF` and is its own document; a page carries its script inline. Two fragments of
different builds in one document would share the first script loaded (`__dgInit` in `head.js`); that
case is not supported.

## 8. Rejected alternatives

- **A layout or routing library** (libavoid-js, msagljs, elkjs, Graphviz WASM): hundreds of KB
  against a 10 KB script, LGPL for libavoid, and all need rectangles before routing, which would
  move routing into the browser and lose errors before display.
- **Automatic node placement** (layered, topology-shape-metrics): no width budget, scale-to-fit, and
  no knowledge of the main path; it lost to the author's grid on every real example.
- **A full port of the ordered-bundles ordering now.** PR #8 already follows the same principle; the
  three defects are local. The port (Bereg et al. §6.1 with the look directions of Hegemann and
  Wolff, GD 2023, about 120–160 lines, no cycles by construction) becomes the next step if the
  property test of §3.4 finds a failure that comes from the `loose → firm → ranked[0]` fallback or
  from the scalar `pref`.
- **A layout error for an ordering the renderer cannot resolve.** The author cannot act on it; the
  property test is the guard, and the port above is the remedy.
- **Negotiated congestion history costs** (PathFinder): they are multipliers for hard capacities;
  ours are soft, and a soft analogue measured no better than two starts.
- **ILP, simulated annealing, more than two starts:** a solver or randomness for 1–3 % of Φ; best-of
  many is less stable under small edits.
- **Visibility graphs, A\* heuristics, VPSC:** answers to arbitrary coordinates and thousands of
  nodes; on a lattice of at most 15 columns Dijkstra visits everything sooner.
- **Label placement in the browser:** exact geometry, but no error before display.
- **A text halo as part of this work:** it is already there.

## 9. Risks

- **Existing diagrams change.** Stage A changes offsets only where a defect applied (none in the
  examples). Stage B changes pitch only in groups that do not fit today. Stage C can change any
  route: every example is re-rendered, its crossings may not rise, and the owner reviews the pairs.
  Stage E moves every label over a horizontal second segment.
- **A capacity error stops a diagram that rendered yesterday.** It rendered with lines on cards; the
  router cost makes the error rare, `--draft` still renders, and Q1 can make it a warning. A chain
  of runs that only meet end to end was counted as wide as it was long; it proved common on the
  first measurement, and slot reuse was taken into the stage (§4.1a).
- **The objective trades a crossing for other costs.** Crossings carry 10 against 1–3 for the rest;
  the acceptance of §10 C3 forbids more crossings on the examples.
- **Large models.** Nothing limits the number of edges or rows (`flow.plan`, `grid.parse_grid`); a
  model with 300 edges spends the starts alone beyond 600 calls. The starts always complete, the
  descent stops at its budget, and time grows linearly with edges.
- **Advice costs more tokens than it saves, or more time than 3 s.** It is measured before it is
  kept (§10 D2, D4) and can be switched off.
- **The label refactor is large.** It is staged: the model beside the old code with an equivalence
  test, then the switch, then new candidates, then the anchors.
- **Python and the browser disagree on geometry.** Unchanged by this design; the browser harness
  stays the check.

## 10. Done when

Stage A
- A1. The cases A, B and C of §3 are tests that fail at the governing base and pass, and the cycle
  case of §3.2 — the end-to-end rule gives way to the orders it closes a cycle with — is a test that
  fails without the `firm` and `loose` step of the pick order: test names in
  `tests/test_crossings.py`.
- A2. The property test of §3.4 passes on at least 300 instances in under 20 s: test output.
- A3. Every shipped example renders byte-identical HTML in both modes before and after the stage:
  command output of the golden comparison.
- A4. `layout["crossings"]` is `drawn_crossings`: a test. The docstring of `route` says `+3`: the
  diff.

Stage B
- B0. The room of the top and bottom margins is measured in the browser harness and recorded in the
  amendment: test output.
- B1. Five runs in one column gutter get the 6 px pitch at `gap` 32 (flow, page) and fail with the
  message of §4.4 at `gap` 18 (swimlane, widget); three runs keep 8 px at `gap` 28: tests.
- B2. At capacity no line touches a card or is clipped: `tests/test_browser_lines.py`.
- B3. Shipped examples byte-identical: command output. Owner's pair review of two stress models.
- B4. Where a detour cheaper than 20 exists, the router leaves a gutter at its capacity instead of
  adding a line to it: a test on a hand-made grid.
- B5. Two runs of one group that never lie beside each other share a slot, the width of a group is
  its slot count, and the pitch, `overfull` and the message use it: `tests/test_capacity.py`; the
  invariant of A2 stays green and the shipped examples byte-identical.

Stage C
- C1. Fast `Traffic` gives identical paths on the property-test instances: a test; `route` at least
  three times faster on the dense scenario: benchmark output.
- C2. `own` equals the cost `route` reports; Φ equals the direct count of its terms; ΔΦ equals the
  difference of two full sums; `remove` after `add` leaves `Traffic` empty: tests.
- C3. On the examples and on 100 seeded instances: Φ not above today's orchestration in at least
  90 % of the instances, crossings not above on the examples, identical routes per edge for shuffled
  `edges`, identical output for two runs on one model, never more than the budget of `route` calls
  in the descents: tests. Dense scenario median at or below 300 ms: benchmark output. Owner's pair
  review of the examples.
  Amended 2026-09-20: the asserted reading is the one production runs — capacities, room, and
  every third edge labelled as the suite labels them (97 of 100). Without room the unlabelled
  reading is 93 and the labelled one 89, one instance under the mark; `route_all` is never called
  without room outside tests and tools, and all four readings are recorded in the test.

Stage D
- D1. Moves respect the rules of §6 (deep copies, downward edges of the original grid, first row,
  lanes with their columns): tests.
- D2. On 12 seeded instances the advised grid has a lower score than the start, verified by a fresh
  plan, with no new error, within 40 verifying plans: a test. Time on the dense scenario: benchmark
  output against 3 s.
- D3. Output format, silence when nothing improves, `--no-advice`, advice exactly once on an error
  run, stdout and exit codes unchanged: CLI tests.
- D4. Headless benchmark with and without advice on the four tasks of the token cost experiment and
  two tasks that raise the crossings warning: report with renders per diagram and output tokens;
  the owner's recorded decision. Amended 2026-09-21, as run: the owner cut it to the edit task of
  the token cost experiment and the two new tasks, three pairs each, and the first pair of each
  showed that the edit task and the new flow never reach the trigger, so neither can tell the
  variants apart; they ran once, and a constructed edit of a model that already crosses 15 times
  took their place. Sixteen sessions; the report is `design.md` §14.

Stage E
- E1. The browser probe records label boxes: `tests/test_browser_lines.py`.
- E2. The occupancy model gives the same verdicts as today's code for today's candidates on the
  examples, on the models of `tests/test_label_lines.py` and on seeded instances: an equivalence
  test, then the old functions are removed.
- E3. New candidates: a label at the right edge of the diagram that fails today is placed left of
  its line; a branch label sits after the bend; an error names the card or the line in the way:
  tests.
- E4. Branch and bound never costs more than greedy on seeded instances, and returns greedy when its
  node allowance is one: tests.
- E5. `flow.js` holds no `LABEL_*` number; the browser harness finds every label box inside the
  rectangle Python chose, within 2 px, for every anchor form: `tests/test_browser_lines.py`. Size
  budgets of the slots hold: command output. Amended 2026-09-21, after the branch gate: "inside"
  is both ways — across, and down the page wherever Python's bounds are finite, in the browser's
  own frame — and the far edge of the text is allowed 5 % of its width on top of the 2 px. Python's
  width is the glyph table's estimate (E1 measures it 2.3 % off on the one example it reads), so
  2 px cannot hold at the far end of a long text; the near edge and both bounds down the page keep
  the 2 px.
- E6 (added 2026-09-21, after the D4 experiment, whose dearest sessions went to label warnings and
  to nothing else). Over the seeded labelled instances of E4 the number of label warnings and of
  labels that do not fit, today's code against the stage's: a table in the stage report and in
  `design.md` §14. An instance where either number grew is traced to a check today's code does not
  make — `placed` is consulted only beside a vertical second segment — or is a defect.

Every stage: `python3 -m unittest discover -s tests` green, `claude plugin validate` clean, the
amendment to `design.md` §14 written, the performance budgets of the slots measured and recorded.

## 11. Consistency contract

From the design ask; every class was reproduced on the governing base by its probe. "Carried by"
names the criterion that proves the guarantee.

| Class | Guarantee | Closer | Carried by |
|---|---|---|---|
| Run identity does not survive the offset interface | every point knows its runs; signature and result shape unchanged; schema reads as today | one run table with point membership (§3.1) | A1, A3 |
| Local order rules need not give one complete order | the end-to-end rule never displaces a firm or loose order | the rule is the weakest strength and is dropped where it closes a cycle (§3.2); a hand-made cycle case guards that, the invariant the rest | A1, A2 |
| Abstract and browser geometry are different objects | the counters claim centrelines only; margins top and bottom are measured, not assumed | §3.3 scope; measurement of §4.1 | A2, B0, B2 |
| Capacity has two units | capacity, the check and `overflow` all use the groups of `assign_offsets`; `+20` is a heuristic | §4.1, §4.3, §5.2 | B1, B4, C2 |
| The objective is not the router's cost | `own` is `route`'s cost by replay; `pair` is declared different; fast `Traffic` keeps boolean semantics | §5.1, §5.2 | C1, C2 |
| Canonical order is narrower than the output | the promise is routes per (source, target, labelled) only | §2 non-goal, §5.4 | C3 |
| Advice can break the model | deep copies; rules against the original grid; lanes move columns; no new error | §6 | D1, D2 |
| Advice is coupled to the planner's failure path | the draft plan exposes `overflow` and `overfull`; `render.main` alone calls the search, once | §6 | D3 |
| The anchor contract is incomplete | tagged `ref`, "drawn" defined, every place covered, box measured | §7.4 | E1, E5 |
| The label optimiser's bound is undefined | lexicographic cost, owner counting, greedy incumbent over the same candidates, best complete on exhaustion | §7.3 | E4 |
| Work exceeds the stated envelope | starts complete, descent budget shared, advice bounded in plans, label search per plan, generator published | §5.3, §6, §7.3, slots | C3, D2, E4, task 0 |

## 12. Resolved questions

The owner took the default of each on 2026-09-19.

- **Q1.** A group over capacity: layout error (default) or warning?
  Settled by the owner on 2026-09-20 after the pair review of stage B: it stays an error, with the
  slot reuse of §4.1a taken into the stage before its pull request; the wording of the message and
  its zero-based numbering stay as built (§4.4). Two alternatives were put to the owner and are not
  taken now: more vertical padding in `.dg-grid` (§4.1), and removing fully empty rows from the grid
  before layout, which would retire the band rules of `design.md` §14 at the price of changing how
  such models look.
- **Q2.** Advice: on whenever it is triggered, with `--no-advice` (default), or opt-in `--advise`?
  Settled by the owner on 2026-09-21 on the report of the D4 experiment (`design.md` §14): on
  whenever it is triggered, with `--no-advice`. The rule that a move which leaves the author with
  more warnings is not offered (§6) stays as built, with its measured price known: two of the three
  runs of the swimlane task with advice were offered nothing at three crossings.
- **Q3.** Order and cut of the stream: A, C fast `Traffic`, B, C, D, E, each a pull request of its
  own (default); or stop after C and decide on D and E from its results?
- **Q4.** "Just after the bend" moves the label of every horizontal second segment in existing
  diagrams. Preferred (default), or second to the far end?
- **Q5.** The six research reports of 2026-09-18 are outside the repository. Keep them out, with the
  sources in §13 (default), or commit them under `docs/research/`?

## 13. Sources

- Bereg, Holroyd, Nachmanson, Pupyrev. Edge Routing with Ordered Bundles. arXiv:1209.4227.
- Fink, Pupyrev. Metro-Line Crossing Minimization: Hardness, Approximations, and Tractable Cases.
  arXiv:1306.2079.
- Wybrow, Marriott, Stuckey. Orthogonal Connector Routing. GD 2009.
  https://users.monash.edu/~mwybrow/papers/wybrow-gd-2009.pdf
- Hegemann, Wolff. A Simple Pipeline for Orthogonal Graph Drawing. GD 2023. arXiv:2309.01671.
- Graphviz `lib/ortho/ortho.c` (`segCmp`, `CHANSZ`), EPL-2.0 — ideas only.
  https://gitlab.com/graphviz/graphviz/-/tree/main/lib/ortho
- libavoid `connector.cpp`, `orthogonal.cpp`, LGPL-2.1 — ideas only.
  https://github.com/mjwybrow/adaptagrams
- MSAGL `Routing/Rectilinear/Nudging`, MIT. https://github.com/microsoft/automatic-graph-layout
- McMurchie, Ebeling. PathFinder. FPGA 1995 (bibliographic record only).
- Kakoulis, Tollis. Labeling Algorithms. Handbook of Graph Drawing and Visualization, ch. 15.
- Christensen, Marks, Shieber. An Empirical Study of Algorithms for Point-Feature Label Placement.
  ACM TOG 14(3), 1995.
- Kieffer, Dwyer, Marriott, Wybrow. HOLA: Human-like Orthogonal Network Layout. InfoVis 2015.
- ISO 5807:1985, §9.2.2.4 (preview fragment).
