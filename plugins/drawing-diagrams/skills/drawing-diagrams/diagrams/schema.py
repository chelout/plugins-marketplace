"""Kind `schema`: database tables as cards, FKs and logical joins as lines."""
import json

from . import assets, router
from .common import BASE_MODES, ICONS, CHEVRON, ID_RE, RAMPS, ModelError, esc, icon_svg, labels_for, plural
from .grid import ascii_map, check_placement, empty_lines, parse_grid

KEY_FLAGS = ("PK", "FK", "U")
FLAGS = ("PK", "FK", "U", "N")
ENDS = ("plain", "one", "many")

MODES = {
    "widget": {"gap": 32, "row_gap": 46, "char": 6.9, "max_cols": 3, "type_on_keys": False, "open": False},
    "page": {"gap": 40, "row_gap": 52, "char": 7.2, "max_cols": 4, "type_on_keys": True, "open": True},
}


def is_key(col):
    return bool(col.get("key")) or any(f in KEY_FLAGS for f in col.get("flags", []))


def icon_for(col):
    if col.get("key"):
        return col["key"]
    flags = col.get("flags", [])
    if "PK" in flags:
        return "key"
    if "FK" in flags:
        return "link"
    return "dot"


def mode_for(mode_name, overrides):
    mode = dict(BASE_MODES[mode_name])
    mode.update(MODES[mode_name])
    mode.update(overrides or {})
    return mode


# ---------------------------------------------------------------- validation


