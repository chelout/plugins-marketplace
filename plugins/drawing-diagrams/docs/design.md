# drawing-diagrams: design decisions

Agreed with the owner on 12.09.2026 after a full walk of the decision tree.
This file is the source of truth for scope and architecture; SKILL.md tells an
agent how to use what is built, the files under reference/ document the model.

## 1. Scope

One skill, six diagram kinds on one core: `schema` (database tables),
`flow` (algorithm with decisions), `swimlane` (steps by participant),
`state` (lifecycle with transitions), `timeline` (moments and entity states),
`blocks` (composition of parts). `kind` is a field of the model; one command,
`render.py model.json`. The skill replaces `drawing-db-schemas`.

## 2. Core

Nodes are HTML cards on an explicit grid; connectors are an SVG overlay
computed by JavaScript from the cards' real geometry, so text never shrinks
and the page grows instead. One token set for chat widgets and artifact pages:
white ground, white cards, system font stacks, dark theme via `data-mode`,
`data-theme` and `prefers-color-scheme`. Modes: widget 680 px, page 1100 px.

## 3. Layout

The author places nodes with a grid map: rows of tokens, a token is a node id,
a dot is an empty cell. The renderer routes connectors between any two cells
along the gutters, around occupied cells, spreading parallel lines 8 px apart.
No automatic layout. The old `cell: [row, col]` field is gone.

## 4. Node vocabulary

`step`, `decision`, `terminal`, `state`, `note`, `block`. Colour encodes the
owner or category (graph, resolver, adapter, vendor, user; kind of truth);
shape and chrome encode the node kind. No diamonds: a decision is a card with
a question marker in its header. An id ending in `?` is a decision.

## 5. Edges

Shorthand string `from -> to : label | modifiers`; an object form exists for
rare options. A label is at most three words (about 24 characters) and sits at
the exit of the line next to its node; anything longer becomes a numbered
footnote under the diagram with a marker on the line. Flow-like kinds use an
arrowhead at the target; `schema` keeps the dot and crow's foot.

## 6. Swimlane

Lanes are columns with a header and a tinted band; time runs down; rows are
numbered automatically. Up to 5 lanes in widget mode, 7 in page mode; beyond
that the check suggests merging minor participants into one lane.

## 7. Timeline and blocks

Timeline: a vertical rail of moments on the left, one card per moment on the
right, entity states as chips in a fixed order. Blocks: a grid of `block`
cards with a title and a list; edges allowed, not required.

## 8. Limits

Widget: up to 4 grid columns (node about 150 px), 16 nodes. Page: up to 6
columns (about 165 px), 30 nodes. A node holds a one-line title and up to two
lines of text; the check refuses a title that would wrap. Gutters: 28 px
between columns, 40 px between rows. A diagram over the limit is split into an
overview and detail diagrams; the check says so.

## 9. Interactivity

Hover highlights a node's connectors. Named routes (scenarios) in the model
become chips above the diagram; a chip highlights the route's nodes and
edges. Routes are validated against edges. No step player, no animation.

## 10. Checks

Errors stop the render: a node in the map but not described or described but
not placed, a node placed twice, a decision with fewer than two exits or an
unlabeled branch, a label over the limit without a footnote, a route through
a pair of nodes with no edge, a line that cannot avoid a node (the check names
the node to move), more nodes, lanes or columns than the mode allows, a title
that does not fit. Warnings continue: an unreachable node, a non-terminal
node with no exit, line crossings (counted; three or more suggest a
rearrangement), empty rows or columns, two nodes in one swimlane row.
`--check` prints the map with routed lines as ASCII. `--draft` downgrades
errors to warnings and stamps the output "черновик".

## 11. Outputs

HTML for chat widgets and artifact pages; `--format mermaid` exports the same
model as `flowchart TD` for markdown documents in a repository; ASCII for the
terminal.

## 12. Order of work

Step 1: core and `schema`; migrate the KYC model; rerun the card-check test
with a subagent; compare the section 7 preview; remove `drawing-db-schemas`.
Step 2: the router, `flow` and `swimlane`; test on the resolver rules with
branches 4a/4b and on the 11-step trace. Step 3: `state`, `timeline`,
`blocks`; test on the verdict row lifecycle, the Mark timeline and the four
blocks on a check. Each step follows writing-skills: an unprompted subagent
run on a real task, review of its workarounds and remarks, fixes, rerun.
Examples from each step become `examples/`.

Implementation details left to the renderer: a decision's exit side follows
the target's position; the colour group limit for a swimlane equals its lane
count, up to five.

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
- Outcome of the experiment (2026-09-17): neither skill-level effort nor delegation paid off at equal quality; the session's effort and model stay. Against the previous version the changes above cut output tokens by 26–42% and cache reads by 47–56% on four benchmark tasks. `effort: high` in the frontmatter cut output further but applied in only two of three runs and led the model to inline assets, tripling widget size; `effort: medium` dropped required states from a model twice; a delegated `sonnet` agent raised cache reads by 49% on the schema task.

## 14. Routing quality (amendment, 2026-09-19)

Spec: `docs/specs/2026-09-19-routing-quality-design.md`. Decided after measuring the renderer against
its own count: over 1 500 random grids the lines drawn once `router.assign_offsets` had spread them
crossed more often than `router.crossings` reported, in 0.9% of them.

- The invariant, stage A: for every set of paths the router can produce, with `offs =
  assign_offsets(paths, nodes=nodes)`, `drawn_crossings(paths, offs, nodes) == crossings(paths)` and
  `drawn_overlaps(paths, offs, nodes) == 0` (all four in `diagrams/router.py`). What the renderer
  reports is what the reader sees: `flow.plan` counts `drawn_crossings`, and the warning
  "пересечений линий: N" with it. A break of the invariant is a defect of the renderer, never a
  message to the author.
- The unit of a slot and of an order is the run — a maximal straight piece of one path on one
  lattice line (`router._runs`) — and not the path. So a path with two runs on one line is placed
  twice instead of overwriting its own slot, and a pair that shares two stretches on one line keeps
  the order of each. (Placed twice, and drawn twice: whether the two land in one slot or in two is
  the slot rule below, which asks only whether they lie beside each other.) A zero-length segment — two equal consecutive points, which `schema.plan`
  produces — stays a run of its own and does not break the straight piece it lies in, so no output
  of `schema.plan` moves: its `cross_count`, the `off` and `via` of its edges and its warnings are
  what they were. (That was true of stage A's change. Slot reuse, stage B below, moves the `off` of
  schema edges that never lie beside each other — 576 of 23 948 synthetic plans — and leaves every
  `cross_count` and warning where it was.) The signature of `assign_offsets` and the shape of its result do not change:
  one `(ox, oy)` per point, read from the runs through that point, and `schema.plan` reads them as
  before.
