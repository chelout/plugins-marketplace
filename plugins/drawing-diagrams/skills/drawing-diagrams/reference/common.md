# Model format: common parts

`render.py` checks a JSON model and turns it into HTML. The model holds content and a grid map only;
look, connectors, toggles and legend are the renderer's. `kind` picks the renderer and the file to read
next: `reference/schema.md` for `schema`; `reference/flow.md` for `flow`, `swimlane`, `state` and
`blocks`; `reference/timeline.md` for `timeline`. `reference/output.md` covers looking at a rendered
diagram and exports.

## Common top level

| Field | Required | Meaning |
|---|---|---|
| `kind` | yes | `schema`, `flow`, `swimlane`, `state`, `blocks` or `timeline` |
| `id` | no | Stable id for the `<section>`; defaults to a hash of the model |
| `title` | no | Caption; shown as a heading in page mode only |
| `summary` | no | One sentence for screen readers (falls back to `title`) |
| `grid` | yes, except `timeline` | The grid map, see below |
| `groups` | yes, except `timeline` | Colour groups, see below. At most 4 |
| `edges` | no | Connectors; the syntax is in the file of the kind |
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
A layout error prints the map back, and so does `--check`.

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

## Labels

Defaults are Russian. Override any of: `more` ("ещё {n} {cols}"), `cols`
(three plural forms), `collapse`, `open_all`, `close_all`, `fk`, `logical`,
`one`, `many`, `draft`. English: `"cols": ["column", "columns", "columns"]`.

## Modes and flags

| | widget | page |
|---|---|---|
| Width | 680 px | 1100 px |
| Colours, fonts | same in both: white ground and cards, own tokens, dark theme via `data-mode`, `data-theme` or `prefers-color-scheme`; nothing from the host | same |
| Assets (`--assets`) | `cdn` by default: links to the published CSS and JS; `inline` carries only what the diagram uses | `inline` by default: all CSS and JS; `none` for the second and later diagrams of a page |
| Embed | pass stdout to `show_widget` unchanged | paste into the page |

`--width PX` changes the total width (a padded container, a narrower chat).
`--format mermaid` writes the model as mermaid for a markdown document: a
secondary rendering whose layout mermaid picks itself. `--format ascii`
writes what `--check` prints. `--draft` is reserved for kinds with a router;
for `schema` every layout error must be fixed.

Icons are inline SVG and fonts are system stacks: no icon font, no web font.
With inline assets the output has no external resource and passes an artifact CSP;
with `--assets cdn` a widget loads its CSS and JS from jsDelivr. Connector corners
are rounded with an 8 px radius (less where a segment is shorter), so two
lines diverging from one gutter read as two lines, not as a crossing.

## Commands

```bash
python3 ${CLAUDE_SKILL_DIR}/render.py model.json --mode widget              # chat: stdout goes to show_widget
python3 ${CLAUDE_SKILL_DIR}/render.py model.json --mode page --out a.html
python3 ${CLAUDE_SKILL_DIR}/render.py a.json b.json --mode page --out-dir out
python3 ${CLAUDE_SKILL_DIR}/render.py model.json --check                     # the map and the checks only
python3 ${CLAUDE_SKILL_DIR}/render.py model.json --format mermaid            # markdown in a repository
```

Every render checks the model. On errors stdout is empty and stderr lists every problem at once. A text
that does not fit names its length and how many characters fit (`заголовок 24 симв., влезает 19`), so
one edit fixes it; a line or grid problem also prints the map. Several models in one call write nothing
when any of them fails. Warnings do not stop the render; treat them as errors unless the user accepts
the trade-off. A chat widget carries one diagram: render every widget separately.