def plan(model, mode_name, overrides=None, draft=False):
    """Validate and compute edge geometry. Returns (layout, warnings); raises ModelError."""
    errors, layout_errors, warnings = [], [], []
    mode = mode_for(mode_name, overrides)

    groups = model.get("groups") or {}
    tables = model.get("tables") or []
    edges = model.get("edges") or []

    if not tables:
        errors.append("модель без таблиц")
    if len(groups) > 4:
        warnings.append(f"групп {len(groups)}: больше четырёх цветов читаются плохо")
    for gid, g in groups.items():
        if not ID_RE.match(gid) or gid.endswith("?"):
            errors.append(f"группа {gid!r}: id только из строчных латинских букв, цифр и _")
        if g.get("ramp") not in RAMPS:
            errors.append(f"группа {gid}: ramp должен быть одним из {', '.join(RAMPS)}")

    cells, grid_cols, grid_rows = parse_grid(model.get("grid"), errors)
    if grid_cols < 1 or grid_cols > mode["max_cols"]:
        layout_errors.append(f"grid шириной {grid_cols}: режим {mode_name} допускает от 1 до {mode['max_cols']} столбцов")
    grid_cols = max(grid_cols, 1)
    card_w = (mode["total"] - mode["pad_l"] - mode["pad_r"] - mode["gap"] * (grid_cols - 1)) / grid_cols
    ch = mode["char"]

    by_id = {}
    for t in tables:
        tid = t.get("id")
        if not tid or not ID_RE.match(tid) or tid.endswith("?"):
            errors.append(f"таблица {tid!r}: id только из строчных латинских букв, цифр и _")
            continue
        if tid in by_id:
            errors.append(f"таблица {tid}: id повторяется")
        by_id[tid] = t
        if not t.get("name"):
            errors.append(f"таблица {tid}: нет name")
        if t.get("group") not in groups:
            errors.append(f"таблица {tid}: группа {t.get('group')!r} не описана в groups")
        names = set()
        for col in t.get("columns") or []:
            name = col.get("name")
            if not name:
                errors.append(f"таблица {tid}: колонка без name")
                continue
            if name in names:
                errors.append(f"таблица {tid}: колонка {name} повторяется")
            names.add(name)
            bad = [f for f in col.get("flags", []) if f not in FLAGS]
            if bad:
                errors.append(f"таблица {tid}.{name}: неизвестные flags {bad}; допустимы {list(FLAGS)}")
            if col.get("key") and col["key"] not in ICONS:
                errors.append(f"таблица {tid}.{name}: key {col['key']!r} не из {', '.join(ICONS)}")
            if is_key(col):
                need = 10 + 12 + 4 + len(name) * ch + 4 + len(" ".join(col.get("flags", []))) * 6.6 + 10
                if mode["type_on_keys"]:
                    need += len(col.get("type", "")) * ch + 4
                if need > card_w:
                    warnings.append(
                        f"таблица {tid}.{name}: строка ключа шире карточки на {need - card_w:.0f}px "
                        f"(карточка {card_w:.0f}px), имя перенесётся; сузьте grid или сократите имя")
        if not any(is_key(c) for c in t.get("columns") or []):
            warnings.append(f"таблица {tid}: нет ни одной ключевой колонки, линии крепить не к чему")

    check_placement(cells, list(by_id), errors, "таблица")
    er, ec = empty_lines(cells, grid_cols, grid_rows)
    if er:
        warnings.append(f"пустые ряды в grid: {er}")
    if ec:
        warnings.append(f"пустые столбцы в grid: {ec}")

    # row balance: a very tall card next to a short one leaves a hole under the short one
    def est_height(t):
        cols = t.get("columns") or []
        keys = sum(1 for c in cols if is_key(c))
        h = 40 + 22 * keys + 22 * len(t.get("notes") or []) + 26
        if mode["open"]:
            h += 22 * (len(cols) - keys) + 16 * len(t.get("details") or [])
        return h

    rows_of = {}
    for tid, (r, _) in cells.items():
        if tid in by_id:
            rows_of.setdefault(r, []).append(by_id[tid])
    for r, ts in sorted(rows_of.items()):
        if len(ts) < 2:
            continue
        hs = sorted((est_height(t), t["id"]) for t in ts)
        lo, hi = hs[0], hs[-1]
        if hi[0] > 2 * lo[0] and hi[0] - lo[0] > 200:
            warnings.append(f"ряд {r}: карточка {hi[1]} примерно в {hi[0] / lo[0]:.1f} раза выше {lo[1]}, "
                            f"под короткой останется пустота; переставьте таблицы или сверните ряд")

    # edges: geometry on a pseudo lattice (x: column centres and gutters, y: grid row and key row),
    # so that crossings can be counted and parallel lines in one gutter ordered like in flows
    def key_index(t, cname):
        keys = [c["name"] for c in (t.get("columns") or []) if is_key(c)]
        return keys.index(cname) if cname in keys else 0

    def ypos(t, cname):
        return cells[t["id"]][0] * 1000 + key_index(t, cname) * 10 + 5

    def cross_count(paths):
        # crossings after the slot offsets are applied: two routes on one gutter that overlap
        # end to end cross whichever order they get, and only the offsets show it
        offs = router.assign_offsets(paths)
        bent = [[(x + ox * 0.001, y + oy * 0.001) for (x, y), (ox, oy) in zip(q, o)] for q, o in zip(paths, offs)]
        return router.crossings(bent), bent

    anchors, out_edges, ascii_edges, pseudo = {}, [], [], []
    for i, e in enumerate(edges):
        e = parse_edge(e, errors, i)
        if e is None:
            continue
        ta, ca, tb, cb = e["ta"], e["ca"], e["tb"], e["cb"]
        label = f"связь {ta}.{ca or '*'} -> {tb}.{cb or '*'}"
        if ta not in by_id or tb not in by_id:
            errors.append(f"{label}: неизвестная таблица")
            continue
        if ta == tb:
            errors.append(f"{label}: связь таблицы с собой не рисуется")
            continue
        if ta not in cells or tb not in cells:
            continue
        kind = e["kind"]
        ae, be = e["from_end"], e["to_end"]
        if kind not in ("fk", "logical"):
            errors.append(f"{label}: kind должен быть fk или logical")
        if ae not in ENDS or be not in ENDS:
            errors.append(f"{label}: from_end и to_end из {ENDS}")
        route = e["route"]
        if route not in ("auto", "right", "left"):
            errors.append(f"{label}: route из auto, right, left")
            continue
        A, B = by_id[ta], by_id[tb]
        (ra, xa), (rb, xb) = cells[ta], cells[tb]

        def key_col(t, cname):
            for col in t.get("columns") or []:
                if col.get("name") == cname:
                    return col
            return None

        def need_cols():
            ok = True
            for t, cname in ((A, ca), (B, cb)):
                if cname is None:
                    layout_errors.append(f"{label}: линия крепится к колонкам, укажите колонку у {t['id']}")
                    ok = False
                    continue
                col = key_col(t, cname)
                if col is None:
                    errors.append(f"{label}: у {t['id']} нет колонки {cname}")
                    ok = False
                elif not is_key(col):
                    errors.append(f"{label}: {t['id']}.{cname} не ключевая строка (PK/FK/U или key), "
                                  f"в свёрнутой карточке её не видно")
                    ok = False
            return ok

        if not need_cols():
            continue
        ya, yb = ypos(A, ca), ypos(B, cb)

        def path_for(gutter_x):
            return [(2 * xa + 1, ya), (gutter_x, ya), (gutter_x, yb), (2 * xb + 1, yb)]

        sa = sb = via = None
        if route == "auto":
            if ra == rb and abs(xa - xb) == 1:
                sa, sb = ("R", "L") if xa < xb else ("L", "R")
                path = path_for(2 * min(xa, xb) + 2)
            elif xa == xb and abs(ra - rb) == 1:
                # stacked cards: leave the key row sideways, run the gutter beside the column, enter the key row
                prefer = ["R", "L"] if xa < grid_cols - 1 else ["L", "R"]
                options = []
                for side in prefer:
                    if (ta, ca, side) in anchors or (tb, cb, side) in anchors:
                        continue
                    cand = path_for(2 * xa + 2 if side == "R" else 2 * xa)
                    options.append((cross_count(pseudo + [cand])[0] - cross_count(pseudo)[0], prefer.index(side), side, cand))
                if not options:
                    layout_errors.append(f"{label}: строки {ca} и {cb} заняты с обеих сторон другими связями; "
                                         f"переставьте таблицы или свяжите через другую колонку")
                    continue
                options.sort()
                _, _, side, path = options[0]
                sa = sb = side
                via = "G" + side
            else:
                layout_errors.append(f"{label}: ячейки {[ra, xa]} и {[rb, xb]} не соседние; переставьте таблицы "
                                     f"или задайте route: right|left по внешнему краю")
                continue
        else:
            edge_col = grid_cols - 1 if route == "right" else 0
            if xa != edge_col or xb != edge_col:
                layout_errors.append(f"{label}: route {route} требует обе таблицы в столбце {edge_col}")
                continue
            sa = sb = "R" if route == "right" else "L"
            via = sa
            path = path_for(2 * grid_cols if route == "right" else 0)

        for t, cname, side in ((ta, ca, sa), (tb, cb, sb)):
            k = (t, cname, side)
            if k in anchors:
                layout_errors.append(f"{label}: точка крепления {t}.{cname} ({side}) уже занята связью {anchors[k]}")
            anchors[k] = label

        pseudo.append(path)
        out_edges.append({"a": [ta, ca, sa], "b": [tb, cb, sb], "d": 1 if kind == "logical" else 0,
                          "ae": ae, "be": be, "via": via, "off": 0, "_label": label})
        ascii_edges.append(f"{ta}.{ca} -> {tb}.{cb}  [{kind}{', ' + route if route != 'auto' else ''}]")

    # parallel lines in one gutter, ordered so that a fan does not cross itself
    for e, offs in zip(out_edges, router.assign_offsets(pseudo)):
        e["off"] = offs[1][0]
    # what still crosses
    n_cross, bent = cross_count(pseudo)
    segs = [router.segments(q) for q in bent]
    for i in range(len(pseudo)):
        for j in range(i + 1, len(pseudo)):
            hit = any(a[0] != b[0] and (
                (a[0] == "v" and b[2] < a[1] < b[3] and a[2] < b[1] < a[3]) or
                (a[0] == "h" and a[2] < b[1] < a[3] and b[2] < a[1] < b[3]))
                for a in segs[i] for b in segs[j])
            if hit:
                warnings.append(f"{out_edges[i]['_label']} пересечёт {out_edges[j]['_label']}; переставьте таблицы "
                                f"или свяжите через другую колонку")
    for e in out_edges:
        e.pop("_label", None)

    if errors or layout_errors:
        raise ModelError(errors + layout_errors, layout=layout_errors)

    return {"edges": out_edges, "card_w": card_w, "grid_cols": grid_cols, "grid_rows": grid_rows,
            "cells": cells, "mode": mode, "tables": by_id, "ascii_edges": ascii_edges, "crossings": n_cross}, warnings


