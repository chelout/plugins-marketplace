# drawing-diagrams: design decisions

Agreed with the owner on 12.09.2026 after a full walk of the decision tree.
This file is the source of truth for scope and architecture; SKILL.md tells an
agent how to use what is built, reference/model.md documents the model.

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
