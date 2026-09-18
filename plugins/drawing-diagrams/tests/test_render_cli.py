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
# A flow whose only problem is one unbroken 66-character word in node a's text: in a four-column
# grid it is wider than the text box. Nodes a-c are steps because a terminal shows no text (that
# is a warning of its own), and d is the terminal so no node is left without an outgoing edge.
LONG_WORD = {"kind": "flow", "id": "long_word", "groups": GROUPS, "grid": ["a b c d"],
             "nodes": [{"id": "a", "kind": "step", "group": "g", "title": "A",
                        "text": "https://kyc.example.com/v2/applicants/verification_status_callback"},
                       {"id": "b", "kind": "step", "group": "g", "title": "B"},
                       {"id": "c", "kind": "step", "group": "g", "title": "C"},
                       {"id": "d", "kind": "terminal", "group": "g", "title": "D"}],
             "edges": ["a -> b", "b -> c", "c -> d"]}
LONG_WORD_MESSAGE = r"узел a: слово 66 симв\., влезает ~\d+"


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

    # Every model under examples/ renders in both modes. The models are found by walking the
    # directory, never by name, so one added later is covered without editing this test; EXAMPLES
    # above stays the population of the size budget only.
    def test_every_example_renders_in_both_modes(self):
        self.publish()
        examples = support.SKILL / "examples"
        paths = sorted(examples.rglob("*.json"))
        found = {path.stem for path in paths}
        # An empty or non-recursive walk would pass by checking nothing: it must reach at least the
        # budget's six, kyc-module under full/ among them.
        self.assertLessEqual(set(EXAMPLES), found, f"{examples}: the walk found {sorted(found)}")
        for path in paths:
            for mode in ("widget", "page"):
                where = f"{path.relative_to(support.SKILL)} --mode {mode}"
                with self.subTest(model=where):
                    code, out, err = self.run_cli(str(path), "--mode", mode)
                    self.assertEqual(code, 0, f"{where}: {err}")
                    self.assertTrue(out, f"{where}: empty output")

    # --draft turns a too-wide word, a layout error, into a warning: exit 0, the output is produced
    # and stamped as a draft. Without --draft the same model is refused with the message as its
    # only error.
    def test_draft_downgrades_a_too_wide_word_to_a_warning(self):
        self.publish()
        path = self.model(LONG_WORD)

        code, out, err = self.run_cli(path)
        self.assertEqual((code, out), (1, ""), err)
        errors = [line for line in err.splitlines() if line.startswith("ошибка:")]
        self.assertEqual(len(errors), 1, err)
        self.assertRegex(errors[0], rf"^ошибка: {LONG_WORD_MESSAGE}$")

        code, out, err = self.run_cli(path, "--draft")
        self.assertEqual(code, 0, err)
        self.assertIn('<span class="dg-draft">', out)
        self.assertNotIn("ошибка:", err)
        warnings = [line for line in err.splitlines() if line.startswith("предупреждение:")]
        self.assertEqual(len(warnings), 1, err)
        self.assertRegex(warnings[0], rf"^предупреждение: черновик: {LONG_WORD_MESSAGE}$")

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

    # finding 3: with several models, a summary line is tied to its model only by print order
    # today; carry the model path in the summary itself.
    def test_batch_summary_lines_carry_the_model_path(self):
        out_dir = self.tmp / "out"
        path1, path2 = self.model(GOOD), self.model(dict(GOOD, id="good2"))
        code, out, err = self.run_cli(path1, path2, "--out-dir", str(out_dir))
        self.assertEqual(code, 0)
        self.assertIn(f"ок: {path1}: вид flow, 2 узлов, 1 связей, 0 предупреждений", err)
        self.assertIn(f"ок: {path2}: вид flow, 2 узлов, 1 связей, 0 предупреждений", err)

    # finding 4: two models writing to the same --out-dir target (same id, or same stem without
    # an id) must not silently overwrite each other; reject before writing anything.
    def test_duplicate_out_dir_targets_are_rejected_before_writing(self):
        out_dir = self.tmp / "out"
        a, b = self.tmp / "a.json", self.tmp / "b.json"
        a.write_text(json.dumps(dict(GOOD, id="good"), ensure_ascii=False))
        b.write_text(json.dumps(dict(GOOD, id="good"), ensure_ascii=False))
        code, out, err = self.run_cli(str(a), str(b), "--out-dir", str(out_dir))
        self.assertEqual((code, out), (1, ""))
        self.assertFalse(out_dir.exists())
        self.assertIn(str(a), err)
        self.assertIn(str(b), err)
        self.assertIn("good.html", err)

    # finding 1 (branch-gate round 1, P1): an `id` used verbatim as a file name lets a model
    # escape --out-dir (absolute id, id with "..", id with "/"), and lexically different names
    # that resolve to the same file bypass the literal-name duplicate check. Every case must fail
    # the batch before anything is written: no file at the escape target, out_dir not created.

    def write_model(self, name, data):
        """Write `data` to `<tmp>/<name>.json` directly, bypassing self.model()'s `<id>.json`
        naming — needed when `id` itself is not a safe file name (contains '/', '..', or is
        absolute)."""
        path = self.tmp / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False))
        return str(path)

    def test_out_dir_rejects_absolute_id(self):
        out_dir = self.tmp / "out"
        escaped = self.tmp / "escaped"
        model_path = self.write_model("evil1", dict(GOOD, id=str(escaped)))
        code, out, err = self.run_cli(model_path, "--out-dir", str(out_dir))
        self.assertEqual((code, out), (1, ""))
        self.assertFalse(out_dir.exists())
        self.assertFalse(escaped.with_suffix(".html").exists())
        self.assertIn(model_path, err)

    def test_out_dir_rejects_id_with_dotdot(self):
        out_dir = self.tmp / "out"
        model_path = self.write_model("evil2", dict(GOOD, id="../victim"))
        code, out, err = self.run_cli(model_path, "--out-dir", str(out_dir))
        self.assertEqual((code, out), (1, ""))
        self.assertFalse(out_dir.exists())
        self.assertFalse((self.tmp / "victim.html").exists())
        self.assertIn(model_path, err)

    def test_out_dir_rejects_id_with_slash(self):
        out_dir = self.tmp / "out"
        model_path = self.write_model("evil3", dict(GOOD, id="nested/evil"))
        code, out, err = self.run_cli(model_path, "--out-dir", str(out_dir))
        self.assertEqual((code, out), (1, ""))
        self.assertFalse(out_dir.exists())
        self.assertIn(model_path, err)

    # finding P1 (branch-gate round 5): a non-string `id` must not crash the batch (JSON number,
    # bool, list, object) nor silently fall back to the file stem (falsy-but-not-null: "", 0,
    # [], {}). Only an absent key or an explicit `null` may fall back; every other non-conforming
    # value fails the whole batch before anything is written, with the existing --out-dir id
    # error and no traceback.
    def test_out_dir_rejects_non_string_ids(self):
        bad_ids = (123, True, 0, "", [], {}, ["a"])
        for i, bad_id in enumerate(bad_ids):
            with self.subTest(bad_id=bad_id):
                out_dir = self.tmp / f"out_bad_{i}"
                good_path = self.write_model(f"good_{i}", dict(GOOD, id=f"good_{i}"))
                bad_path = self.write_model(f"bad_{i}", {**GOOD, "id": bad_id})
                code, out, err = self.run_cli(good_path, bad_path, "--out-dir", str(out_dir))
                self.assertEqual((code, out), (1, ""))
                self.assertFalse(out_dir.exists())
                self.assertIn("--out-dir", err)
                self.assertIn(bad_path, err)
                self.assertNotIn("Traceback", err)

    def test_out_dir_null_id_falls_back_to_file_stem(self):
        out_dir = self.tmp / "out"
        model_path = self.write_model("stem_name", {**GOOD, "id": None})
        code, out, err = self.run_cli(model_path, "--out-dir", str(out_dir))
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(p.name for p in out_dir.iterdir()), ["stem_name.html"])

    def test_out_dir_rejects_targets_colliding_after_resolution(self):
        # One model names its target via an explicit id, the other via the file-stem fallback;
        # both resolve to "dup.html". A literal-name comparison of "dup" (id) vs the fallback
        # stem still matches here, but must go through the same resolved-path dedup as every
        # other --out-dir collision — nothing gets written for either.
        out_dir = self.tmp / "out"
        explicit = self.write_model("explicit", dict(GOOD, id="dup"))
        no_id = {k: v for k, v in GOOD.items() if k != "id"}
        implicit = self.write_model("dup", no_id)
        code, out, err = self.run_cli(explicit, implicit, "--out-dir", str(out_dir))
        self.assertEqual((code, out), (1, ""))
        self.assertFalse(out_dir.exists())
        self.assertIn(explicit, err)
        self.assertIn(implicit, err)
        self.assertIn("dup.html", err)


if __name__ == "__main__":
    unittest.main()
