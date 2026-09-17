"""CSS, JS and page wrappers shared by every kind.

Styles and scripts are fragments under template/css and template/js. A page carries all of them;
a chat widget either links to the published build in template/dist (served by jsDelivr at the
commit named in template/dist/REF) or carries only the fragments its diagram uses."""
import hashlib
import json
from pathlib import Path

from .common import RAMPS, esc

TPL = Path(__file__).resolve().parent.parent / "template"
DIST = TPL / "dist"
CSS_PARTS = ("base", "schema", "flow", "lanes", "routes", "foot", "timeline")
JS_PARTS = ("head", "flow", "schema", "draw", "routes", "end")
FLOW_KINDS = ("flow", "swimlane", "state", "blocks")
CDN = ("https://cdn.jsdelivr.net/gh/chelout/plugins-marketplace@{ref}"
       "/plugins/drawing-diagrams/skills/drawing-diagrams/template/dist/{name}")


def ramp_css(ramps):
    if not ramps:
        return ""
    light, dark = [], []
    for r in sorted(ramps):
        s = RAMPS[r]
        light.append(f".dg .r-{r}{{background:{s[0]};color:{s[5]}}}.dg .r-{r} small{{color:{s[4]}}}"
                     f".dg .sw-{r}{{background:{s[0]};border-color:{s[4]}}}.dg .s-{r}{{border-left-color:{s[3]}}}")
        dark.append(f".dg .r-{r}{{background:{s[5]};color:{s[1]}}}.dg .r-{r} small{{color:{s[2]}}}")
    d = "".join(dark)

    def scoped(prefix):
        return d.replace(".dg ", prefix + " .dg ").replace("}.dg", "}" + prefix + " .dg")

    return ("".join(light) + scoped('[data-mode="dark"]') + scoped(':root[data-theme="dark"]')
            + "@media (prefers-color-scheme:dark){" + scoped(':root:not([data-mode]):not([data-theme="light"])') + "}")


def css_text(parts=CSS_PARTS, ramps=None):
    """Tokens, the named fragments in CSS_PARTS order, then the ramps: all nine when `ramps` is None,
    because a second diagram on a page (rendered with --assets none) may use colours the first did not."""
    body = "".join((TPL / "css" / f"{p}.css").read_text() for p in CSS_PARTS if p in parts)
    return (TPL / "tokens.css").read_text() + body + ramp_css(RAMPS if ramps is None else ramps)


def js_text(parts=JS_PARTS):
    return "".join((TPL / "js" / f"{p}.js").read_text() for p in JS_PARTS if p in parts)


def widget_parts(kind, edges, routes, footnotes):
    """(CSS parts, JS parts) of one diagram in a chat widget. A timeline draws nothing by script and a
    flow-like diagram without edges has nothing to draw; a schema needs its toggles either way."""
    css = ["base"]
    if kind == "schema":
        css.append("schema")
    elif kind == "timeline":
        css.append("timeline")
    else:
        css.append("flow")
        if kind == "swimlane":
            css.append("lanes")
        if routes:
            css.append("routes")
        if footnotes:
            css.append("foot")
    if kind == "timeline" or (kind in FLOW_KINDS and not edges):
        return css, []
    js = ["head", "schema" if kind == "schema" else "flow", "draw"]
    if routes:
        js.append("routes")
    return css, js + ["end"]


def style_block(parts=CSS_PARTS, ramps=None):
    return "<style>" + css_text(parts, ramps) + "</style>"


def script_block(parts=JS_PARTS):
    return "<script>" + js_text(parts) + "</script>" if parts else ""


def read_ref():
    """SHA of the commit whose tree holds template/dist, or None before the first release."""
    try:
        ref = (DIST / "REF").read_text().strip()
    except OSError:
        return None
    return ref or None


def cdn_url(ref, name):
    return CDN.format(ref=ref, name=name)


def asset_blocks(assets_mode, mode_name, kind, ramps=None, edges=(), routes=None, footnotes=()):
    """(before, after): what surrounds a diagram's <section>. `cdn` needs read_ref() to be set;
    render.py falls back to `inline` otherwise."""
    if assets_mode == "none":
        return "", ""
    if assets_mode == "cdn":
        ref = read_ref()
        return (f'<link rel="stylesheet" href="{esc(cdn_url(ref, "dg.css"))}">',
                f'<script src="{esc(cdn_url(ref, "dg.js"))}"></script>')
    if mode_name == "page":
        return style_block(), script_block()
    css, js = widget_parts(kind, edges, routes, footnotes)
    return style_block(css, ramps or ()), script_block(js)


def harness(fragment):
    return (TPL / "harness.html").read_text().replace("{{BODY}}", fragment)


def section_id(model):
    return model.get("id") or hashlib.sha1(json.dumps(model, sort_keys=True).encode()).hexdigest()[:8]


def section_open(model, kind, style_vars, labels_js, summary):
    uid = section_id(model)
    return (f'<section class="dg" data-dg="{esc(uid)}" data-kind="{esc(kind)}" data-labels="{labels_js}" '
            f'style="{style_vars}">\n<h2 class="sr">{esc(summary)}</h2>')


def edges_json(edges):
    return ('<script type="application/json" class="dg-edges">'
            + json.dumps(edges, ensure_ascii=False).replace("</", "<\\/") + "</script>")