- Three strengths of order, weakest last: `firm`, from a stretch two runs share and enter and leave
  in one order; `loose`, from one they enter and leave in swapped order; and the end-to-end rule —
  two runs that meet at a gutter point with their arms there pointing opposite ways take the slots
  their arms point to. The weakest is recorded wherever two runs meet end to end: such a pair shares
  no piece of a stretch, so it has no firm or loose order. Through a third run it can still close a
  cycle with firm or loose orders; where it does, no run of that cycle is ever free under all three
  strengths, so once the runs of the cycle are what remains to place, the pick order falls to `firm`
  and `loose` and the end-to-end order is the one dropped; a run outside the cycle is placed before
  that with the end-to-end order honoured. So it never displaces a firm or a loose order, and that
  step of the pick order is what the guarantee rests on.
- `tests/test_drawn_property.py` is the guard of any later ordering algorithm, this one included:
  it routes 300 seeded instances of `tools/instances.py` as `flow.plan` routes a model and asserts
  the invariant on every one, knowing `route_all`, `assign_offsets`, `crossings` and the two
  counters and nothing about how the offsets are found. All 300 agree, and the 14 renders of the
  shipped examples are byte-identical to the ones before the stage.
- Fast `Traffic`, stage C1: `router.Traffic` keeps a reference count per thing a path occupies — the
  points strictly inside its horizontal and vertical segments, the unit edges it runs along, its
  corners, its exits and its entries per node side — moved by `add` and `remove`, and a count that
  reaches zero drops its key. `route` reads `crosses`, `shares` and corner membership as booleans,
  so two earlier lines on one step cost the one surcharge one of them costs, and reads exits and
  entries as counts, which multiply theirs. `route_all` keeps one `Traffic` for the whole run: a
  rip-up removes its own line, routes it against what is left and puts back the path it keeps,
  instead of building the traffic of all the other lines again. `shares` answers for one step of
  `route` — a lattice point and a neighbour — where the class it replaced answered for any interval
  inside a run; a longer stretch is asked of the unit-edge table `units`, edge by edge, which the
  full-gutter price of stage B and the objective of stage C read directly (tasks 9, 11 and 12
  of `docs/plans/2026-09-19-routing-quality.md`). No path moves: `reference_route_all` of
  `tests/reference.py` takes the traffic class as a parameter, and `RoutesIdentically` of
  `tests/test_traffic.py` runs that one loop twice — once with `OldTraffic`, the class as it was,
  once with `router.Traffic` — and holds the two answers equal over the 300 instances of the
  property test above. The
  dense scenario of `tools/bench_routing.py` fell from a median of 298 ms to 70 ms on the measuring
  machine, 4.3 times faster.
- Gutter capacity, stage B: a gutter and a margin hold a stated number of lines, and a diagram that
  wants more is refused. The unit is the **group** of `router.assign_offsets` — the runs on one
  lattice line that overlap or meet end to end in a gutter, formed once in `router._line_groups` —
  because a group is drawn in the same slots wherever it reaches, whatever its load at any one
  point; how many slots that is, and why it is not the number of its runs, is the bullet below.
  At pitch `s` a group `w` slots wide has its outermost line `(w − 1) · s / 2` from the lattice
  line, and it fits while that line keeps `flow.LINE_CLEAR` = 4 px from the nearest card edge and
  `flow.EDGE_CLEAR` = 1 px from whatever bounds it on the other side (`router.fits`).
  `router.PITCHES` is 8, 6, 5 px: with the room in hand `assign_offsets` gives a group the first
  pitch that fits and the smallest where none does, so a group too wide for 8 px closes up instead
  of reaching over a card edge, and `router.capacity(room)` is the width the smallest pitch allows.
  Without the room — `schema.plan` passes none — every group keeps 8 px.
- Slots are reused, and that is what the width of a group is (spec §4.1a, taken into the stage by
  the owner on 2026-09-20 after the first measurement showed the unit above to be wasteful rather
  than wrong). The order of a group is decided exactly as the three strengths above decide it;
  then each run, in that order, takes the lowest slot above every earlier run it **lies beside** —
  shares a stretch of the line with, or meets end to end at a point that is not a node
  (`router._beside`) — and two runs that never lie beside each other are drawn in one slot
  (`router._slots`). A run of no length, which only the pseudo paths of `schema.plan` carry, holds a
  point and no stretch, so it lies beside a run whose interval holds that point — strictly inside it
  always, at either of its ends under that same node exemption — and without that reading the two
  would share a slot and a crossing `schema.plan` reports would drop out of its count
  (`SchemaGutter` in `tests/test_crossings.py`). So the width is the slots taken and not the runs counted: the chain of four
  that hand over at three gutter points (`CHAIN` in `tests/test_capacity.py`) is drawn in three
  slots, because the end-to-end rule places the two middle runs first, and each outer run then lies
  beside one of those two only: the first shares a slot, the second has to take a third. A
  staircase, where every run lies beside the one placed before it, stays as wide as it is long.
  `router._spread` is the one place that decides order and slots, as
  `_line_groups` is the one place that decides groups, so what `assign_offsets` draws is what
  `overfull` prices. The invariant of stage A is untouched: only two runs that lie beside each other
  can cross or overlap, and every such pair keeps the relative order the placing gave it, so
  `tests/test_drawn_property.py` guards this ordering as it guards any other. Measured over the 500
  seeded grids of the stage's capacity experiment, the refusals fell from 99, 127, 231 and 111 —
  flow widget, flow page, swimlane widget, swimlane page — to 54, 86, 173 and 75, against 29, 56,
  130 and 47 for the bound by the busiest point of a group; the rest is held by the orders, and an
  order chosen for width is left to the objective of stage C. All 14 shipped renders stayed
  byte-identical.
- Where the room comes from, per lattice line, is `flow.Geometry.room`: `gap / 2` in a column
  gutter, `row_gap / 2` in a row gutter between two rows of cards (a gutter beside an empty row is
  the exception, in the last bullet of this section) and, in the side margins, `Geometry.margin`
  towards the cards and `pad − margin` towards the grid box, all of it from the mode tables
  `flow.MODES` and `common.BASE_MODES`. So a column gutter holds five lines at `gap` 28 or 32 and
  three at 18, such a row gutter seven at `row_gap` 40 and eight at 44, a side margin three in
  either mode. The two outer
  row margins follow from no table: `.dg-grid` pads 8 px vertically while `by()` of
  `template/js/flow.js` puts a margin line `margin` px outside the cards, so both fall outside the
  grid box, where what clips or covers a line is the section, the title above it or the content the
  section goes on with below. `flow.TOP_ROOM` and `flow.BOTTOM_ROOM` carry what the browser
  measured (case 14 of `tests/test_browser_lines.py`, which fails when a change of the CSS moves
  them); the bottom one is keyed by the footnotes as well, because a `.dg-foot` list is what bounds
  a line there when the model has one. A swimlane's top margin, a row gap under the lane headers,
  holds four lines in a widget and six on a page; the bottom margin holds three in a widget and one
  on a page, two and none under a footnote list.
- Two of the measured rooms hold **nothing at all**, and the renderer says so rather than drawing a line
  no reader will see: a flow's top margin, where a widget's section clips the line
  (`overflow-x:auto` makes `overflow-y` compute to `auto`) and a page's `h3` title lies over it, and
  a page's bottom margin under a footnote list, which starts above where the line would be drawn.
  Giving `.dg-grid` more vertical padding would buy that room back; it is a template change with a
  CDN release behind it, and it is left to the owner rather than taken here.
