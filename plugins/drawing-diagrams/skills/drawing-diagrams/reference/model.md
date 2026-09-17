# Model format and layout rules

`render.py MODEL.json` turns a JSON model into HTML. The model holds content
and a grid map only. Look, connectors, toggles and legend are the renderer's.
`kind` picks the renderer; this page documents the common parts and the
`schema` kind. Other kinds are described in design.md and will get their
sections here as they land.

## Common top level

| Field | Required | Meaning |
|---|---|---|
| `kind` | yes | `schema` today; `flow`, `swimlane`, `state`, `timeline`, `blocks` planned |
| `id` | no | Stable id for the `<section>`; defaults to a hash of the model |
| `title` | no | Caption; shown as a heading in page mode only |
| `summary` | no | One sentence for screen readers (falls back to `title`) |
| `grid` | yes | The grid map, see below |
| `groups` | yes | Colour groups, see below. At most 4 |
| `edges` | no | Connectors, shorthand strings or objects |
| `labels` | no | Override UI strings, see below |

## Grid map

```json
"grid": [
  "matrix   verdicts    attempts",
  "subject  history     checks",
  "conn     applicants  outbox"
]
```

One string per row; tokens separated by spaces are node ids, a dot is an
empty cell. The map's width is the number of grid columns; rows may be
shorter than the widest one. Every described node must appear exactly once.
`--check` prints the map back, so a misplaced node is visible before any
render.

## Groups

```json
"groups": {
  "ven": {"label": "истина вендора", "ramp": "teal"},
  "out": {"label": "за портом адаптера", "ramp": "gray", "outside": true}
}
```

`ramp` is one of purple, teal, coral, pink, gray, blue, green, amber, red.
Colour must encode a category (owner, kind of truth, subsystem), never "which
node". `outside: true` draws a dashed border; use it for things that already
exist or belong to another module. Prefer purple, teal, coral, pink for
categories and gray for outside; blue, green, amber, red carry UI meanings.

## Edges

Shorthand: `"from -> to | modifiers"`. For `schema` the ends are
`table.column`; modifiers are comma-separated: `logical` (dashed join without
a constraint; default is `fk`), `right` or `left` (route along the outer
margin), `ends=a/b` with `plain`, `one` or `many` (default `many/one`).

```json
"edges": [
  "history -> verdicts",
  "verdicts.attempt_id -> attempts.attempt_id | ends=plain/one",
  "outbox.external_correlation_id -> attempts.external_attempt_id | logical, right"
]
```

The object form `{"from": ["a", "col"], "to": ["b", "col"], "kind": "fk",
"from_end": "many", "to_end": "one", "route": "auto"}` is accepted too.

## Labels

Defaults are Russian. Override any of: `more` ("ещё {n} {cols}"), `cols`
(three plural forms), `collapse`, `open_all`, `close_all`, `fk`, `logical`,
`one`, `many`, `draft`. English: `"cols": ["column", "columns", "columns"]`.

## Modes and flags

| | widget | page |
|---|---|---|
| Width | 680 px | 1100 px |
| Colours, fonts | same in both: white ground and cards, own tokens, dark theme via `data-mode`, `data-theme` or `prefers-color-scheme`; nothing from the host | same |
| Embed | pass the fragment to `show_widget` as HTML | paste into the page; `--no-assets` for the second diagram |

`--width PX` changes the total width (a padded container, a narrower chat).
`--format mermaid` writes the model as mermaid for a markdown document: a
secondary rendering whose layout mermaid picks itself. `--format ascii`
writes what `--check` prints. `--draft` is reserved for kinds with a router;
for `schema` every layout error must be fixed.

Icons are inline SVG and fonts are system stacks: no icon font, no web font,
no external resource. The output passes an artifact CSP. Connector corners
are rounded with an 8 px radius (less where a segment is shorter), so two
lines diverging from one gutter read as two lines, not as a crossing.

