import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401
from diagrams import assets

EDGE = [{"a": "a", "b": "b"}]
CDN = "https://cdn.jsdelivr.net/gh/chelout/plugins-marketplace@{}/plugins/drawing-diagrams/skills/drawing-diagrams/template/dist/"
REGEX_AFTER = "(,=:[!&|?{};+-*%<>~^"  # a `/` after one of these (or at the start) opens a regex literal
FUNCTION = re.compile(r"function\s*([A-Za-z_$][\w$]*)?\s*\(")
# The screen-space rectangle APIs, as a set: every name holding ClientRect (getBoundingClientRect,
# getClientRects), getBoxQuads and getScreenCTM.
RECT_API = "ClientRect|getBoxQuads|getScreenCTM"
RECT = re.compile(RECT_API)
RECT_MEMBER = re.compile(r"\.[\w$]*(?:" + RECT_API + ")")


def js_comments(source):
    """(line, text) of every `//` and `/* */` comment in `source`, skipping string, template and regex
    literals, so that 'http://...' or /\\/\\// is not one."""
    found, i, n, prev = [], 0, len(source), ""
    while i < n:
        ch = source[i]
        if ch in "'\"`":
            j = i + 1
            while j < n and source[j] != ch:
                j += 2 if source[j] == "\\" else 1
            i, prev = j + 1, ch
        elif source.startswith("//", i) or source.startswith("/*", i):
            end = source.find("\n", i) if source[i + 1] == "/" else source.find("*/", i) + 2
            end = n if end < i + 2 else end
            found.append((source.count("\n", 0, i) + 1, source[i:end]))
            i = end
        elif ch == "/" and (prev == "" or prev in REGEX_AFTER):
            j, klass = i + 1, False
            while j < n and (klass or source[j] != "/") and source[j] != "\n":
                if source[j] == "\\":
                    j += 1
                elif source[j] in "[]":
                    klass = source[j] == "["
                j += 1
            i, prev = j + 1, "/"
        else:
            if not ch.isspace():
                prev = ch
            i += 1
    return found


def measurements(source):
    """(function, receiver) of every member access to a rectangle API of RECT in `source`, called or
    not: the innermost function around it, by its name or, for a function without one, by what it is
    assigned to, and the expression the access is made on. Braces inside string literals open
    nothing."""
    found, stack, pending, i, n = [], [], None, 0, len(source)
    while i < n:
        ch = source[i]
        if ch in "'\"`":
            j = i + 1
            while j < n and source[j] != ch:
                j += 2 if source[j] == "\\" else 1
            i = j + 1
            continue
        m = FUNCTION.match(source, i)
        if m and (i == 0 or not (source[i - 1].isalnum() or source[i - 1] in "_$")):
            assigned = re.search(r"([\w$.]+)\s*=\s*$", source[:i])
            pending, i = m.group(1) or (assigned.group(1) if assigned else "?"), m.end()
            continue
        if ch == "{":
            stack.append(pending)
            pending = None
        elif ch == "}":
            stack.pop()
        elif RECT_MEMBER.match(source, i):
            owner = next((name for name in reversed(stack) if name), None)
            found.append((owner, re.search(r"([\w$.]*)$", source[:i]).group(1)))
        i += 1
    return found


class ShippedSource(unittest.TestCase):
    def test_no_fragment_of_template_js_carries_a_comment(self):
        # Every fragment ships verbatim into every diagram, inline or through the CDN build.
        for path in sorted((assets.TPL / "js").glob("*.js")):
            with self.subTest(fragment=path.name):
                self.assertEqual(js_comments(path.read_text()), [])

    def test_only_draw_and_box_measure_a_rectangle(self):
        # The drawing works in the grid's own layout px: draw() measures the grid once per drawing and
        # box() takes every other rectangle back to it through that measurement. A rectangle measured
        # anywhere else is in screen px, which differ from the grid's under a scaled ancestor. The count
        # takes every occurrence of a RECT name in a fragment, inside string literals too; a name put
        # together at run time from pieces that hold none of them is beyond a static scan.
        self.assertEqual(sorted(measurements(assets.js_text())), [("box", "el"), ("draw", "grid")])
        for path in sorted((assets.TPL / "js").glob("*.js")):
            with self.subTest(fragment=path.name):
                expected = {"head.js": [("box", "el")], "draw.js": [("draw", "grid")]}.get(path.name, [])
                self.assertEqual(len(RECT.findall(path.read_text())), len(expected))

    def test_the_measurement_scanner_names_the_innermost_function(self):
        self.assertEqual(measurements("function f(a){var s='{',t=\"}\";a.getBoundingClientRect()}"),
                         [("f", "a")])
        self.assertEqual(measurements("o.k=function(){function g(){}q.r.getBoundingClientRect()}"),
                         [("o.k", "q.r")])
        self.assertEqual(measurements("function f(){if(x){g(function(){e.getBoundingClientRect()})}}"),
                         [("?", "e")])
        self.assertEqual(measurements("x.getBoundingClientRect();function h(){}"), [(None, "x")])

    def test_the_measurement_scanner_finds_every_rectangle_api(self):
        self.assertEqual(measurements("function f(a){var c=a.getClientRects()[0],q=a.b.getBoxQuads();"
                                      "g.getScreenCTM;a.getRect();a.offsetWidth;'.getClientRects()'}"),
                         [("f", "a"), ("f", "a.b"), ("f", "g")])
        self.assertEqual(len(RECT.findall("a['getBounding'+'ClientRect']();b.getBoxQuads()")), 2)

    def test_the_comment_scanner_skips_literals_and_finds_both_forms(self):
        self.assertEqual(js_comments("var a='http://x',b=\"/*\",c=`//`,d=/\\/\\//g,e=a.split(/\\s+/);"), [])
        self.assertEqual(js_comments("var r=/[/]/;x=r"), [])
        self.assertEqual(js_comments("a=1;\n b=a/2;// half\nc=/* two */2"),
                         [(2, "// half"), (3, "/* two */")])


