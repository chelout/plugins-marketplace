# Kinds `flow`, `swimlane`, `state`, `blocks`

One engine for four kinds: steps and decisions, lanes of participants, states, blocks. Common fields,
grid and groups: `reference/common.md`.

## Fields

| Field | Required | Meaning and limits |
|---|---|---|
| `nodes[].id` | yes | lowercase latin, digits, `_`; a trailing `?` makes a decision |
| `nodes[].kind` | no | `step` (default in flow and swimlane), `decision`, `terminal`, `note`, `state` (default in state), `block` (default in blocks) |
| `nodes[].title` | yes | one line; widget: 22 characters at 3 columns (decision 19), 15 at 4 (decision 12), 9 in a 5-lane swimlane; page: 28 at 4 columns, 16 at 6 |
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
spread 8 px apart, 6 or 5 px where the gutter is too narrow for that, and the
router sends a line round a gutter that is already full. `--check` prints the map with the routed lines and the
number of line crossings; three or more crossings are a warning.

Where a gutter holds more lines than fit or three lines cross, stderr also
carries an advice: the moves that lower that count, numbered, and the grid
they leave behind, ready to paste back into the model. The headline
names what the whole sequence buys — extra lines, crossings or the length of
the lines — and every step names the one it moved itself, so a step that only
shortened the lines says so instead of printing a count that stands still.
The last move always lowers the extra lines or the crossings: a sequence is
never padded with moves that only tidy the drawing. For a swimlane the block
prints `lanes:` under the grid as well, and the two are pasted back together —
the columns travel with the lanes, so the grid on its own would move cards
into other lanes. Every move is verified — the renderer routes the grid it
would produce and reports what it measured, not a guess — and no move is
offered that brings an error the model did not already have or leaves it with
more warnings than it had (the crossings warning aside): a warning may change
its kind, their number never grows. The advice never changes the model: apply it by editing
the grid, or leave it and say why. Nothing is printed when no move improves
the drawing. The search runs only when one of those two problems was
reported, and costs about half a second on a dozen cards, several seconds on
a full page of thirty; `--no-advice` turns it off.

### Edges

`"a -> b : label [n] | dashed"`. The label sits by its own line: at the exit
next to the source node, or, where the line turns, on its second segment,
which can carry the text as far as that segment's far end. It is at most
three words or 24 characters; longer text goes to `footnotes` and is
referenced with `[n]` (a circled number appears
on the line, the list appears under the diagram). `dashed` marks an
asynchronous or optional transition. The object form `{"from", "to",
"label", "dashed"}` is accepted.

Where a label goes follows the shape of the route, and the check measures it
in pixels exactly where the widget script draws it: card width
and gaps come from the mode, the 8 px spread of parallel lines from the
router, the text width from glyph widths measured in a browser (macOS system
font; a footnote marker such as ① is 10 px, wider than any digit). The text
keeps 2 px from a card edge.

The places below are listed in the order a label prefers them, and the check
does not simply take the first that fits: it chooses the places of all the
labels together, the arrangement with the fewest pairs of labels that overlap
first, then the fewest lines running through a text, then the most preferred
places. So a label gives up its first place for a later one when that takes a
line off it or parts it from another label, and keeps it otherwise.

- A straight line down or up keeps the label at the exit, 5 px beside the
  line, in the gutter under or over the card: a card width of room, up to the
  edge of the diagram. Right of the line first, and left of it where the right
  has no room — at the last column, or where another line turns there. The
  text stands between the card and the middle of the gutter, where lines turn:
  a line leaving or entering the same side of the card beside it runs through
  it, and so does a line along the gutter moved towards the card (4 px is
  enough in a widget, 8 px on a page); a line from the far side that turns
  along the middle stays clear, except over a card with two or more empty rows
  above it: there the gutter next to the card stands 16.5 px or less over it,
  and a line along its middle lies on the label of an exit up. A card shorter
  than its row hangs the text inside the row, so when the row holds other
  cards the next card ends the room, and a line drawn there at another card's
  height lies on the label.
- A straight sideways exit starts the label 3 px from the card edge, above its
  own line and, where that room is taken, below it. Into an occupied
  neighbour the room is the gutter less 5 px: 23 px in a widget flow, state or
  blocks (gutter 28), 27 px on a page (gutter 32), 13 px in a widget swimlane
  (gutter 18). "да", "нет", "RED" fit a flow, "нет ①" (32 px) fits none of
  them. Into an empty neighbour: a gutter and a card width less 20 px.
- A line that turns carries its label on the second segment. Over a horizontal
  one the label starts 6 px past the bend and runs on away from the source, so
  a line that goes down and then sideways into its target has half a card and
  a gutter, not a whole cell. It is drawn 9 px over that segment as the
  segment itself is drawn, so parallel lines moving it take their labels with
  them. Where a line comes down through the text there, the label goes 17 px
  under the same segment instead, or back to its far end. The three places
  have one room between them, unless a text reaches out of its gutter into the
  row of cards beside it, as one over or under a segment drawn far off the
  gutter's middle does: a card in its way there ends that place's room.
  Otherwise what chooses is what runs through each.
- Beside a vertical one the label stands 6 px off the line, moved with it when
  parallel lines spread, right side before left. By default the script centres
  it on the segment, at a height that depends on how tall the cards are, which
  the check cannot know; so the check keeps that place only when no card and
  no edge of the diagram takes the room in any row the middle can fall in (the
  rows of cards and gutters the segment passes, less the target card it ends
  on). Otherwise it pins the label to one of those rows, the middle first and
  the rows where the line turns last, and hands the place to the script as the
  label's anchor. A line or another label in one of those rows does not send
  the label away: those are priced against the other places above, so the
  middle can be kept and warned about instead. Only a card or the edge of the
  diagram drops a place outright, and that holds for every place, not this one
  alone; a text keeps 2 px off a card and a word space off another label. A
  gutter row has no cards: a line running down a gutter
  between two occupied cells gets its label in the gutter above or below them,
  since beside the cards themselves only half a gutter less 6 px is left, less
  than one letter. At most a card width less 20 px.

The check refuses a label that fits none of its places, naming the room the
roomiest of them had and, where something stands in it, what that is: a card,
a line, another label's text or the edge of the diagram. The two are measured
differently, so read them apart — the room is what the cards and the edge of
the diagram leave, while the thing named is the nearest of everything, so a
line named there can still run through a text cut to that length. The check
warns once when the place it takes lies on another line or label,
once per line that runs through a label on a horizontal segment, and once for
a pair of labels that land in one place — on the later of the two. The fixes
are a shorter label, a footnote, or moving the target so the line leaves
downward. A reference to a footnote also works at the end of a node's `text`
("… [2]"), for a note that needs one.

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
route through a pair without an edge, an unroutable line, more lines in one
gutter, margin or empty row than fit (the message names it, how many go there,
how many fit and the edges to move), more nodes or
columns than the mode allows, a title, text, item or label that does not fit (the message names its length and how many
characters fit, and for a label what stands in its way), a single word in a
text or item wider than its box (the message names that word's length
instead). Warnings:
a node with no incoming edge outside the first row, a non-terminal with no
exit, three or more crossings, empty rows or columns, an unused footnote.
`--draft` turns the layout errors (routing, limits, width) into warnings,
drops the lines it could not route and stamps the output "черновик".

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
- Up to 5 lanes in widget mode (cards about 114 px, titles up to about 9
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