## Kind `schema`

### Tables

```json
{
  "id": "verdicts", "name": "kyc_verdicts", "group": "ven",
  "subtitle": "вердикты · истина вендора",
  "columns": [
    {"name": "connection_id", "type": "uuid", "flags": ["PK"], "key": "connection"},
    {"name": "review_status", "type": "text"},
    {"name": "attempt_id", "type": "uuid", "flags": ["FK", "N"], "key": "attempt"}
  ],
  "details": ["<code>review_status</code>: approved · declined_retry · ..."],
  "notes": ["claim: UNIQUE (connection_id, user_id) WHERE status = open"]
}
```

- `id`: lowercase latin, digits, underscore; used in the grid map and edges.
- `columns[].flags`: subset of `PK`, `FK`, `U` (unique), `N` (nullable).
- `columns[].key`: icon and "key row" marker. One of connection, tenant,
  user, profile, attempt, id, check, external, kind, key, link, dot. Use the
  same key name for the same concept in every table.
- A column is a key row if it has `key` or any of PK/FK/U. Key rows are always
  visible and are the only rows connectors can attach to. Other columns sit
  behind the "ещё N колонок" toggle (page mode opens them by default).
- A partial unique index is not `U`: mark the column with `key` and state the
  predicate in `details`.
- `details`: lines shown only when the card is open. Raw HTML allowed; use
  `<code>` for identifiers and `&lt;` for a literal `<`. Value dictionaries,
  CHECK constraints and indexes go here.
- `notes`: lines always visible under the columns. One or two at most.

### Geometry

- Same row, adjacent columns: the line leaves the left card's key row and
  enters the right card's key row. Both columns are required.
- Same column, adjacent rows: field to field as well. The line leaves the
  key row sideways, runs down or up the gutter beside the column and enters
  the other card's key row from the same side. Both columns are required. The
  renderer picks the side whose anchors are free (the inner gutter first);
  when both sides of a row are taken it refuses and asks to move a table.
- Anything else: `right` or `left` runs the line along the outer margin; both
  tables must sit in the outermost column on that side. Otherwise the
  renderer refuses: move the tables.
- One anchor (table, column, side) serves one edge. Lines sharing a gutter
  are spread 8 px apart and ordered so that a line does not cut the entry
  of its neighbour. Margin routes run 14 px outside the outer cards.
- Two routes on one side of a column cross when their spans overlap end to
  end (one enters higher but ends earlier), whatever their order; the check
  counts such crossings and names the pair. Fixes: the other side (another
  key column of the same FK), a different order of key rows in the card so
  the spans nest, or another cell.
- No star of `connection_id` or `tenant_id` edges from every application
  table to a hub (`tenants`, `provider_connections`). Grey the hub, mark it
  `outside`, say so in its `notes`. Real FKs of a bridge table are drawn.

### Modes

Widget: up to 3 grid columns, 196 px cards at 3, key rows only, cards
collapsed. Page: up to 4 columns, 236 px cards at 4, types on key rows,
cards open. `--open` and `--types` bring the page behaviour into widget mode.
A key column name longer than about 20 characters (`external_correlation_id`)
does not fit a 196 px card: plan a 2-column map from the start, the check
will ask for it anyway. `ends=many/many` is allowed for a many-to-many join
through a key pair.

### Checks

Errors stop the render: unknown group, ramp, flag, key or table; a table not
in the map or in it twice; a grid wider than the mode allows; an edge between
non-adjacent cells without a route; a route on tables not in the outer
column; an edge column that is not a key row; two edges on one anchor.
Warnings continue: a key row wider than the card (the name wraps), a table
without any key row, more than four groups, empty rows or columns in the map,
a grid row whose tallest card is more than twice the height of the shortest.
Treat warnings as errors unless the user accepts the trade-off.

## Verifying the output

