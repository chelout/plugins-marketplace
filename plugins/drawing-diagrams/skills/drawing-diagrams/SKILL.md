---
name: drawing-diagrams
description: Use when asked to draw, show, or review a database schema or ERD, a flowchart or algorithm with decisions, a swimlane of steps by participant, a lifecycle or state machine, a timeline of moments, a composition of blocks, or "what is stored where", for a design doc, chat widget, or HTML artifact; and when an existing diagram (mermaid, any auto-layout ERD or flowchart) came out too small, cramped, or with lines through boxes.
---

# Drawing diagrams

## Overview

A diagram stops being readable the moment an auto-layout engine picks the font size to fit the graph into the container. This skill fixes the font and lets the page grow: nodes are HTML cards on an explicit grid, connectors are an SVG overlay computed from the cards' real geometry, and `render.py` routes lines through the gutters and refuses layouts that would cross a node or truncate text. One core, six kinds: `schema`, `flow`, `swimlane`, `state`, `blocks`, `timeline`.

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

1. Collect the content. Schema: tables with, per column, name, type, PK/FK/U/N. Flow: steps, decisions with their branches, outcomes. Swimlane: steps in time order with the participant of each. State: states and transitions with their reasons. Timeline: moments, what happened, the state of each entity. Blocks: parts with short facts and the numbered path through them.
2. Pick the kind and the grouping that colours cards: owner, kind of truth, subsystem, participant. At most four groups (five lanes for a swimlane).
3. Read `reference/common.md` and the file of the kind: `reference/schema.md`, `reference/flow.md` (flow, swimlane, state, blocks) or `reference/timeline.md`. A small model per kind is in `examples/`: `schema-small`, `resolver-rules`, `kyc-trace`, `verdict-row-lifecycle`, `four-blocks`, `mark-timeline`. Write the model next to the document it serves. Put nodes that connect next to each other, the main path down the first column, branches to the right.
4. Render with one command; it checks the model first:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/render.py model.json --mode widget
   ```

   On errors stdout is empty and stderr lists every problem: a text that does not fit names its length and how many characters fit; a line or grid problem also prints the map. Fix all of them in one edit and render again. Treat warnings as errors unless the user accepts the trade-off. Where lines cross or do not fit a gutter, stderr also offers verified moves and the grid they make, with the lane order beside it for a swimlane: apply the block whole or say why not (`--no-advice` turns the search off).
5. Embed. Chat: pass stdout to `show_widget` unchanged. Page: `--mode page --out file.html`, or `--out-dir DIR` for several models; `--assets none` for every diagram after the first on the same page. Markdown in a repository: `--format mermaid`.
6. Look at the result outside the chat only when asked or for a new layout: `reference/output.md`.

## Cost

Every tool call re-reads the whole conversation, and every widget stays in it.

1. Show in chat only the diagrams that changed; check intermediate states by the renderer's messages, not by widgets.
2. Keep models next to the document they serve, not in a temporary directory; change them with Edit, never by rewriting the whole file or by patch scripts.
3. One shell call per iteration: for pages, several models in one `--out-dir` call; for chat, every changed widget rendered in the same shell call.
4. Pass the fragment unchanged; never trim its CSS or JS. A widget loads them from jsDelivr; if its cards show without styles or lines, render again with `--assets inline`.
5. Do not read `render.py`, `diagrams/` or `template/`. If the reference lacks something, say so.

## Rules the renderer enforces

- Widget: 680 px; up to 3 columns for a schema, 4 for a flow, 5 lanes; 16 nodes. Page: 1100 px; 4 / 6 / 7 columns; 30 nodes. A title fits one line, text two lines.
- Schema lines attach to key rows; flow lines run through the gutters, never through a node.
- A branch label is at most three words; anything longer is a footnote `[n]`. A decision has at least two labelled exits.

## Common mistakes

| Mistake | What happened | Do instead |
|---|---|---|
| Mermaid because it is quick | Graph scaled to fit 680 px: 6–8 px fonts, edges through boxes; the owner rejected it | Model + `render.py`; mermaid only as `--format mermaid` for markdown |
| Hand-written cards and SVG | 30 KB of fresh CSS/JS every time, text down to 9 px, nothing validated | Model + `render.py` |
| Trimming the widget's CSS/JS by hand | A script and a copy of the fragment paid on every iteration | Pass stdout unchanged |
| Patch scripts for the model | A script per change, the JSON rewritten, extra calls | Edit the model file |
| Reading renderer sources | 25–100K characters of code in the conversation | The reference; say what it lacks |
| Showing unchanged diagrams again | Every widget stays in the context | Show only what changed |
| A line to every table with `connection_id` or `tenant_id` | Parallel dashed lines merge into one bundle | Grey hub, `outside: true`, a note in the card |
| Different colour per node | Colour must encode a category | Group by owner, kind of truth, participant |
| Long labels on lines | They collide with lines and nodes | Short label at the exit, the rest in `footnotes` |
| A node far from what it connects to | Long routes, crossings | Move the node; the map shows it |

## Files

- `render.py` — the renderer
- `reference/` — `common.md`, one file per kind, `output.md`
- `examples/` — one small model per kind
