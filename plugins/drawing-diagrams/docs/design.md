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
  what they were. The signature of `assign_offsets` and the shape of its result do not change:
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
  full-gutter price of stage B and the objective of stage C will read directly (tasks 9, 11 and 12
  of `docs/plans/2026-09-19-routing-quality.md`). No path moves: `reference_route_all` of
  `tests/reference.py` routes with `OldTraffic`, the class as it was, and `RoutesIdentically` of
  `tests/test_traffic.py` holds the two equal over the 300 instances of the property test above. The
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
  Without the room — `schema.plan` passes none — every group keeps 8 px and no output moves.
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
- The guarantee is the check. After the offsets, `router.overfull(paths, nodes, room)` names every
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