Page mode: open the HTML from any static server. Widget mode: render once
more with `--harness` for a standalone page around the fragment (the
harness is the only way to see a widget fragment outside the chat), open
it, then pass the plain fragment to `show_widget`. The in-app browser does not open `file://` and
`preview_start` needs a launch config in the project, so serve the folder
yourself: `python3 -m http.server 8768 -d <folder> &` and open
`http://localhost:8768/<file>`; stop it by its PID, never by `pkill` on the
process name, another server may be running. Both modes paint their own white ground. Check
three things: no line crosses a card, no name is cut, the legend lists
exactly the groups used. Click a toggle and confirm the lines follow.

## Kind `flow`

An algorithm: steps, decisions, outcomes. The renderer routes the lines.

```json
{
  "kind": "flow",
  "groups": {"graph": {"label": "граф", "ramp": "purple"}, "res": {"label": "резолвер", "ramp": "teal"}},
  "nodes": [
    {"id": "start", "kind": "terminal", "group": "graph", "title": "Вход в узел KYC"},
    {"id": "covered?", "group": "res", "title": "Покрыто целиком?", "text": "approved-строка учётки содержит всё требование"},
    {"id": "covered", "kind": "terminal", "group": "res", "title": "covered: approved"}
  ],
  "grid": [
    "start     .",
    "covered?  covered"
  ],
  "edges": [
    "start -> covered?",
    "covered? -> covered : да",
    "covered? -> live? : нет [1]"
  ],
  "footnotes": ["Полный текст причины, когда три слова не вмещают её."],
  "routes": {"Марк: покрыто": ["start", "covered?", "covered"]}
}
```

### Nodes

- `kind`: `step` (default), `decision`, `terminal`, `note`. An id ending in `?`
  is a decision without saying so. A decision shows a `?` marker in its
  header and must have at least two labelled exits.
- `title`: one line; the check refuses a title that would wrap. `text`: up
  to two lines (a greedy word wrap is simulated). A terminal shows only its
  title, as a pill. A note is a dashed card with no colour and no edges.
- `group`: colour of the header band. Optional; without it the card is
  neutral.

### Grid and routing

Place nodes with the map. Put the main path down the first column and
branches to the right, so that most lines are short. Any two cells can be
connected: the router walks the gutters between columns and rows, including
the outer margins left and right of the grid, and crosses empty cells, never
a node. It prefers to leave a node downward or sideways and to enter from
above; a line leaves through the top or enters from below only when nothing
else works, so a back edge (a loop to an earlier step) is drawn along the
margin. Lines are routed together: crossing another line costs the most,
then leaving through the top, then passing through another line's corner,
leaving a node through a side another line already uses, entering beside
another arrow, running along a line or along the outer margin; every line is
rerouted twice more with the others in place, so exits spread over the
sides of a node and arrows into one node arrive from different sides. Lines
that share a gutter are spread 8 px apart in an order that follows where
each one turns, and two lines meeting end to end in a gutter are spread the
same way, so their corners sit side by side instead of on top of each
other. The map still decides most of it: a node placed far from its
neighbours produces long detours. A line that cannot avoid a node is an error naming
the edge; free a cell or move a node. Parallel lines on one gutter are
spread 8 px apart. `--check` prints the map with the routed lines and the
number of line crossings; three or more crossings are a warning.

### Edges

`"a -> b : label [n] | dashed"`. The label sits at the exit of the line next
to the source node and is at most three words or 24 characters; longer text
goes to `footnotes` and is referenced with `[n]` (a circled number appears
on the line, the list appears under the diagram). `dashed` marks an
asynchronous or optional transition. The object form `{"from", "to",
"label", "dashed"}` is accepted.

Where a label goes follows the shape of the route, and the check measures it
in pixels exactly where `drawFlow` in `template/core.js` draws it: card width
and gaps come from the mode, the 8 px spread of parallel lines from the
router, the text width from glyph widths measured in a browser (macOS system
font; a footnote marker such as ① is 10 px, wider than any digit). The text
keeps 2 px from a card edge. The offsets live in two places, `LABEL_*` in
`diagrams/flow.py` and the label branch of `drawFlow`; change them together.

