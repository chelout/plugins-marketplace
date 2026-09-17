"""CSS, JS and page wrappers shared by every kind."""
import hashlib
import json
from pathlib import Path

from .common import RAMPS, esc

TPL = Path(__file__).resolve().parent.parent / "template"


def ramp_css(ramps):
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


def style_block(ramps=None):
    """All nine ramps are emitted regardless of `ramps`: a second diagram on the
    same page (rendered with --no-assets) may use colours the first did not."""
    css = (TPL / "tokens.css").read_text() + (TPL / "core.css").read_text() + ramp_css(RAMPS)
    return "<style>" + css + "</style>"


def script_block():
    return "<script>" + (TPL / "core.js").read_text() + "</script>"


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