- The price, and what it does not promise: `router.Lattice(cols, rows, occupied, capacity=…)`
  resolves the capacity of every line once, W + H answers, and in `route` a step along a unit edge
  of an even line whose load in `Traffic.units` already equals that line's capacity costs +20 —
  more than a crossing, so a full gutter is left to the lines in it wherever anything cheaper
  exists. A line that holds none prices every step along it with or without traffic, which is why
  the router now leaves a flow's top margin alone. It is a heuristic of the proposer: the load of a
  unit edge is not the width of a group, so a chain of runs that only meet end to end loads nothing
  and is still drawn two slots wide or more.
- The guarantee is the check. With the offsets, and from the same `router.place` call as they come
  from (the bullet on placing, below), `router.overfull(paths, nodes, room)` names every
  group that does not fit at the smallest pitch — reading its groups, their order and their slots
  from `_spread` as `assign_offsets` does, so the width priced is the width drawn — and
  `flow.overfull_error` turns each into a layout error, which prints the map and which `--draft`
  downgrades: "между столбцами 0 и 1 линий 4, помещается 3:
  a -> b, …; освободите ячейку рядом или переставьте узлы", with "между рядами" for a row gutter
  and "по левому полю" and its three siblings for the margins, columns and rows counted from zero
  as every other message counts them. The count is the width of the group — the slots that have to
  fit — while the list names at most four edges once each and may be the longer of the two, since
  an edge with two runs there is one name and two runs sharing a slot are one line; where the line
  holds nothing the advice is to move the nodes instead, since no cell freed beside it would help.
- The lattice ends where the page's rows end. `tracks()` of `template/js/head.js` takes its row count
  from the cards and invents a track for an empty row above or between occupied ones, never for one
  after the last, so `flow.plan` builds the lattice, the `Geometry` and the row count of its
  capacity messages from the last occupied row (`drawn_rows`), and `layout["grid_rows"]` is that
  count too. A line under the last card row was a line the script had no y for: it aborted and drew
  no edge at all. The defect was latent before this stage — three parallel edges over a trailing
  empty row reached it — and the price on a flow's top margin made it frequent; the branch gate
  found it. `tests/test_trailing_rows.py` holds the property that matters: an empty row the browser
  never creates does not change the drawing. Columns need no such rule, `tracks()` fills every
  column up to `--dg-cols`.
- An empty row inside the drawn extent does get a track, and the band around it is not a row gap
  wide. `tracks()` of `template/js/head.js` invents one track per such row and fills them in
  ascending order, so each sees the ones already invented above it: the first row of the grid lands
  `flow.TRACK_LEAD` = 20 px over the first cards and every empty row after it halves what is left of
  the way down to the next row of cards. An empty implicit grid row is 0 px high and both of its row
  gaps stay, so the span a run of k empty rows halves between two rows of cards is (k + 1) row gaps.
  `by()` of `template/js/flow.js` then puts a row line on its own track, a gutter halfway between two
  tracks and the top margin `Geometry.margin` over the first. So a page flow with one leading empty
  row draws the gutter above its cards 10 px from them, not 22, and the four lines the stage had put
  there at the 8 px pitch reached 2 px inside a card with no capacity error — the branch gate found
  it. `flow.Geometry` now takes the empty rows of the drawn extent and `Geometry._band` answers from
  the measured rule: towards a card edge the distance to it less `LINE_CLEAR`, towards another lattice
  line `flow.shared_room` of the distance — the two groups share it, less one smallest pitch
  (`router.PITCHES[-1]` = 5 px) kept between them, so the outermost lines of two neighbouring groups
  stay as far apart as two lines of one group ever come. Sharing the whole distance instead let both
  groups reach the very same y, and no counter saw it: `router.drawn_overlaps` works in lattice
  coordinates, where the two lines lie on lines of their own. The gate found that too, on the same model
  with one line more: the third line ran along the empty row at the offset +5 and the fourth along the
  gutter under it at −5 — two lattice lines 10 px apart, so a reader saw one line 15 px over the cards
  where the lattice had two.
  The row line of a fully empty row states a room like a gutter, since nothing but `by()` places it,
  while a row of cards keeps stating none; `router.Lattice` therefore resolves the capacity of every
  line and not only the even ones, so the +20 prices a step along a full row of empty cells too, and
  `flow.line_name` names such a line "в пустом ряду N" with "уберите пустой ряд" for advice — beside
  an empty row the cells are free already and what leaves no room is the row. The halving and that
  clearance make the band tight fast: on a page an empty row between two rows of cards turns one gutter
  that held eight lines into three lines of four, a leading empty row leaves two lines on its own row
  line and two in the gutter under it, and under a run of three leading empty rows only its first row
  line and the gutter under it hold a line at all, one each: every line below them has a neighbour
  2.5 px away, less than the clearance two groups keep, and the last gutter is inside `LINE_CLEAR` of
  the cards as well. Case 17 of `tests/test_browser_lines.py` holds the rule against the page — a flow
  and a swimlane, both modes, a run of one empty row and a run of two, leading and interior — case 18
  draws a group at the capacity of every line of two such bands, and case 19 measures those groups
  against each other, which is what the shared distance left to chance.
  Above a leading empty row the top margin has more room than `flow.TOP_ROOM` states, because the
  grid box starts a row gap higher while the line itself sits only 20 px over that row's track: 14 px
  under the box's top edge in a page flow, where the constant says 10 px above it, and 50 px under the
  lane headers in a page swimlane, where it says 26. The constant is kept there as the conservative
  number rather than a second table measured; case 17 checks that it is the conservative one.
- The objective, stage C: a whole routing has a price, `router.phi(infos, nodes, room)` — the sum of
  three things. What every path costs alone is `own`, the cost `route` itself reports for it with no
  other line there, replayed step rule by step rule on the `Info` that `router.describe` builds.
  What every pair of them costs together is `router.pair`: ten per crossing — drawn, or a stretch
  the two enter and leave in swapped order, which `route` cannot see at all — one per unit step they
  share, three per point of one that is a corner of the other both ways round, and three for each
  node side they leave or enter together. And `router.FULL` = 20 per slot the groups take past what
  their lattice line holds (`router.overflow`, over the groups `overfull` names, so what is priced
  is the width the offsets draw). `route` stays the proposer and Phi is what decides: `route` prices
  one step and knows a gutter only by the load of a unit edge, while Phi prices the routing that
  came out of it. `router.delta(i, new, infos, nodes, room)` is what one rerouted edge changes it
  by, exactly — the own and pair terms are a difference of two sums (`_own_and_pairs`), and
  `overflow` is recomputed on the lattice lines the old and the new path lie on, which is where the
  groups can have moved and nowhere else.