def parse_edge(e, errors, i):
    """Accept the object form {from, to, kind, from_end, to_end, route} and the
    shorthand "a.col -> b.col | logical, right"."""
    label = f"связь #{i + 1}"
    if isinstance(e, str):
        body, _, mods = e.partition("|")
        if "->" not in body:
            errors.append(f"{label}: ожидается 'a.col -> b.col'")
            return None
        left, right = (s.strip() for s in body.split("->", 1))
        ta, _, ca = left.partition(".")
        tb, _, cb = right.partition(".")
        out = {"ta": ta.strip(), "ca": ca.strip() or None, "tb": tb.strip(), "cb": cb.strip() or None,
               "kind": "fk", "from_end": "many", "to_end": "one", "route": "auto"}
        for m in (x.strip() for x in mods.split(",") if x.strip()):
            if m in ("fk", "logical"):
                out["kind"] = m
            elif m in ("right", "left"):
                out["route"] = m
            elif m.startswith("ends="):
                a, _, b = m[5:].partition("/")
                out["from_end"], out["to_end"] = a or "many", b or "one"
            else:
                errors.append(f"{label}: неизвестный модификатор {m!r}; допустимы fk, logical, right, left, ends=a/b")
        return out
    try:
        fa, fb = e["from"], e["to"]
        return {"ta": fa[0], "ca": fa[1] if len(fa) > 1 else None, "tb": fb[0], "cb": fb[1] if len(fb) > 1 else None,
                "kind": e.get("kind", "fk"), "from_end": e.get("from_end", "many"),
                "to_end": e.get("to_end", "one"), "route": e.get("route", "auto")}
    except (KeyError, TypeError, IndexError):
        errors.append(f"{label}: from и to должны быть [table_id, column] или [table_id]")
        return None


