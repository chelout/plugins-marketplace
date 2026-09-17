import io
import json
import statistics
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import support
import render
from diagrams import assets

REF = "c" * 40
GROUPS = {"g": {"label": "g", "ramp": "teal"}}
GOOD = {"kind": "flow", "id": "good", "groups": GROUPS,
        "nodes": [{"id": "a", "kind": "terminal", "group": "g", "title": "Старт"},
                  {"id": "b", "kind": "terminal", "group": "g", "title": "Финиш"}],
        "grid": ["a", "b"], "edges": ["a -> b"]}
LONG_TITLE = {"kind": "flow", "id": "bad", "groups": GROUPS, "grid": ["a b c d"], "edges": [],
              "nodes": [{"id": n, "kind": "terminal", "title": "Очень длинный заголовок узла" if n == "a" else n.upper()}
                        for n in "abcd"]}
WIDE = {"kind": "flow", "id": "wide", "groups": GROUPS, "grid": ["a b c d e"],
        "nodes": [{"id": n, "kind": "terminal", "title": n.upper()} for n in "abcde"],
        "edges": ["a -> b", "b -> c", "c -> d", "d -> e"]}
# G6: a grid-width layout error together with an ordinary validation error (duplicate node id),
# so the draft re-plan `failure_map` attempts also raises. See gate.md row G6.
WIDE_DUP = {**WIDE, "id": "wide_dup",
            "nodes": WIDE["nodes"] + [{"id": "a", "kind": "terminal", "title": "A2"}]}
EXAMPLES = ("kyc-module", "resolver-rules", "kyc-trace", "verdict-row-lifecycle", "four-blocks", "mark-timeline")


class RenderCli(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.dist = self.tmp / "dist"
        self.dist.mkdir()
        patcher = mock.patch.object(assets, "DIST", self.dist)
        patcher.start()
        self.addCleanup(patcher.stop)

    def model(self, data):
        path = self.tmp / f"{data['id']}.json"
        path.write_text(json.dumps(data, ensure_ascii=False))
        return str(path)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = render.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def publish(self):
        (self.dist / "REF").write_text(REF + "\n")

    def test_widget_defaults_to_cdn_links(self):
        self.publish()
        code, out, _ = self.run_cli(self.model(GOOD))
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith('<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/chelout/'
                                       f'plugins-marketplace@{REF}/'), out[:160])
        self.assertTrue(out.endswith('/template/dist/dg.js"></script>'), out[-160:])
        self.assertNotIn("<style>", out)

    def test_cdn_without_ref_falls_back_to_inline(self):
        code, out, err = self.run_cli(self.model(GOOD))
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("<style>"))
        self.assertIn("нет template/dist/REF", err)

    def test_no_assets_is_assets_none(self):
        self.publish()
        path = self.model(GOOD)
        alias, none = self.run_cli(path, "--no-assets")[1], self.run_cli(path, "--assets", "none")[1]
        self.assertEqual(alias, none)
        self.assertNotIn("<style>", none)
        self.assertNotIn("<link", none)

    def test_page_defaults_to_the_full_inline_build(self):
        self.publish()
        code, out, _ = self.run_cli(self.model(GOOD), "--mode", "page")
        self.assertEqual(code, 0)
        self.assertIn(".dg-tl{", out)
        self.assertIn("drawKind.schema", out)

    def test_text_fit_failure_has_empty_stdout_and_no_map(self):
        code, out, err = self.run_cli(self.model(LONG_TITLE))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("заголовок", err)
        self.assertNotIn("пересечений линий", err)

    def test_layout_failure_prints_the_map(self):
        code, out, err = self.run_cli(self.model(WIDE))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("grid шириной 5", err)
        self.assertIn("пересечений линий", err)

    def test_several_models_need_out_dir(self):
        code, out, err = self.run_cli(self.model(GOOD), self.model(dict(GOOD, id="good2")))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("--out-dir", err)

    def test_batch_writes_every_model(self):
        out_dir = self.tmp / "out"
        code, out, _ = self.run_cli(self.model(GOOD), self.model(dict(GOOD, id="good2")), "--out-dir", str(out_dir))
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p.name for p in out_dir.iterdir()), ["good.html", "good2.html"])
        self.assertEqual(len(out.strip().splitlines()), 2)

    def test_batch_with_failures_writes_nothing_and_reports_all(self):
        out_dir = self.tmp / "out"
        bad1, bad2 = self.model(LONG_TITLE), self.model(WIDE)
        code, out, err = self.run_cli(self.model(GOOD), bad1, bad2, "--out-dir", str(out_dir))
        self.assertEqual((code, out), (1, ""))
        self.assertFalse(out_dir.exists())
        self.assertIn(bad1, err)
        self.assertIn(bad2, err)

    def test_cdn_fragments_of_the_examples(self):
        self.publish()
        sizes = []
        for name in EXAMPLES:
            path = next(support.SKILL.joinpath("examples").rglob(f"{name}.json"))
            code, out, err = self.run_cli(str(path))
            self.assertEqual(code, 0, err)
            sizes.append(len(out))
        print(f"\ncdn widget fragments of the examples: {dict(zip(EXAMPLES, sizes))}, median {statistics.median(sizes)}")
        self.assertLessEqual(statistics.median(sizes), 6000, sizes)

    # --- G4 (gate.md): every successful render that is not --check prints one summary line to
    # stderr in the --check shape; stdout stays exactly the rendered fragment.
    def test_successful_render_prints_check_shaped_summary_to_stderr(self):
        self.publish()
        code, out, err = self.run_cli(self.model(GOOD))
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith('<link rel="stylesheet"'))
        self.assertNotIn("ок:", out)
        self.assertIn("ок: вид flow, 2 узлов, 1 связей, 0 предупреждений", err)

    # --- G6 (gate.md): when the draft re-plan inside `failure_map` raises too (here: a grid-width
    # error alongside a duplicated node id), fall back to the grid map for every kind that has a grid.
    def test_grid_map_used_when_draft_replan_also_fails(self):
        code, out, err = self.run_cli(self.model(WIDE_DUP))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("grid шириной 5", err)
        self.assertIn("a  b  c  d  e", err)


if __name__ == "__main__":
    unittest.main()
