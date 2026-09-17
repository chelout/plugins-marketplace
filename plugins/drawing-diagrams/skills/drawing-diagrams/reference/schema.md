# Kind `schema`

Database tables as cards; foreign keys and logical joins as lines between key rows. Common fields, grid
and groups: `reference/common.md`.

## Fields

| Field | Required | Meaning and limits |
|---|---|---|
| `tables[].id` | yes | lowercase latin, digits, `_`; used in the grid map and edges |
| `tables[].name` | yes | table name in the header |
| `tables[].group` | yes | a key of `groups` |
| `tables[].subtitle` | no | small line under the name |
| `tables[].columns` | yes | list of columns, below |
| `tables[].details` | no | HTML lines shown only when the card is open |
| `tables[].notes` | no | lines always visible under the columns; one or two |
| `columns[].name` | yes | unique in the table; a key row name fits about 20 characters in a 3-column widget |
| `columns[].type` | no | shown on key rows in page mode or with `--types`, on the other rows when open |
| `columns[].flags` | no | subset of `PK`, `FK`, `U`, `N` |
| `columns[].key` | no | icon and key-row marker: connection, tenant, user, profile, attempt, id, check, external, kind, key, link, dot |
| `edges[]` | no | `"a.col -> b.col \| modifiers"`, see Edges |

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


## Tables

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

## Geometry

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

## Modes

Widget: up to 3 grid columns, 196 px cards at 3, key rows only, cards
collapsed. Page: up to 4 columns, 236 px cards at 4, types on key rows,
cards open. `--open` and `--types` bring the page behaviour into widget mode.
A key column name longer than about 20 characters (`external_correlation_id`)
does not fit a 196 px card: plan a 2-column map from the start, the check
will ask for it anyway. `ends=many/many` is allowed for a many-to-many join
through a key pair.

## Checks

Errors stop the render: unknown group, ramp, flag, key or table; a table not
in the map or in it twice; a grid wider than the mode allows; an edge between
non-adjacent cells without a route; a route on tables not in the outer
column; an edge column that is not a key row; two edges on one anchor.
Warnings continue: a key row wider than the card (the name wraps; the warning names how many characters fit), a table
without any key row, more than four groups, empty rows or columns in the map,
a grid row whose tallest card is more than twice the height of the shortest.
Treat warnings as errors unless the user accepts the trade-off.