# ------------------------------------------------------------------- render


def card_html(t, group, layout, labels):
    mode = layout["mode"]
    outside = bool(group.get("outside"))
    ramp = group["ramp"]
    cols = t.get("columns") or []
    keys = [c for c in cols if is_key(c)]
    extras = [c for c in cols if not is_key(c)]
    r, c = layout["cells"][t["id"]]
    cls = "dg-c" + (" out" if outside else "") + (" open" if mode["open"] else "")
    parts = [f'<div class="{cls}" data-t="{esc(t["id"])}" data-r="{r}" data-c="{c}" style="grid-row:{r + 1};grid-column:{c + 1}">']
    sub = f"<small>{esc(t['subtitle'])}</small>" if t.get("subtitle") else ""
    parts.append(f'<div class="dg-h r-{ramp}">{esc(t["name"])}{sub}</div>')
    for col in keys:
        flags = " ".join(col.get("flags", []))
        typ = f"<em>{esc(col.get('type', ''))}</em>" if mode["type_on_keys"] else ""
        rcls = "dg-r t" if mode["type_on_keys"] else "dg-r"
        parts.append(f'<div class="{rcls}" data-c="{esc(col["name"])}">{icon_svg(icon_for(col))}'
                     f'<span>{esc(col["name"])}</span>{typ}<b>{esc(flags)}</b></div>')
    for col in extras:
        flags = " ".join(col.get("flags", []))
        parts.append(f'<div class="dg-r x"><span>{esc(col["name"])}</span><em>{esc(col.get("type", ""))}</em>'
                     f'<b>{esc(flags)}</b></div>')
    details = t.get("details") or []
    if details:
        parts.append('<div class="dg-x x">' + "".join(f"<div>{d}</div>" for d in details) + "</div>")
    notes = t.get("notes") or []
    if notes:
        parts.append('<div class="dg-n">' + "<br>".join(notes) + "</div>")
    if extras or details:
        n = len(extras)
        more = labels["more"].format(n=n, cols=plural(n, labels["cols"]))
        text = labels["collapse"] if mode["open"] else more
        parts.append(f'<button type="button" class="dg-toggle" data-more="{esc(more)}">{CHEVRON}'
                     f'<span>{esc(text)}</span></button>')
    parts.append("</div>")
    return "".join(parts)


