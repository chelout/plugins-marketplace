---
name: drawing-diagrams
description: Use when asked to draw, show, or review a database schema or ERD, a flowchart or algorithm with decisions, a swimlane of steps by participant, a lifecycle or state machine, a timeline of moments, a composition of blocks, or "what is stored where", for a design doc, chat widget, or HTML artifact; and when an existing diagram (mermaid, any auto-layout ERD or flowchart) came out too small, cramped, or with lines through boxes.
---

# Drawing diagrams

## Overview

A diagram stops being readable the moment an auto-layout engine picks the font size to fit the graph into the container. This skill fixes the font and lets the page grow: nodes are HTML cards on an explicit grid, connectors are an SVG overlay computed from the cards' real geometry, and `render.py` routes lines through the gutters and refuses layouts that would cross a node or truncate text. One core, six kinds: `schema`, `flow`, `swimlane`, `state`, `blocks`, `timeline` (design.md).

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

1. Collect the content. Schema: tables from migrations or the design, per column name, type, PK/FK/U/N. Flow: steps, decisions with their branches, outcomes. Swimlane: steps in time order with the participant of each. State: states and transitions with their reasons. Timeline: moments with what happened and the state of each entity. Blocks: parts with their short facts and the numbered path through them.
2. Pick the kind and the grouping that colours cards: owner, kind of truth, subsystem, participant. At most four groups (five lanes for a swimlane). Colour encodes the category; shape and chrome encode the node kind.
3. Write the model (format: reference/model.md; examples in examples/: kyc-module (schema), resolver-rules (flow), kyc-trace (swimlane), verdict-row-lifecycle (state), mark-timeline (timeline), four-blocks (blocks)). Place nodes with the grid map; put nodes that connect next to each other, the main path down the first column, branches to the right.
4. Render:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/render.py model.json --check
   python3 ${CLAUDE_SKILL_DIR}/render.py model.json --mode widget --out out.html
   ```

   `--check` prints the map with routed lines as text and the crossing count. Fix every error; treat warnings as errors unless the user accepts the trade-off. `--format mermaid` exports for a markdown document; `--draft` renders a flow with layout errors as a stamped draft.
5. Embed. Widget mode: the file contents go to `show_widget` as HTML. Page mode: paste the section into the page; `--no-assets` for the second diagram on the same page.
6. Look at the result (`--harness` wraps a widget fragment into a standalone page). Check: no line through a card, every arrow lands on its target, no title wraps, the legend lists exactly the groups used; click a route chip and a toggle.

## Rules the renderer enforces

- Schema lines always attach to key rows, field to field: horizontal neighbours across the gutter, stacked neighbours around the gutter beside the column; anything else needs `right` or `left` along the margin.
- Flow, swimlane, state and blocks lines are routed by the renderer between any two cells through the gutters, never through a node; routes are chosen together so exits spread over a node's sides and arrows do not pile into one entry; parallel lines are spread 8 px apart; the check counts crossings.
- A branch label is at most three words, at the exit of the line; anything longer is a numbered footnote referenced as `[n]`. A decision has at least two labelled exits.
- Widget: 680 px, up to 3 columns for a schema, 4 for a flow, 5 lanes; 16 nodes. Page: 1100 px, 4 / 6 / 7; 30 nodes. A title must fit one line, text two lines.
- Swimlane: lanes are columns, time runs down, rows are numbered automatically. State: cards with a colour stripe, transitions labelled at the exit. Blocks: cards with up to five short items. Timeline: no lines; a rail of moments, entity chips in a fixed order, a changed chip highlighted.

## Common mistakes

| Mistake | What happened without the skill | Do instead |
|---|---|---|
| Mermaid because it is quick | Graph scaled to fit 680 px: 6–8 px fonts, edges through boxes; the owner rejected it | Model + `render.py`; mermaid only as `--format mermaid` for markdown |
| New hand-written cards and SVG for each diagram | 30 KB of fresh CSS/JS every time, a different look every time, text down to 9 px, nothing validated | Model + `render.py`; change the look in `template/` once |
| A line to every table with `connection_id` or `tenant_id` | Three parallel dashed lines merge into one bundle | Grey hub, `outside: true`, a note in the card |
| Different colour per node | Colour must encode a category | Group by owner, kind of truth, participant |
| Long labels on lines | They collide with other lines and nodes | Short label at the exit, the rest in `footnotes` |
| A node far from what it connects to | Long routes, crossings, a line that cannot avoid a node | Move the node; `--check` shows the map |
| Patching renderer internals from a wrapper | The next diagram will not have it | CLI flags, or change the skill |
| Skipping `--check` | Crossing or truncated output ships | Run it; fix errors and warnings |

## Files

- `render.py` — CLI: `--check`, `--mode widget|page`, `--format html|mermaid|ascii`, `--out`, `--no-assets`, `--open`, `--types`, `--width`, `--harness`, `--draft`
- `diagrams/` — core (`common`, `grid`, `router`, `assets`); `schema`; `flow` for flow, swimlane, state and blocks; `timeline`
- `template/` — tokens, core CSS, JS overlay, harness page
- `reference/model.md` — model format, geometry rules, checks, embedding notes
- `examples/` — one model per kind, all from the KYC design
- `design.md` — agreed scope and architecture for all kinds