- A straight line down or up keeps the label at the exit, 5 px beside the
  line, in the gutter under or over the card: a card width of room.
- A straight sideways exit starts the label 3 px from the card edge. Into an
  occupied neighbour the room is the gutter less 5 px: 23 px in a widget flow,
  state or blocks (gutter 28), 27 px on a page (gutter 32), 13 px in a widget
  swimlane (gutter 18). "да", "нет", "RED" fit a flow, "нет ①" (32 px) fits
  none of them. Into an empty neighbour: a gutter and a card width less 20 px.
- A line that turns carries its label on the second segment. Above a
  horizontal one the label ends 6 px before the far end and must not reach
  back past the line's own bend, so a line that goes down and then sideways
  into its target has half a card and a gutter, not a whole cell.
- Beside a vertical one the label stands 6 px off the line, moved with it when
  parallel lines spread, right side before left. By default `core.js` centres
  it on the segment, at a height that depends on how tall the cards are, which
  the check cannot know; so the check keeps that place only when the side is
  clear in every row the middle can fall in (the rows of cards and gutters the
  segment passes, less the target card it ends on). Otherwise it pins the label
  to one of those rows, the middle first and the rows where the line turns
  last, and hands the row to `core.js` as `ly` (as it hands the side as `ls`).
  Clear means: off the cards of the row, off every other line and a word space
  off every label already placed (labels with a single place go first). A
  gutter row has no cards: a line running down a gutter between two occupied
  cells gets its label in the gutter above or below them, since beside the
  cards themselves only half a gutter less 6 px is left, less than one
  letter. At most a card width less 20 px.

The check refuses a label with no place, warns when its only place lies on
another line, when two labels would land in one place, or when a label above
a horizontal segment would sit on another line. The fixes are a shorter
label, a footnote, or moving the target so the line leaves downward. A
reference to a footnote also works at the end of a node's `text` ("… [2]"),
for a note that needs one.

### Routes

`routes` maps a scenario name to a list of node ids. Each consecutive pair
must be an edge, in that direction. Routes become chips above the diagram;
a click highlights the path and dims the rest. Use them for the cases a
reviewer will ask about ("проведи Марка по правилам").

### How much text fits

| kind, mode, columns | card | title, chars | text, chars (2 lines) | items, chars |
|---|---|---|---|---|
| flow, widget, 3 | 199 px | 22 (decision 19) | 48 | — |
| flow, widget, 4 | 142 px | 15 (decision 12) | 32 | — |
| swimlane, widget, 5 | 114 px | 9 | 24 | — |
| state, widget, 2 | 312 px | 38 | 80 | — |
| blocks, widget, 3 | 199 px | 22 | 48 | 44 each |
| flow, page, 4 | 242 px | 28 | 60 | — |
| flow, page, 6 | 151 px | 16 | 36 | — |

Counts assume Cyrillic; Latin fits about a fifth more. A title never wraps,
text wraps by words, so one long word costs a line. A hub state or step
with many transitions goes in a middle column, never the first: its lines
must be able to leave left, down and right, or they bunch into one gutter
and their labels collide.

### Limits and checks

Widget: up to 4 columns, 16 nodes. Page: up to 6 columns, 30 nodes. More
means an overview plus detail diagrams. Errors: a node in the map but not
described or the reverse, a node placed twice, a decision with fewer than two
exits or an unlabeled branch, a label over the limit without a footnote, a
route through a pair without an edge, an unroutable line, more nodes or
columns than the mode allows, a title or text that does not fit. Warnings:
a node with no incoming edge outside the first row, a non-terminal with no
exit, three or more crossings, empty rows or columns, an unused footnote.
`--draft` turns the layout errors (routing, limits, width) into warnings,
drops the lines it could not route and stamps the output "черновик".