def legend_html(model, labels):
    items = []
    for gid, g in (model.get("groups") or {}).items():
        style = ' style="border-style:dashed"' if g.get("outside") else ""
        items.append(f'<span><span class="sw sw-{g["ramp"]}"{style}></span>{esc(g.get("label", gid))}</span>')
    items.append('<span><svg width="34" height="10" viewBox="0 0 34 10"><path d="M1 5H33" stroke="currentColor" '
                 f'stroke-width="1.5" fill="none"/></svg>{esc(labels["fk"])}</span>')
    items.append('<span><svg width="34" height="10" viewBox="0 0 34 10"><path d="M1 5H33" stroke="currentColor" '
                 f'stroke-width="1.5" stroke-dasharray="5 4" fill="none"/></svg>{esc(labels["logical"])}</span>')
    items.append('<span><svg width="22" height="10" viewBox="0 0 22 10"><path d="M1 5H14" stroke="currentColor" '
                 f'stroke-width="1.5" fill="none"/><circle cx="17" cy="5" r="3" fill="currentColor"/></svg>{esc(labels["one"])}</span>')
    items.append('<span><svg width="26" height="12" viewBox="0 0 26 12"><path d="M1 6H14M14 6L24 1M14 6L24 6M14 6L24 11" '
                 f'stroke="currentColor" stroke-width="1.5" fill="none"/></svg>{esc(labels["many"])}</span>')
    return '<div class="dg-legend">' + "".join(items) + "</div>"


def render(model, mode_name, layout, warnings, with_assets=True, draft=False):
    mode = layout["mode"]
    labels = labels_for(model)
    groups = model["groups"]
    style_vars = (f"--dg-cols:{layout['grid_cols']};--dg-w:{layout['card_w']:.0f}px;--dg-gap:{mode['gap']}px;"
                  f"--dg-rowgap:{mode['row_gap']}px;--dg-padl:{mode['pad_l']}px;--dg-padr:{mode['pad_r']}px")
    summary = model.get("summary") or model.get("title") or "Схема таблиц"
    labels_js = esc(json.dumps({k: labels[k] for k in ("collapse", "open_all", "close_all")}, ensure_ascii=False))

    parts = []
    if with_assets:
        parts.append(assets.style_block({g["ramp"] for g in groups.values()}))
    parts.append(assets.section_open(model, "schema", style_vars, labels_js, summary))
    if mode_name == "page" and model.get("title"):
        parts.append(f'<h3 style="margin:0 0 4px {mode["pad_l"]}px;font-size:16px;font-weight:500">{esc(model["title"])}</h3>')
    if draft:
        parts.append(f'<span class="dg-draft">{esc(labels["draft"])}</span>')
    parts.append(f'<div class="dg-bar"><button type="button" class="dg-all">{esc(labels["open_all"])}</button></div>')
    parts.append('<div class="dg-grid">')
    for t in model["tables"]:
        parts.append(card_html(t, groups[t["group"]], layout, labels))
    parts.append('<svg class="dg-svg" aria-hidden="true"></svg></div>')
    parts.append(legend_html(model, labels))
    parts.append(assets.edges_json(layout["edges"]))
    parts.append("</section>")
    if with_assets:
        parts.append(assets.script_block())
    return "\n".join(parts)


def ascii(model, layout):
    """The map plus the edge list, for --check."""
    return ascii_map(layout["cells"], layout["grid_cols"], layout["grid_rows"]) + "\n" + \
        "\n".join("  " + e for e in layout["ascii_edges"]) + f"\n  пересечений линий: {layout['crossings']}"


def mermaid(model, layout):
    """Secondary rendering for markdown: erDiagram with the same tables and edges."""
    lines = ["erDiagram"]
    for t in model["tables"]:
        lines.append(f"    {t['name']} {{")
        for col in t.get("columns") or []:
            # mermaid wants "PK, FK" with a comma and calls unique UK
            flags = ", ".join({"U": "UK"}.get(f, f) for f in col.get("flags", []) if f in KEY_FLAGS)
            typ = (col.get("type") or "text").replace("[]", "_array").replace(" ", "_")
            lines.append(f"        {typ} {col['name']}{(' ' + flags) if flags else ''}")
        lines.append("    }")
    by_id = layout["tables"]
    for e in layout["edges"]:
        a, b = by_id[e["a"][0]]["name"], by_id[e["b"][0]]["name"]
        left = "}o" if e["ae"] == "many" else "||"
        right = "o{" if e["be"] == "many" else "||"
        line = "--" if not e["d"] else ".."
        label = e["a"][1] or ""
        lines.append(f'    {a} {left}{line}{right} {b} : "{label}"')
    return "\n".join(lines)
