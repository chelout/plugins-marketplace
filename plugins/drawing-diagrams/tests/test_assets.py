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
