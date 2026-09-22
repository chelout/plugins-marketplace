# Kinds `flow`, `swimlane`, `state`, `blocks`

One engine for four kinds: steps and decisions, lanes of participants, states, blocks. Common fields,
grid and groups: `reference/common.md`.

## Fields

| Field | Required | Meaning and limits |
|---|---|---|
| `nodes[].id` | yes | lowercase latin, digits, `_`; a trailing `?` makes a decision |
| `nodes[].kind` | no | `step` (default in flow and swimlane), `decision`, `terminal`, `note`, `state` (default in state), `block` (default in blocks) |
| `nodes[].title` | yes | one line; widget: 22 characters at 3 columns (decision 19), 15 at 4 (decision 12), 8 in a 5-lane swimlane; page: 28 at 4 columns, 16 at 6 |
| `nodes[].text` | no | at most two lines, about twice the title budget; `[n]` at the end references a footnote; not shown on a terminal |
| `nodes[].group` | no | a key of `groups`; in a swimlane the lane gives the colour and a different `group` is an error |
| `nodes[].items` | no | `block` only: at most 5, each at most two lines (44 characters at 3 widget columns) |
| `lanes` | swimlane | group ids, one per grid column, left to right |
| `edges[]` | no | `"a -> b : label [n] \| dashed"`; a label is at most 3 words or 24 characters |
| `footnotes` | no | texts referenced as `[n]` from labels or node text |
| `routes` | no | `{"name": [ids]}`; every consecutive pair must be an edge |

Limits: widget 4 columns and 16 nodes (blocks 3 and 12, swimlane 5 lanes); page 6 columns and 30 nodes
(blocks 5 and 20, swimlane 7 lanes).

## Flow

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

Place nodes with the map. Put the main path down the first column and branches
to the right, so that most lines are short; a node placed far from its
neighbours produces long detours. Any two cells can be connected: lines run
along the gutters between columns and rows, including the outer margins, and
across empty cells, never through a node. A line prefers to leave a node
downward or sideways and to enter from above, so a back edge (a loop to an
earlier step) is drawn round the side of the cards, along a gutter or a
margin. Parallel lines in one gutter are spread apart, and a gutter, margin or
empty row holds only so many (an error, below). `--check` prints the map with
the routed lines and the number of line crossings; three or more crossings are
a warning.

Where a gutter holds more lines than fit or three lines cross, stderr also
carries an advice: a headline with what the moves buy (extra lines, crossings
or the length of the lines), the moves numbered, each with the count it moved,
and the grid they leave behind under `grid:`, ready to paste back into the
model. For a swimlane it prints `lanes:` as well; paste the two together, since
the columns travel with the lanes. Every move is verified by routing, and none
brings an error the model did not have or more warnings (the crossings warning
aside). The advice never changes the model: apply it by editing the grid, or
leave it and say why. Nothing is printed when no move improves the drawing.
The search takes up to several seconds on a full page; `--no-advice` turns it
off.

### Edges

`"a -> b : label [n] | dashed"`. The label sits by its own line: at the exit
next to the source node or, where the line turns, on its second segment. It
is at most three words or 24 characters; longer text goes to `footnotes` and
is referenced with `[n]` (a circled number appears on the line, the list
appears under the diagram). `dashed` marks an asynchronous or optional
transition. The object form `{"from", "to", "label", "dashed"}` is accepted.

The check measures a label in pixels where the page draws it; a footnote
marker such as ① is 10 px, wider than any digit. The text keeps 2 px from a
card edge. Each shape of route offers the places below, preferred first; all
labels are placed together, so a label takes a later place when that keeps a
line or another label off it.

- A straight line down or up: 5 px beside the line, right of it and else left,
  in the gutter under or over the card: a card width of room, up to the edge
  of the diagram; under a card whose row holds other cards, the next card
  ends it.
- A straight sideways exit: from 3 px off the card edge, above its line and
  else below. Into an occupied neighbour the room is the gutter less 5 px:
  23 px in a widget flow, state or blocks and in a page swimlane, 27 px in a
  page flow, state or blocks, 13 px in a widget swimlane. "да", "нет", "RED"
  fit a flow, "нет ①" (32 px) fits none of them. Into an empty neighbour: a
  gutter and a card width less 20 px.