class Fragments(unittest.TestCase):
    def test_full_build_holds_every_fragment_once(self):
        css, js = assets.css_text(), assets.js_text()
        for part in assets.CSS_PARTS:
            self.assertEqual(css.count((assets.TPL / "css" / f"{part}.css").read_text()), 1, part)
        for part in assets.JS_PARTS:
            self.assertEqual(js.count((assets.TPL / "js" / f"{part}.js").read_text()), 1, part)

    def test_widget_parts(self):
        self.assertEqual(assets.widget_parts("timeline", [], None, []), (["base", "timeline"], []))
        self.assertEqual(assets.widget_parts("blocks", [], None, [])[1], [])
        self.assertEqual(assets.widget_parts("schema", [], None, [])[1], ["head", "schema", "draw", "end"])
        self.assertEqual(assets.widget_parts("swimlane", EDGE, {"r": ["a", "b"]}, ["note"]),
                         (["base", "flow", "lanes", "routes", "foot"], ["head", "flow", "draw", "routes", "end"]))

    def test_page_inline_is_the_full_build(self):
        self.assertEqual(assets.asset_blocks("inline", "page", "flow"),
                         ("<style>" + assets.css_text() + "</style>", "<script>" + assets.js_text() + "</script>"))

    def test_widget_inline_keeps_only_what_the_diagram_uses(self):
        before, after = assets.asset_blocks("inline", "widget", "flow", {"teal"}, EDGE)
        self.assertIn(".r-teal", before)
        self.assertNotIn(".r-purple", before)
        self.assertNotIn(".dg-tl{", before)
        self.assertIn("drawKind.flow", after)
        self.assertNotIn("drawKind.schema", after)

    def test_timeline_widget_has_no_script(self):
        before, after = assets.asset_blocks("inline", "widget", "timeline")
        self.assertIn(".dg-tl{", before)
        self.assertEqual(after, "")

    def test_none_is_empty(self):
        self.assertEqual(assets.asset_blocks("none", "widget", "flow", {"teal"}, EDGE), ("", ""))

    def test_cdn_links_pin_ref(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(assets, "DIST", Path(tmp)):
            Path(tmp, "REF").write_text("a" * 40 + "\n")
            before, after = assets.asset_blocks("cdn", "widget", "flow", {"teal"}, EDGE)
        base = CDN.format("a" * 40)
        self.assertEqual(before, f'<link rel="stylesheet" href="{base}dg.css">')
        self.assertEqual(after, f'<script src="{base}dg.js"></script>')

    def test_read_ref_without_file(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(assets, "DIST", Path(tmp)):
            self.assertIsNone(assets.read_ref())

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_every_script_combination_parses(self):
        combos = {tuple(assets.JS_PARTS)}
        for kind in ("schema", "flow", "swimlane", "state", "blocks"):
            for routes in (None, {"r": ["a", "b"]}):
                parts = assets.widget_parts(kind, EDGE, routes, [])[1]
                if parts:
                    combos.add(tuple(parts))
        with tempfile.TemporaryDirectory() as tmp:
            for i, parts in enumerate(sorted(combos)):
                path = Path(tmp, f"{i}.js")
                path.write_text(assets.js_text(parts))
                subprocess.run(["node", "--check", str(path)], check=True)


if __name__ == "__main__":
    unittest.main()