- The orchestration is `router.route_all(lat, ends, labelled, room=None, budget=600, passes=8,
  trace=None)`. The edges go into a canonical order (`canonical_order`): Manhattan length first and
  the **long edges first**, then the two points, then the label, and the model index only between edges
  equal in all four — which are one routing problem asked twice. Spec §5.3 gave the key and not the
  direction; long-first is at or under the old loop's Phi on 93 of the 100 instances of criterion C3
  without a room and 97 with one, where short-first reaches 90 and 95, and the long edges are the
  ones with somewhere to go. Two starts are built from that order and both are always completed,
  because a routing is complete or it is not a routing: `_greedy`, every edge against the traffic of
  the ones before it, and `_alone`, every edge routed with no other line there. From each a descent
  (`_descend`) takes every edge in turn, routes it again against the rest and keeps the new path
  only where ΔΦ is **under zero**, so Phi falls strictly and the loop cannot cycle. The lower Phi
  wins; on a tie the fewer crossings, then the lower Σ `own` — the routing whose lines are each
  nearer their own best — and the first start only when all three tie (spec §5.3 item 4, amended
  twice on 2026-09-20). Phi prices a whole routing and knows nothing about labels until stage E, so
  where it cannot tell two routings apart the one to take is the one that keeps its lines out of
  gutters they have no business in. The crossings are asked before the sum because a tie of Phi can
  hide one: Phi charges `CROSSING` = 10 for a crossing, so a routing that crosses can be ten cheaper
  in `own` and cost the same, and a reader is served worse by a crossing than by lines that run a
  little further from their own best — a fixture of `tests/test_label_lines.py` is that shape
  exactly, two descents at Phi 82 where the one with Σ `own` 66 crosses once and the one with 72
  crosses nothing, and the bullet on the two keys below names it. Neither key costs the search
  anything it notices: `_descend` holds the `Info` of every standing path already and hands the sum
  back with the Phi it ends at, and `_crossings` is called only where the two Phi are equal. That
  restriction is the whole of it — one count over the 40 paths of a dense plan of
  `tools/bench_routing.py` takes 4.9 ms against the 1.5 ms a whole Phi of the same routing takes,
  and counting on every pick would pay that twice a plan; over the ten plans of that scenario the
  two descents never end at one Phi, so it is not called at all, and paired runs of the tree with
  the rule and without it differ by less than the spread the machine has between two runs of either.
  The measurement behind the
  first amendment, which §5.3 item 4 records: over 600 plans
  of 300 seeded labelled models the sum moves neither the label warnings, 1 148, nor the crossings,
  5 466. The two
  starts share `BUDGET` = 600 calls of `route`, half to the first and the rest to the second, and it
  never binds: over the instances of criterion C3 in all four configurations a descent spends at
  most 162 calls — 130 in the configuration production routes in — and about three passes of
  `PASSES` = 8. `trace`, when a caller passes a list, receives a `router.Change` per accepted
  reroute, which is what `PhiFallsAcrossTheTrace` of `tests/test_objective.py` reads.
- What the descent costs is four levers, and each of them is the difference between a search that
  runs and one that is too slow to ship. Measured on the dense scenario of `tools/bench_routing.py`,
  the median is 194.9 ms with all four and, with one switched off at a time: 223.0 ms without the
  skip of a proposal equal to the path it replaces (`new == cur[n]` in `_descend` — after the first
  pass most rerouting is exactly that, and nothing of Phi need be asked about it); 204.6 ms without
  the early exit of `_weigh` (where the own and pair terms are already no improvement and the lines
  the two paths lie on overflow nothing, no recomputation can turn the proposal into one); 213.1 ms
  without `router._Memo` (the runs of a standing path and the pair orders of two standing paths,
  kept between proposals instead of walked again, and dropped per position by `forget` when a
  proposal for it is weighed); and 371.5 ms without the restriction of the overflow to the lattice
  lines the two paths lie on, with the per-line map `_overflow_by_line` gives and `_descend`
  carries — by far the largest, and the one spec §5.2 names.
- What the routing promises and what it does not. Spec §5.4: no `random`, no clock, integer costs,
  and the canonical order, so two runs on one model give identical paths and the same model with
  its `edges` shuffled gives the same route for every (source, target, labelled) — `CanonicalOrder`
  and `TwoCallsAgree` of `tests/test_route_all.py`, five shuffles over seeded instances. It promises
  nothing beyond the routes and the offsets they are drawn at, which the bullet below added: which
  label of two crossing ones is the one warned about, and the id a section is written under, still
  follow the order the model lists its edges in. An edge with no route is `None` in its own place,
  takes no part in either start or either descent, and leaves the others where they would be without
  it (`Unroutable`, same file).
- Placed as priced — the branch gate found it. The width of a group depends on the order the paths
  are given in: the sorts of `router._line_groups` and `router._order` break their ties by the path's
  index, and two runs read the order of a stretch they share from the path that comes first.
  `route_all` priced the canonical order and `flow.plan` drew the model's, so a descent could accept
  a reroute whose ΔΦ was under zero as priced and over it as drawn, and a group could be drawn over
  the capacity of its line with no message to name it. On instance 202 of
  `instances.small(61279, 203)` planned as a flow widget, nine of its edges, the search ends at
  Phi 314 with every group inside its line; those same nine paths in the model's order cost 334 and
  put six lines in the gutter between the first two columns, where five fit.
  `router.place(ends, labelled, paths, nodes, room)` is now the one place a routing is drawn from:
  it puts the paths in `router.canonical_order` — public for that reason — asks `assign_offsets` and
  `overfull` in that order, and answers per model position, so the width drawn is the width priced
  and the capacity error still names the edges in the model's own order. It costs nothing in the
  shipped output: all 14 renders stay byte-identical, and the dense median of
  `tools/bench_routing.py`, which now times `place` and so the capacity check as well as the
  offsets, read 201.2 ms before the change and between 201 and 207 over five runs after it, against
  a budget of 300 — the check it now also times costs 0.6 ms of that median on its own, and five
  runs of one tree differ by more than the rest of it. What it buys is §5.4's promise carried past
  the routes: a model with its `edges` shuffled is drawn identically too, which
  `OffsetsFollowTheOrderTheSearchPricedIn` of `tests/test_route_all.py` holds through `flow.plan`
  over five shuffles of twelve seeded models — 15 of those 60 shuffles drew an offset elsewhere
  before this — while `PlacedAsPriced` of
  `tests/test_objective.py` holds the total the search ends at equal to a whole Phi of the placement
  over the hundred instances of criterion C3 and reads the gate's own instance as a named case. The
  order the model lists two edges in stops deciding which of them is drawn above, or on the side a
  label's text stands: that is now the order the search priced them in, the lower source point
  first, and the two fixtures of `tests/test_label_lines.py` that stood on the old reading are
  written from the new one — `SidewaysLabel.test_a_straight_line_back_above_the_labels_own_line_is_a_warning`
  takes both readings from the two mirrored grids and asserts that the list no longer decides, and
  `StraightExitLabel.test_a_line_through_the_gutter_past_the_label_is_a_warning` gets its passing
  line from further up the column, over a free cell, since of two lines between the same two cards
  the one drawn on the text's side is never the exit up whose label it is.
- `tests/reference.py` is the only home of the loop the renderer routed with before — one pass with
  accumulating traffic and two rip-up passes. `route_all` is no longer that loop, so the identity
  test that held them equal is gone; what replaced it is Phi against the loop on the hundred seeded
  instances (`TheSearchCostsNoMoreThanTheLoop` of `tests/test_objective.py`, criterion C3) and
  crossings against it on the shipped examples. The loop now takes the traffic class as a parameter,
  which is what criterion C1 is asserted with: the same loop run with `router.Traffic` and with
  `OldTraffic` gives the same paths (`RoutesIdentically` of `tests/test_traffic.py`).