## Kind `swimlane`

A flow whose columns are participants and whose rows are steps in time.

```json
{
  "kind": "swimlane",
  "groups": {"user": {"label": "пользователь", "ramp": "pink"}, "graph": {"label": "граф", "ramp": "purple"}},
  "lanes": ["user", "graph"],
  "nodes": [{"id": "buy", "title": "Покупка", "text": "Марк жмёт «купить»"}, {"id": "node", "title": "Узел KYC"}],
  "grid": [
    "buy  .",
    ".    node"
  ],
  "edges": ["buy -> node"]
}
```

- `lanes` lists group ids, one per grid column, left to right. A node's colour
  comes from its lane; a `group` that disagrees with the lane is an error.
- Rows are numbered automatically and the number appears in each node. Two
  nodes in one row read as simultaneous and raise a warning.
- Up to 5 lanes in widget mode (cards about 114 px, titles up to about 13
  characters), 7 in page mode. Merge minor participants into one lane rather
  than exceeding the limit.
- Everything else (edges, labels, footnotes, routes, checks) is as in `flow`.

## Exports

`--format ascii` prints the map with routed lines, the edge list and the
crossing count; `--check` prints the same to stdout (errors and warnings
stay on stderr), so a script can compare grid variants by their output.
`--format mermaid` writes `flowchart TD` (a `subgraph` per lane for a
swimlane) with the same nodes, labels and dashed edges, and the footnotes as
`%%` comments, for a markdown document; mermaid lays it out itself, so treat
it as the secondary rendering.

## Kind `state`

A lifecycle: the same engine as `flow`, nodes default to `state` (a card
with a colour stripe on the left, the state name as title, its meaning as
text). Use `terminal` for "нет строки" and `note` for a fact that is not a
state (an expired `valid_until` keeps the status and only leaves the
projection). Transitions are edges with a short reason at the exit; the
vendor's signal vocabulary goes to a footnote. Routes name the stories a
reviewer asks about ("Кира: изъятие документа"). Example:
examples/verdict-row-lifecycle.json. `--format mermaid` writes
`flowchart LR` with stadium nodes.

## Kind `blocks`

A composition: nodes default to `block`, a card with a header band and
`items`, up to five short lines (who writes, who reads, what it derives).
Edges are optional; use them for the numbered path of one check through the
blocks ("1 читает approved", "6 resume: covered"), labels follow the flow
rules. Up to 3 columns and 12 blocks in widget mode, 5 and 20 in page mode.
Example: examples/four-blocks.json.

## Kind `timeline`

A story over time. No grid, no edges.

```json
{
  "kind": "timeline",
  "entities": [{"id": "verdicts", "label": "вердикты"}, {"id": "attempts", "label": "попытки"}],
  "moments": [
    {"id": "t1", "label": "t1", "title": "Покупка: документ, селфи", "text": "1 нет → 2 нет → 4b fire",
     "states": {"verdicts": "нет", "attempts": "A open {t1}"}},
    {"id": "t4r", "label": "t4′", "tag": "вариант", "title": "A RED retry", "states": {"attempts": "A declined_retry"}}
  ]
}
```

- `entities`: up to four, in the order the chips appear on every card.
- `moments`: at most 12 in widget mode, 24 in page mode. `label` is the
  rail mark (t1, a date), `tag` a small uppercase word next to the title
  (вебхук, вариант). `states` lists only what changed; a missing entity
  keeps its previous value. A chip whose value changed is highlighted.
- Checks: unknown entity in `states`, duplicate ids, a title that wraps, text
  over two lines, a chip value over 28 characters (warning).
- `--format mermaid` writes a mermaid `timeline` with the title, the text and
  the changed states as events; colons are replaced because mermaid splits
  events on them. `--format ascii` prints a table of moments by entity with
  `*` on changed values. Example: examples/mark-timeline.json.
