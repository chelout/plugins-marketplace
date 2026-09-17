"""Kind `timeline`: a vertical rail of moments, one card per moment, entity
states as chips in a fixed order. No connectors."""
import json

from . import assets
from .common import BASE_MODES, ID_RE, ModelError, esc, labels_for, text_width, wrap_lines

MODES = {
    "widget": {"rail": 64, "max_moments": 12},
    "page": {"rail": 80, "max_moments": 24},
}
CHIP_MAX = 28


def mode_for(mode_name, overrides):
    mode = dict(BASE_MODES[mode_name])
    mode.update(MODES[mode_name])
    mode.update(overrides or {})
    return mode


def plan(model, mode_name, overrides=None, draft=False):
    errors, layout_errors, warnings = [], [], []
    mode = mode_for(mode_name, overrides)
    entities = model.get("entities") or []
    moments = model.get("moments") or []
    card_w = mode["total"] - mode["pad_l"] - mode["pad_r"] - mode["rail"] - 14

    ent_ids = []
    for e in entities:
        eid = e.get("id") if isinstance(e, dict) else None
        if not eid or not ID_RE.match(eid) or eid.endswith("?"):
            errors.append(f"сущность {eid!r}: id только из строчных латинских букв, цифр и _")
            continue
        if eid in ent_ids:
            errors.append(f"сущность {eid}: id повторяется")
        ent_ids.append(eid)
        if not e.get("label"):
            errors.append(f"сущность {eid}: нет label")
    if not ent_ids:
        errors.append("timeline: нужен список entities, чьи состояния показываются чипами")
    if len(ent_ids) > 4:
        warnings.append(f"сущностей {len(ent_ids)}: больше четырёх чипов в карточке читаются плохо")

    if len(moments) < 2:
        errors.append("timeline: нужно хотя бы два момента")
    if len(moments) > mode["max_moments"]:
        layout_errors.append(f"моментов {len(moments)}, режим {mode_name} допускает до {mode['max_moments']}; разбейте историю")
    seen = set()
    prev = {}
    rows = []
    for m in moments:
        mid = m.get("id")
        if not mid or not ID_RE.match(mid) or mid.endswith("?"):
            errors.append(f"момент {mid!r}: id только из строчных латинских букв, цифр и _")
            continue
        if mid in seen:
            errors.append(f"момент {mid}: id повторяется")
        seen.add(mid)
        label = m.get("label") or mid
        if text_width(label) > mode["rail"] - 18:
            layout_errors.append(f"момент {mid}: метка {label!r} шире рельса; укоротите")
        if not m.get("title"):
            errors.append(f"момент {mid}: нет title")
            continue
        tag = m.get("tag") or ""
        need = text_width(m["title"]) * 1.04 + 20 + (text_width(tag) * 0.9 + 8 if tag else 0)
        if need > card_w:
            layout_errors.append(f"момент {mid}: заголовок шире карточки на {need - card_w:.0f}px")
        text = m.get("text") or ""
        if text and wrap_lines(text, card_w - 20) > 2:
            layout_errors.append(f"момент {mid}: текст займёт больше двух строк")
        states = m.get("states") or {}
        for k in states:
            if k not in ent_ids:
                errors.append(f"момент {mid}: состояние для неизвестной сущности {k!r}")
        chips = []
        for eid in ent_ids:
            val = states.get(eid, prev.get(eid, "—"))
            if len(str(val)) > CHIP_MAX:
                warnings.append(f"момент {mid}: состояние {eid} длиннее {CHIP_MAX} символов, чип станет широким")
            chips.append({"id": eid, "value": str(val), "changed": eid in states and str(val) != str(prev.get(eid, "\0"))})
            prev[eid] = val
        rows.append({"id": mid, "label": label, "title": m["title"], "text": text, "tag": tag, "chips": chips})

    if errors:
        raise ModelError(errors + layout_errors, layout=layout_errors)
    if layout_errors and not draft:
        raise ModelError(layout_errors, layout=layout_errors)
    if layout_errors:
        warnings = ["черновик: " + x for x in layout_errors] + warnings
    ent_labels = {e["id"]: e.get("label", e["id"]) for e in entities if isinstance(e, dict) and e.get("id")}
    return {"kind": "timeline", "rows": rows, "entities": ent_ids, "ent_labels": ent_labels, "mode": mode,
            "card_w": card_w, "edges": [], "draft": bool(layout_errors)}, warnings


