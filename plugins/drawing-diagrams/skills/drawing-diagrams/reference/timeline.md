# Kind `timeline`

A story over time: a rail of moments, one card per moment, entity states as chips. No grid, no edges,
no groups.

## Fields

| Field | Required | Meaning and limits |
|---|---|---|
| `entities[]` | yes | `{"id", "label"}`; up to four, in the order the chips appear |
| `moments[]` | yes | at least 2; at most 12 in widget mode, 24 in page mode |
| `moments[].id` | yes | lowercase latin, digits, `_` |
| `moments[].label` | no | rail mark (t1, a date), defaults to `id`; about 6 characters in widget mode |
| `moments[].tag` | no | small uppercase word next to the title |
| `moments[].title` | yes | one line: about 70 characters in widget mode, 120 in page mode, less with a tag |
| `moments[].text` | no | at most two lines |
| `moments[].states` | no | `{entity id: value}` for what changed; a value over 28 characters is a warning |

## Model

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
