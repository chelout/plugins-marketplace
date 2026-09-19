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
  lattice line (`router._runs`) — and not the path. So a path with two runs on one line gets a slot
  for each instead of overwriting its own, and a pair that shares two stretches on one line keeps
  the order of each. A zero-length segment — two equal consecutive points, which `schema.plan`
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