def render(model, mode_name, layout, warnings, assets_mode="inline", draft=False):
    mode = layout["mode"]
    labels = labels_for(model)
    total = mode["total"]
    style_vars = (f"--dg-rail:{mode['rail']}px;--dg-tlw:{total}px;--dg-padl:{mode['pad_l']}px;--dg-padr:{mode['pad_r']}px;"
                  f"--dg-cols:1;--dg-w:{layout['card_w']:.0f}px;--dg-gap:0px;--dg-rowgap:0px")
    summary = model.get("summary") or model.get("title") or "Таймлайн"
    before, after = assets.asset_blocks(assets_mode, mode_name, "timeline")
    parts = [before] if before else []
    parts.append(assets.section_open(model, "timeline", style_vars, esc("{}"), summary))
    if mode_name == "page" and model.get("title"):
        parts.append(f'<h3 style="margin:0 0 4px {mode["pad_l"]}px;font-size:16px;font-weight:500">{esc(model["title"])}</h3>')
    if draft or layout.get("draft"):
        parts.append(f'<span class="dg-draft">{esc(labels["draft"])}</span>')
    parts.append('<div class="dg-tl">')
    for r in layout["rows"]:
        tag = f'<span class="tag">{esc(r["tag"])}</span>' if r["tag"] else ""
        text = f'<div class="dg-t">{esc(r["text"])}</div>' if r["text"] else ""
        chips = "".join(f'<span class="dg-chip{" chg" if c["changed"] else ""}"><b>{esc(layout["ent_labels"][c["id"]])}</b>{esc(c["value"])}</span>'
                        for c in r["chips"])
        parts.append(f'<div class="dg-tlr"><div class="dg-tlm">{esc(r["label"])}</div>'
                     f'<div class="dg-c dg-tlc" data-t="{esc(r["id"])}"><div class="dg-h"><span class="ttl">{esc(r["title"])}</span>{tag}</div>'
                     f'{text}<div class="dg-chips">{chips}</div></div></div>')
    parts.append("</div>")
    parts.append(f'<div class="dg-legend"><span><span class="dg-chip chg" style="margin-right:4px"><b>{esc(labels["chip"])}</b>…</span>'
                 f'{esc(labels["changed"])}</span></div>')
    parts.append("</section>")
    if after:
        parts.append(after)
    return "\n".join(parts)


def ascii(model, layout):
    ents = layout["entities"]
    head = ["момент", "заголовок"] + [layout["ent_labels"][e] for e in ents]
    rows = [[r["label"], r["title"]] + [c["value"] + ("*" if c["changed"] else "") for c in r["chips"]] for r in layout["rows"]]
    widths = [max(len(str(x)) for x in col) for col in zip(head, *rows)]
    fmt = lambda row: "  ".join(str(x).ljust(w) for x, w in zip(row, widths))
    return "\n".join([fmt(head), fmt(["-" * w for w in widths])] + [fmt(r) for r in rows] + ["", "  * состояние изменилось в этот момент"])


def mermaid(model, layout):
    def safe(t):
        return str(t).replace(": ", " · ").replace(":", "∶")  # a colon splits events in mermaid timeline

    lines = ["timeline"]
    if model.get("title"):
        lines.append(f"    title {safe(model['title'])}")
    for r in layout["rows"]:
        parts = [safe(r["title"])]
        if r["text"]:
            parts.append(safe(r["text"]))
        parts += [safe(f"{layout['ent_labels'][c['id']]} {c['value']}") for c in r["chips"] if c["changed"]]
        lines.append(f"    {safe(r['label'])} : " + " : ".join(parts))
    return "\n".join(lines)