- `tools/bench_routing.py` now plans its dense scenario the way `flow.plan` plans a page flow
  (`DENSE_CONFIG`, `planned`): the lattice states the capacity of every line and the routing and the
  offsets are given the room those capacities come from. Timed without them the run would leave out
  the one term of Phi that is not pairwise additive and report a budget nothing in production ever
  meets. The dense median went from 61.3 ms to 195.7 ms against the spec's budget of 300, and the
  shipped examples stay at a maximum of about 8 ms against their budget of 25.
- What the stage bought, measured over 500 seeded grids of other seeds than the tests', every third
  edge labelled, in the configuration production routes in: crossings down 11 to 13 % in total — up
  in about 18 % of the instances, down in about 57 % — overflow slots down 80 to 85 %, and Phi down
  9 %. Plans the capacity check refuses fell from 49 to 14 (flow widget), 68 to 16 (flow page), 162
  to 36 (swimlane widget) and 65 to 19 (swimlane page).
- What moved in the shipped output: 2 of the 14 renders, `four-blocks` in both modes, where the
  routing costs exactly what the loop's did — Phi 63, no crossings, Σ `own` 47 — and draws two of
  its lines, `resolver -> verdicts` and `resolver -> attempts`, with each other's shape; the tie
  there is with the routing before the stage and not between the two descents, which end at 65 and
  63. Every other render, `verdict-row-lifecycle` among them, is byte-identical to the one before
  the stage. That model is where the tie rule earns its keep: both descents end at Phi 60 and
  neither of them crosses anything, so the sum is what decides it. Σ `own` is 53 for the greedy one,
  which sends `none -> declined_retry` out through the bottom of its card and along the gutter under
  the label "вердикт" of `none -> approved`, against 52 for the one that leaves through the side of
  the card, which is also what the loop drew. So no warning of the shipped examples is new.
  `TheTieKeepsTheLabelOfTheShippedExample` of `tests/test_objective.py` holds that label clear of
  the other line in both modes and reads the tie from the trace, and the two `TieCase` classes of
  `tests/test_route_all.py` read each key both ways round on a hand-made pair of routings —
  `TheTieGoesToTheLowerSumOfOwn` where the crossings tie, `TheTieGoesToTheFewerCrossingsBeforeTheSumOfOwn`
  where the lower sum is the routing that crosses. Hand-made is what it takes to put the higher
  Σ `own` on the second start: `_alone` gives every line its own best, so the second start's sum is
  the lowest a routing of the model can have, and only a descent can raise it.
- What the order of the two keys settles, and what it costs. Σ `own` alone moved the second model of
  `StraightExitLabel.test_a_line_turning_in_the_gutter_from_the_far_side_is_no_warning` in
  `tests/test_label_lines.py`, hand-made so that `a? -> b` is cheapest straight up: its two descents
  tie at Phi 82 and the lower sum, 66 against 72, is the routing that sends that edge round the
  margin beside the card instead of straight up, 11 of `own` against 14, with `g -> a?` moving to
  the other margin along with it, 8 against 11 — `own` charges +8 for a first step through the top
  of a card. That routing crosses once where the other crosses nothing, so the crossings take the
  case back to the straight exit and it stands as it was written. The order costs one fixture
  instead: the fourth case of `test_a_line_along_the_gutter_counts_when_it_runs_on_the_card_side_of_the_text`,
  the exit up, whose two descents tie at Phi 78 with the crossing on the side of the lower sum, 60
  against 61 — a straight exit up crosses whatever runs along the gutter over it, which is the very
  line that case measures. Its model now carries a card in the cell beside `a?`, where a labelled
  line that leaves sideways pays the +8 of the occupied cell it heads towards: the way round costs
  16 of `own` against the 14 of the two steps up, both descents draw the exit straight, and
  `ExitLabelCase.straight_exit` asserts that premise under its own name rather than leaving it to
  the first assertion that trips over it.
- Rearrangement advice, stage D: where the renderer has already told the author something about the
  drawing, it also says what to do about it, and every word of that is measured. `render.main` asks
  `advice.search` once per model — after `produce`, or after the `ModelError` — and never anywhere
  else: not from `flow.plan`, and not from `render.failure_map`, which plans again for the map. The
  trigger is a group drawn past the capacity of its lattice line or the crossings the warning counts
  (`render.triggered`, `render.MANY_CROSSINGS` = 3, `layout["overflow"]` of a draft plan), and the
  score a grid is ranked by is the tuple (overflow, crossings, total length) compared
  lexicographically (`advice.evaluate`). Spec §6 wrote that tuple with `unroutable` first and it was
  dropped on 2026-09-20: a grid of cards cannot wall an edge in — cards sit on odd lattice points
  and the gutters between them are never blocked — so `route` always finds a way and the
  "нет маршрута" branch of `flow.plan` is a guard no model reaches.