- A horizontal second segment: over it, starting 6 px past the bend and
  running on away from the source, so a line that goes down and then sideways
  into its target has half a card and a gutter, not a whole cell; then under
  it; then over its far end.
- A vertical second segment: 6 px off the line, right side before left, at
  most a card width less 20 px. A line running down a gutter between two
  occupied cells gets its label in the gutter above or below them, since
  beside the cards less than one letter of room is left.

A label that fits none of its places is an error naming the room the roomiest
of them had and, where something stands in it, the nearest such thing: a card,
a line, another label's text or the edge of the diagram. Read them apart: the
room is what the cards and the edge leave, so a line named there can still run
through a text cut to that length. The check warns once when the place a label
takes lies on another line or label, once per line that runs through a label
on a horizontal segment, and once for a pair of labels that land in one place
— on the later of the two. The fixes are a shorter label, a footnote, or
moving the target so the line leaves downward. A reference to a footnote also
works at the end of a node's `text` ("… [2]"), for a note that needs one.

### Routes

`routes` maps a scenario name to a list of node ids. Each consecutive pair
must be an edge, in that direction. Routes become chips above the diagram;
a click highlights the path and dims the rest. Use them for the cases a
reviewer will ask about ("проведи Марка по правилам").

### How much text fits

| kind, mode, columns | card | title, chars | text, chars (2 lines) | items, chars |
|---|---|---|---|---|
| flow, widget, 3 | 196 px | 22 (decision 19) | 48 | — |
| flow, widget, 4 | 140 px | 15 (decision 12) | 32 | — |
| swimlane, widget, 5 | 114 px | 8 | 24 | — |
| state, widget, 2 | 308 px | 37 | 80 | — |
| blocks, widget, 3 | 196 px | 22 | 48 | 44 each |
| flow, page, 4 | 239 px | 28 | 60 | — |
| flow, page, 6 | 149 px | 16 | 36 | — |

Counts assume Cyrillic; Latin fits about 9% more. A title never wraps,
text wraps by words, and a word wider than the box is refused: the card
clips such a word instead of breaking it, so shorten it or spell it in
words. A hub state or step
with many transitions goes in a middle column, never the first: its lines
must be able to leave left, down and right, or they bunch into one gutter
and their labels collide.

### Limits and checks

Widget: up to 4 columns, 16 nodes. Page: up to 6 columns, 30 nodes. More
means an overview plus detail diagrams. Errors: a node in the map but not
described or the reverse, a node placed twice, a decision with fewer than two
exits or an unlabeled branch, a label over the limit without a footnote, a
route through a pair without an edge, an unroutable line (free a cell or move
a node), more lines in one gutter, margin or empty row than fit (the message
names it, how many go there, how many fit and the edges to move), more nodes
or columns than the mode allows, a title, text, item or label that does not
fit (the message names its length and how many characters fit, and for a
label what stands in its way), a single word in a text or item wider than its
box (the message names that word's length instead). Warnings: a node with no
incoming edge outside the first row, a non-terminal with no exit, three or
more crossings, empty rows or columns, an unused footnote. `--draft` turns the
layout errors (routing, limits, width) into warnings, drops the lines it could
not route and stamps the output "черновик".

## Swimlane

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
- Up to 5 lanes in widget mode (cards about 114 px, titles up to about 8
  characters), 7 in page mode. Merge minor participants into one lane rather
  than exceeding the limit.
- Everything else (edges, labels, footnotes, routes, checks) is as in `flow`.

## State

A lifecycle: the same engine as `flow`, nodes default to `state` (a card
with a colour stripe on the left, the state name as title, its meaning as
text). Use `terminal` for "нет строки" and `note` for a fact that is not a
state (an expired `valid_until` keeps the status and only leaves the
projection). Transitions are edges with a short reason at the exit; the
vendor's signal vocabulary goes to a footnote. Routes name the stories a
reviewer asks about ("Кира: изъятие документа"). Example:
examples/verdict-row-lifecycle.json. `--format mermaid` writes
`flowchart LR` with stadium nodes.

## Blocks

A composition: nodes default to `block`, a card with a header band and
`items`, up to five short lines (who writes, who reads, what it derives).
Edges are optional; use them for the numbered path of one check through the
blocks ("1 читает approved", "6 resume: covered"), labels follow the flow
rules. Up to 3 columns and 12 blocks in widget mode, 5 and 20 in page mode.
Example: examples/four-blocks.json.