- The gate is the trigger and not what the search finds. A model that crosses twice is offered a
  move and told nothing, one crossing under the count the warning is printed at
  (`test_a_model_one_crossing_under_the_threshold_is_not_advised` of `tests/test_render_cli.py`,
  which holds the search's own answer as its premise rather than an absence). Both halves of the
  trigger are read, and the capacity half alone is held on a model with a group over its line and
  the crossings under the threshold
  (`test_a_group_over_its_capacity_is_advised_with_the_crossings_under_the_threshold`); the model
  is `tests/models/overfull-gutter.json` without the two edges that make it cross three times, so
  a trigger that had quietly become "count the crossings" would say nothing about it. The kinds
  `flow.py` plans are the only ones searched — a schema and a timeline have no advice — and a model
  refused for the length of a text alone gets none either: it has no layout to read a trigger off,
  it gets no map for the same reason, and what it needs is a shorter text and not a rearrangement.
- The moves, and the rules that keep the author's reading. `advice.moves(original, current,
  mode_name)` offers three kinds (`advice.Swap`, `advice.Shift`, `advice.Lanes`) in the order of how
  little they disturb the reading — inside one row, then to the row beside it, then the rest
  (`advice._reach`) — with ties to the earlier node in the model, so two calls give one answer. A
  swimlane moves no card of its own, since a column is a lane and a row is a moment: its only move
  is a lane order that takes the grid columns with it. Every move produces a deep copy with a new
  `grid` and nothing else touched, because `flow.plan` writes `_note` and `_text` into the nodes it
  plans, and `advice.write_grid` writes the map back at the author's own column offsets, keeping a
  row nothing moved in byte for byte, once at the end of the sequence and never per move — written
  per move, a card carried into a column too narrow for it would push the rows a later move
  rewrites out of the author's own alignment
  (`test_the_advised_grid_after_several_moves_keeps_the_authors_offsets` of
  `tests/test_render_cli.py`). `advice._Rules` judges the grid a move **produces** against the grid
  the author **wrote**, which is what closes the rules over a whole sequence instead of one step at
  a time: an edge that runs downward in the author's grid never has its target above its source,
  and a node the author gave no incoming edge stays in the first row if that is where it stood.
  Level is allowed, which is spec §6's own reading and not a stricter one: the two cards of a
  downward edge may come to stand in one row, and it is the original grid — not the grid in hand,
  which by then has nothing to say — that refuses the later move reversing them
  (`TheOriginalGrid` of `tests/test_advice.py`). Task 14 first read it strictly, target below
  source, and the branch gate measured what that costs: on the first seeded model the search
  stopped at (0, 1, 102) where the spec's rule reaches (0, 0, 102) in three moves instead of four,
  and on `CROSSED` of `tests/test_render_cli.py` one swap now clears all three crossings where two
  were needed. A lane order is a permutation, so a model of twelve lanes has 479 001 600
  of them: `advice.MAX_LANES` = 7, the widest `max_lanes` any mode declares
  (`flow.MODES["swimlane"]["page"]`), is the cap, and a model over a limit of its mode is advised
  nothing and plans nothing at all (the plan gate's finding G3, `LaneOrders` and `NothingToAdvise`
  of the same file). The cap is held under `lane_orders()`, a `permutations` that refuses to build
  the orders of more lanes than the cap allows, so a cap that stopped holding is a failed assertion
  and not a suite that never finishes.
- What ranks a move before anything is routed is `advice.proxy`: ten per crossing of the straight
  lines between the cell centres of two edges, six per card standing on such a line where it runs
  along one row or one column, three per edge that goes up, plus the Manhattan length of every edge.
  It counts the lines an author would draw with a ruler where the router draws around the cards and
  through the gutters, so it is a ranking and never a prediction — which is the whole of its job:
  `advice.search` prices every move of the grid in hand with it and pays a routing only for the few
  it then verifies (`TheProxy` of `tests/test_advice.py`).
- The search is hill climbing with a verified step. One step: rank the moves by the proxy, plan the
  best `advice.TOP` = 8 of them with `advice.evaluate` — a draft plan of a deep copy, at the
  overrides `render.main` forwards, so a move is never verified against a geometry the render will
  not use (the plan gate's finding G2, `TheRendersOwnWidth`) — and take the best whose score is
  strictly lower than the grid's own, whose plan carries no message the author's grid did not
  already have, and which brings no more warnings than that grid did. Then step again from the grid
  that move produced. It stops when nothing improves, after `advice.MAX_MOVES` = 8 moves, or when
  `advice.MAX_PLANS` = 40 plans are spent, the one that prices the author's own grid included
  (`HillClimbing` and `ThePlanAllowance`). Two of the three numbers are spec §6's and are pinned as
  such; `MAX_PLANS` is the owner's, measured and ruled on, so only its mechanism is held
  (`TheNumbersOfTheSpec`).
- A warning counts as a problem, since `SKILL.md` tells the author to treat one as an error. The
  third value of `advice.evaluate` is how many warnings the draft plan carried, the crossings
  warning left out (`flow.CROSSINGS`) because lowering that count is what the moves are for, and a
  candidate carrying more of them than the start is dropped however well it scores. It bites: on
  seeded #15 the best move by score at the very first step opens an empty row and the search takes
  a worse-scoring one instead, and on #6 the same happens three steps in
  (`NoNewWarning` of `tests/test_advice.py`, and the population assertion of `HillClimbing`). Both
  models were handing the author a grid with an empty-row warning their own grid did not have.
- The author is not asked for the cosmetic moves. The climb reads the whole score, the length of
  the lines included, because a move that only shortens them can open the way to one that removes a
  crossing; the sequence `advice.search` hands back ends with the last move that lowered overflow
  or crossings, and the moves after it are dropped inside `search`, so every caller gets the same
  trimmed sequence and the same claim. Over the twelve seeded models that is 41 moves asked for
  where the untrimmed climb made 55, and on the shipped examples it is the difference between an
  advice and none: every one of the eight example-and-mode pairs the benchmark runs is now offered
  nothing, because a shorter routing was all any of them had.
- Every verifying plan routes in full, and the lever spec §6 held in reserve was measured and
  refused. `tools/bench_routing.py --advice` runs both readings over three populations: the shipped
  examples in both modes; the twelve seeded models `bench_routing.seeded_models` builds for the
  tests, each an instance of `tools/instances.py` on the naive reading-order grid an author writes
  before thinking about the lines, kept when its plan crosses three times or more — seven to sixteen
  cards, which is the size of a model somebody writes by hand; and the dense scenario, a page of 30
  cards and 40 edges. Full verification is 44.2 ms median on the examples (max 138.5), 587.0 ms on
  the seeded models (max 1 995.4) and 6 380.9 ms on the dense scenario (max 7 686.0), against the
  3 s spec §6 asked to be reported against — one run's numbers, which drift a percent or two
  between runs on one machine. The lever — verifying plans that stop at the better of
  the two starts, which `bench_routing._route_budget` prices by setting `flow._ROUTE_BUDGET` to
  zero, with the advised grid planned in full once at the end — is three times faster and advises a
  different grid on every model of the two populations where that matters (the same moves 0 of 5
  and 0 of 12; 8 of 8 on the examples, where there is nothing to advise either way): on seeds 2, 4
  and 5 of the dense scenario it finds no move at all, and on seed 2 that leaves the author's own
  (2, 102, 392) where the full search reaches (0, 33, 270) — two slots over capacity left standing,
  and overflow is the first term of the score. So there is no fast mode: what bounds the cost is
  the trigger and the 40 plans. `flow._ROUTE_BUDGET` stays as the measurement switch it is: the
  tool moves it for the length of its own run and puts it back, and no renderer path sets it.
- The output is stderr and nothing else, printed after the warning or the error it answers
  (`render.advice_block`): a headline, the moves numbered from one with what each buys, the advised
  grid under `grid:` with each row quoted as the author would paste it back into the model, and —
  where a move changed it — the lane order under `lanes:`. A `lanes` move changes `lanes` and `grid`
  together, because the columns travel with the lanes; the grid pasted on its own would hand the
  cards of one lane to the lane beside it, and on `overfull-gutter.json` it does so silently, since
  there a lane is what colours a card and no node names a group of its own
  (`test_a_lane_order_is_printed_with_its_lanes`).
  The headline counts the term of the score the whole sequence moved — the first of the three whose
  two ends differ, which is the one that made the sequence an improvement, since the three are
  compared in that order — and `render.SCORE_TERMS` names it to the author: "лишних линий" for a
  slot over capacity, in the word the capacity error itself uses for a line that does not fit,
  "пересечений" for a crossing, "длина линий" for the length. So a trigger answered is a trigger
  counted: a group over its capacity gets a headline that speaks of it. Every step names the term
  it moved itself (`render.moved_term`): the climb reads the whole score, so a move inside the
  sequence may have bought nothing but a shorter line, and a step naming the headline's term would
  then print a count standing still. No step of any block over the seeded population does
  (`test_no_step_of_the_seeded_populations_blocks_stands_still`). "за N ходов" declines through
  `common.plural`, which is what lets the count stand where spec §6 wrote it instead of moving the
  noun in front of it as the other messages do. With several models the headline carries the path
  of its own model and not of the first of the batch, exactly as the summary lines do. Nothing is
  printed when no move improves the score, and `--no-advice` suppresses the search itself, in a
  batch as much as in a single render.
- What the advice does not touch: stdout, the exit codes, `--check`, `--format mermaid|ascii` and
  the all-or-nothing of `--out-dir` are what they were, and an error run prints the advice once,
  after the errors and the map, and still exits 1 (`tests/test_render_cli.py`, criterion D3). All 14
  shipped renders stay byte-identical, on stdout and on stderr alike: not one of them has a trigger,
  so not one of them gains a block.
- Measured before it is kept (spec §6, criterion D4 as amended), 2026-09-21: sixteen headless
  sessions of `claude-opus-5` at effort `xhigh` by the method of the token cost experiment, over two
  plugins that draw alike — this branch, and `main` at `1fcb07e`, which has neither the block nor
  the passage about it. Where a block was printed the author applied it whole, rendered once more
  and stopped. T7, a constructed task (two trivial edits of a model that crosses 15 times as given),
  three runs of three: 2 renderer calls, 4.2K output tokens, 0.87 USD and 56 s a run, against 5.3
  calls, 22.7K tokens, 1.73 USD and 514 s without the block, where the author writes a grid search
  of its own over `render.py --check`. T6, a new swimlane of four lanes that reached the trigger by
  itself in all six of its sessions (3 to 5 crossings on the author's first grid), the one run of
  three that was offered a block: 75 s and 0.94 USD, where the three runs without advice averaged
  253 s and 1.61 USD.
  What the block costs is the last crossing. On T7 it ends at 1 and the author stops there, the
  warning being gone; the authors without it, free to relay the whole grid, ended at 0, 1 and 0, at
  ten times the wall time. On T6 every run of both variants ends at 2.
  Two of T6's three runs with advice were offered nothing at 3 crossings. With one card a row the
  only moves are the 23 other lane orders; the two that reach 2 crossings bring a label warning, and
  a move that leaves the author with more warnings is dropped. Those authors reached 2 by giving a
  card to another lane, which no move may do. A trigger without a block costs what no advice costs.
  The trigger is rarer than the tasks were written for: on T4, the edit task of the token cost
  experiment, and on T5, a new flow of 9 nodes and 16 edges whose reading-order grid crosses six
  times, the author's first grid crosses 0 and 1 times, no block is ever printed and the variants
  differ in nothing, so each ran one pair. T5's two sessions are the dearest of the sixteen, 3.78
  and 6.50 USD and 13 and 35 minutes, and spend all of it on label warnings — stage E's subject.
  28.33 USD in all. Three runs a cell make the means an indication; the finding is the pattern.
  The harness and its rows stay outside the repository (`.experiments/d4`).
- The owner's decision on that report, 2026-09-21 (task 17, spec §12 Q2): the advice stays on
  whenever it is triggered, with `--no-advice` to switch the search off; it is neither made opt-in
  nor removed. The rule that drops a move which leaves the author with more warnings stays as built:
  the two runs it left without a block are its known price, and what would lower that price is fewer
  label warnings, which is stage E's work, not a block that trades one warning for another.
- Stage E, labels (spec §7, tasks 18–22). One model of what is drawn, `diagrams/labels.py`: every
  card, run and bound is a rectangle `(Y, y0, y1, x0, x1, kind, owner)` of one lattice row, `y` from
  the row's `base()` as the script computes it, `x` from `Geometry`. Card heights are unknown in
  Python and the model keeps that instead of guessing: a card is the whole of its row, a vertical
  run the whole of every row it passes and, in a row it ends in, as far as the bend drawn there —
  half the row where the row is banded or the run ends on a card — and a text whose place depends
  on a height covers every row it can fall in. The first model cut every such run at the base of
  the row; the second round of the branch gate found what that costs (634 of the 1 168 such ends
  of the seeded corpus are drawn off the base). `room` measures a text from its near edge outwards,
  `hits` names the owners it lies on, `meet` tests two texts. What `room_beside`, `band_obstacles`,
  `under_card`, `label_spots` and the pass after the label loop did with `half`, `reach`,
  `horizontal` and a second pass are values of `y0`, `y1`; all five are gone from `flow.py`. A
  place that hangs from its own source card is exempt from that card and from the lines drawn
  within its height, by (row, owner) — plan gate finding G4. The clamp of a banded row sits on the
  text, not on the line: the script clamps the lines of such a row and a text drawn from a point of
  it together, so only their order survives.
- Two readings changed when `flow.plan` moved onto the model, and the browser is why. The model
  stood beside the old code first, held to its verdicts on the 8 example plans, the 66 plans of the
  label cases and 100 seeded labelled instances; it differed in one class, a row a vertical second
  segment ends in, which it reads past the bend drawn there (5 of the 100 move a label, the
  examples and the label cases none). And it checks a label over a horizontal second segment by
  the text's own rectangle where the old pass tested the whole segment. Read against the page —
  the hundred drawn as drafts, the label boxes of the probe against the drawn runs of every other
  edge — the old pass warned of 133 lines of which 7 ran through the drawn text and missed 35 of
  the 42 that did; after the switch every one of the 32 warnings is a line through the text.
- The places, spec §7.2: a straight exit down or up right of its line, then left of it; a sideways
  exit above its line, then below; a horizontal second segment over it just after the bend (the
  owner's Q4), under it after the bend, then over its far end; a vertical second segment beside its
  middle or pinned to a row, as before. Every place on a horizontal second segment is anchored to
  the segment as drawn. The old script hung such a label 9 px over `base(Y)` whatever the segment's
  own offset, so a segment drawn 9 px or more above the base ran through its own label: 34 labels
  of the corpus, 8 of the 171 such labels of the hundred struck in the browser and 15 more with the
  line on their baseline; none now. A label that fits nowhere names what is in its way: ", мешает
  карточка X", "линия a -> b", "подпись связи a -> b", "край диаграммы". The one new wording is
  "под вторым отрезком". Every `LABEL_*` number lives in `labels.py`, in one copy.
- The choice, spec §7.3: `labels.cost` is (pairs of chosen labels that overlap, line owners the
  texts lie on, sum of preference ranks), compared in that order, a line counted once per place
  however many rows or runs of it are met. Labels whose places can meet form components; each is solved by
  branch and bound, most constrained first, from the greedy choice over the same places, within
  20 000 nodes a plan spent in the model's order. Never worse than greedy, the same input the same
  choice, `nodes=1` greedy: the components small enough to walk whole equal the exhaustive walk,
  and over 420 plans — the hundred and two other seeds with every second edge labelled — priced by
  a probe that computes the cost of the spec for itself, the search is better on 149, equal on 271
  and worse on none. The first search priced a line by its
  runs, and under the spec's cost three of the hundred came out dearer than greedy; the branch gate
  found it, and `labels.terms` is now the one place a place is priced, a line by its edge. A plan
  spends 122 nodes median and 601 at most on the dense instances, 138 at most on the hundred;
  `labels.place` costs 3.65 ms a plan there against a `flow.plan` of about 200 ms. The dense
  scenario of `tools/bench_routing.py` routes unlabelled edges and never called `flow.plan`, so its
  300 ms never priced a label and does not now (204.25 ms at the end of the stage, 201.01 at its
  base); `--advice` is within the noise of the stage's base on all three populations.
- What a label says, and how often, is a contract, because `advice.evaluate` counts it: one "ляжет"
  where the text lies on a line or on a label, one "пересечёт" per line crossing a text on a
  horizontal second segment, a pair of overlapping labels told once, on the later of the two, as
  one place when it is one place; a label that fits nowhere raises its error and no warning beside
  it. The cost and the verdicts read every place against every rectangle of its rows. The old
  families looked away — a label on a horizontal second segment was measured against no line along
  its row and no label — and 8 of the 9 labels of the hundred that a line or a label ran through
  while the plan said nothing were of that family.
- Criterion E6, the seeded hundred, 442 labels, `main` at `c2b3f36` against the stage: "пересечёт"
  133 → 24, "ляжет" 49 → 89, one place 0 → 0, labels that do not fit 24 → 24. "Ляжет" grows, and
  every rise is a check `main` does not make, in three classes: a line along the row of a label on
  a horizontal second segment, which `main` never read (#14, #16, #48, #52, #75, #77, #80, #87,
  #90 when the search landed); the end-row reading (#57); and — the large one, 22 instances when
  the third fix pass landed (#15, #16, #19, #22, #28, #34, #35, #42, #46, #64, #65, #66, #67, #72,
  #74, #75, #77, #80, #85, #87, #92, #96) — a label that cannot stand over or under its segment
  without reaching a card and so stands on the other side, where the next line of the gutter runs.
  `main` hung such a label over the base of the row, where its own line ran through it, and said
  nothing. The class-wide fix of the frame (below) adds one of each, on seeded #11, where a text
  over a segment along a banded row is now read as far into the gutter above as the clamp can put
  it. What the numbers are worth is read off the browser, a text taken as struck when a line,
  another label or a card shares px with its ink: 99 labels struck on `main`, 20 of them with
  nothing said and 58 warned of with nothing through them; 87 at the end of the stage, 1 with
  nothing said, 28 false alarms. Of the 89 "ляжет" 63 are texts the page does draw something
  through. Over the 174 plans of the corpus the places moved 242 of 646 labels before the search.
  In the shipped examples three labels moved to just after their bend in both modes
  (`four-blocks` "1 читает approved", `kyc-trace` "ссылка", `resolver-rules` "нет") and the search
  moved two more of `four-blocks` as a widget; no example gained a warning.
- A text stands in every row it reaches (the third round of the branch gate). A label is 13 px
  high and hangs 9 px off its line: 19.5 px of the 20 px half gutter of a widget, 22 on a page. A
  segment drawn off the middle of its gutter therefore takes one of its two places out of the
  gutter — onto the card under it, since cards align to the top of their row, or into the row over
  it, which ends with a card of unknown height and is read the same way. The places of spec §7.2
  anchored to their own segment brought that reach with them and the model looked only at the row
  of the segment: between the places landing and this fix 32 of the 442 labels of the hundred were
  drawn on a card with nothing said, where `main` had none. `labels.reached` names the card rows a
  text reaches and the place gets a rectangle in each, so `fits` drops it; the browser holds every
  label's ink off every card over the 36 pages that carry a label. Reading the reach by the ink of
  the text instead of its em box was measured and refused: over the hundred it is better on every
  count ("ляжет" 72, 82 struck, none on a card), but the margin it needs — 3 px above, 2 below —
  is the ink of a lowercase word without й, ё or a descender, and Python knows the width of a
  string, not its height. With a place on a card dropped before the search starts, greedy's own
  choice is the cheaper one more often: 15 of the hundred are strictly cheaper than greedy, none
  dearer.
- A label is read in the frame the page draws it in (spec §7.1 as amended a fourth time). The
  third and fourth rounds of the branch gate each found one more place the model tested in a row
  other than the one the page drew it in; put to the gate as a question, the class had eight
  members — the places on a segment on every line of an empty-row band, comparisons across nearby
  lines of one band, a straight exit across a band of two or three rows, a pinned place on a band
  line 2.5 px from a card, the drawn middle of a vertical segment, a sideways text clamped out of
  its row, a text over a segment along a banded row, and one carried out of a row of cards by its
  offset — and the fix found a ninth, a vertical run ending at a bend a clamp moves. One mechanism
  closes them: `Geometry.frame` states where every row line Python knows the px of — a gutter, an
  outer margin, every line of a band — stands against the cards around it, built from `_tracks`,
  the construction `_band` prices stage B's room from (room answers as before, held by a test);
  `labels.py` writes every rectangle of a frame in the px of its lowest line, so what stands on one
  line meets what stands on the others and a card row a text reaches drops the place. Where the y
  depends on a card height the rectangle holds every y the page can draw, bounded by `CARD_LEAST`
  (28 px, the least card the browser draws, held by a browser test over every drawn card) and
  `CLAMP` (the 10 px `clampY` keeps a line inside its card). Each member has a test that fails when
  its part of the mechanism is undone. Over the corpus it moved three labels, one each by the
  middle, the sideways text and the banded segment; the band models of one to three empty rows,
  leading and interior, in both modes, join the pages the ink-off-every-card case reads (147 inks
  over 46 pages, none on a card). One of them, a leading band of two in a widget, is now refused
  with a fit error where it drew its label on a card: every place of that label lies on one.
- The anchor, spec §7.4: a labelled edge carries `la: [pt, ref, Y, dx, dy, anchor]` — a point of
  the drawn path, a reference down the page ("p" that point, "m" the middle of the second segment,
  "r" `base(Y)`), two offsets and the text anchor — and no edge carries `ls` or `ly`. The label
  block of `flow.js` is three lines that apply it, with no rule, no number and no comment; a fresh
  `dg.js` is 9 973 bytes (10 411 before, budget 10 811) and the median cdn fragment 5 557.5
  characters (budget 5 691). The browser holds it: the probe records `getBBox()` of every label
  text in the svg's own frame (a box is 13 px high, the em box of the 11 px text, the baseline
  about 2 px above its bottom; widths within 2.3 % of `common.label_width` on the one example
  measured, Cyrillic only), and case 21 holds every box inside the rectangle Python chose and
  recomputes each anchor from the drawn line, for all the anchor forms the table has; the place under a
  segment fails it when its offset is the over-offset. Inside is both ways (criterion E5 as
  amended): across for all 110 places, with 5 % of the width allowed at the far edge for what the
  glyph table is known to within, and down the page for the 70 whose rows the page lets it read —
  a rectangle moved 8 px without its anchor fails it. When the anchor replaced `ls` and `ly` no
  label moved: the fragments were equal once the three fields were dropped, and the browser drew
  the 442 labels of the hundred at the x and y it had drawn them at. A fragment with `la` needs
  the script built with it: `template/dist` was rebuilt at `a9d40da` and `REF` names it.
- Found on the way and left alone: a grid column that holds no card is placed by `Geometry` and by
  `tracks()` differently, about 217 px apart on a two-column grid; the renderer warns about such a
  grid today and nothing more.
