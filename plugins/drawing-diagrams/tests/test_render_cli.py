import copy
import io
import json
import re
import statistics
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import support
import render
from diagrams import advice, assets, flow

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
MODELS = Path(__file__).resolve().parent / "models"
# A swimlane whose first two lanes have four lines in the gutter between them and room for three.
OVERFULL = MODELS / "overfull-gutter.json"
OVERFULL_MESSAGE = r"между столбцами \d+ и \d+ линий \d+, помещается \d+: "

# --- the advice of spec 6, printed on stderr by `render.main`
#
# A flow whose grid crosses three lines — the count `flow.plan` warns at, which is what asks for
# the advice — and which the search improves in two moves, so the block carries a numbered list and
# not a single line. Its ids are the ones spec 6's own example moves.
CROSSED_TITLES = {"start": "Заявка", "check": "Проверка", "wait": "Ожидание", "retry": "Повтор",
                  "declined": "Отказ", "done": "Архив"}
CROSSED = {"kind": "flow", "id": "crossed", "groups": GROUPS,
           "nodes": [{"id": nid, "group": "g", "title": title,
                      "kind": "terminal" if nid in ("start", "done") else "step"}
                     for nid, title in CROSSED_TITLES.items()],
           "grid": ["start  .         .",
                    "check  wait      retry",
                    "done   declined  ."],
           "edges": ["start -> check", "start -> wait", "start -> declined",
                     "check -> retry", "check -> declined", "wait -> declined",
                     "retry -> done", "declined -> done"]}
CROSSED_CROSSINGS = 3
# One column, every card joined downward to cards below it: a swap would turn one of those edges
# upward, which the rules of the advice forbid, and there is no empty cell to carry a card into. So
# the model crosses three times, the warning is printed — and the search has nothing to offer.
NO_MOVE = {"kind": "flow", "id": "no_move", "groups": GROUPS,
           "nodes": [{"id": nid, "group": "g", "title": nid.upper(),
                      "kind": "terminal" if nid == "f" else "step"} for nid in "abcdef"],
           "grid": list("abcdef"),
           "edges": ["a -> b", "b -> c", "c -> d", "d -> e", "e -> f",
                     "a -> c", "a -> d", "b -> d", "b -> f", "c -> f"]}
# An example the search does find a move on and the renderer must still say nothing about: its plan
# crosses nothing, so nothing was asked of it. `test_a_model_without_the_trigger_is_not_advised`
# asserts that premise rather than assuming it.
QUIET = support.SKILL / "examples" / "kyc-trace.json"
HEADLINE = re.compile(r"^совет: (?P<prefix>.*?)(?P<term>пересечений|лишних линий|длина линий) "
                      r"(?P<before>\d+) → (?P<after>\d+) за (?P<moves>\d+) ход(?:а|ов)? "
                      r"\(проверено трассировкой\)$")
STEP = re.compile(r"^  (?P<n>\d+)\. (?P<what>.+): (?P<before>\d+) → (?P<after>\d+)$")


def advice_blocks(err):
    """Every advice block in a stderr, each as its list of lines: the headline, the numbered moves,
    `grid:` and the rows under it. The first line that is neither indented nor `grid:` ends one."""
    blocks, block = [], None
    for line in err.splitlines():
        if line.startswith("совет:"):
            block = [line]
            blocks.append(block)
        elif block is not None and (line == "grid:" or line.startswith("  ")):
            block.append(line)
        else:
            block = None
    return blocks


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
        # nor an advice: such a model is never planned again, so nothing says what its gutters and
        # its crossings would be — and what it needs is a shorter text, not a rearrangement
        self.assertEqual(advice_blocks(err), [])

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

    # A gutter holding more lines than fit is a layout error like the ones above: stdout stays
    # empty, the message names the gutter, the edges in it and what to do, the map is printed
    # because the failure is of the layout and not of a length, and --draft downgrades it.
    def test_a_gutter_over_its_capacity_is_refused_with_the_map(self):
        code, out, err = self.run_cli(str(OVERFULL))
        self.assertEqual((code, out), (1, ""), err)
        errors = [line for line in err.splitlines() if line.startswith("ошибка:")]
        self.assertEqual(len(errors), 1, err)
        self.assertRegex(errors[0], rf"^ошибка: {OVERFULL_MESSAGE}")
        self.assertIn("освободите ячейку рядом или переставьте узлы", errors[0])
        self.assertIn("[zayavka]", err)  # the ASCII map of the model, not just the message

    def test_draft_downgrades_a_full_gutter_to_a_warning(self):
        self.publish()
        code, out, err = self.run_cli(str(OVERFULL), "--draft")
        self.assertEqual(code, 0, err)
        self.assertIn('<span class="dg-draft">', out)
        self.assertNotIn("ошибка:", err)
        drafts = [line for line in err.splitlines() if line.startswith("предупреждение: черновик:")]
        self.assertEqual(len(drafts), 1, err)
        self.assertRegex(drafts[0], rf"^предупреждение: черновик: {OVERFULL_MESSAGE}")

    def test_the_stress_models_render_in_their_mode(self):
        # the two models the owner reviews the line pitch on: they are only useful while they
        # render, and tests/test_capacity.py holds them to the pitches they were picked for
        self.publish()
        for name, mode in (("dense-widget-flow", "widget"), ("dense-page-swimlane", "page")):
            with self.subTest(model=name):
                code, out, err = self.run_cli(str(MODELS / f"{name}.json"), "--mode", mode)
                self.assertEqual(code, 0, err)
                self.assertTrue(out, f"{name}: empty output")

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

    # --- spec 6, criterion D3: the rearrangement advice on stderr, `--no-advice`, and what the
    # trigger is. The renderer asks for advice where it has already told the author something — a
    # group over capacity or three crossings — and never otherwise: the last term of the score is
    # the length of the lines, so a search finds a shorter routing on almost any model, and an
    # advice nobody asked for is noise in every render.
    def read_block(self, err, prefix=""):
        """The one advice block of a stderr, checked against the form of spec 6 and returned as
        (the headline's match, the numbered moves' matches, the rows of the advised grid)."""
        blocks = advice_blocks(err)
        self.assertEqual(len(blocks), 1, err)
        head = HEADLINE.match(blocks[0][0])
        self.assertIsNotNone(head, blocks[0][0])
        self.assertEqual(head["prefix"], prefix, blocks[0][0])
        self.assertIn("grid:", blocks[0], blocks[0])
        cut = blocks[0].index("grid:")
        steps = [STEP.match(line) for line in blocks[0][1:cut]]
        self.assertTrue(all(steps), blocks[0][1:cut])
        # the numbers of the block are one chain: the headline's own two ends are the first move's
        # start and the last move's end, and every move starts where the one before it ended
        self.assertEqual([step["n"] for step in steps],
                         [str(i) for i in range(1, len(steps) + 1)], blocks[0])
        self.assertEqual(head["moves"], str(len(steps)), blocks[0])
        self.assertEqual([head["before"]] + [step["after"] for step in steps],
                         [step["before"] for step in steps] + [head["after"]], blocks[0])
        rows = [json.loads(line.strip()) for line in blocks[0][cut + 1:]]
        self.assertTrue(rows, blocks[0])
        return head, steps, rows

    def test_three_crossings_get_the_advice_after_the_warning(self):
        self.publish()
        path = self.model(CROSSED)
        code, out, err = self.run_cli(path)
        self.assertEqual(code, 0, err)
        # stdout is the fragment and nothing else: the advice is stderr's
        self.assertEqual(out, self.run_cli(path, "--no-advice")[1])
        self.assertNotIn("совет", out)
        warning = f"предупреждение: пересечений линий: {CROSSED_CROSSINGS}"
        self.assertIn(warning, err)
        head, steps, rows = self.read_block(err)
        self.assertEqual((head["term"], head["before"]), ("пересечений", str(CROSSED_CROSSINGS)), err)
        self.assertLess(int(head["after"]), CROSSED_CROSSINGS, err)
        self.assertEqual(len(steps), 2, err)
        # the block comes after the warning it answers and after the map printed with it
        self.assertLess(err.index(warning), err.index(head.group(0)), err)
        self.assertLess(err.index("[start]"), err.index(head.group(0)), err)
        # and the grid it prints is the advice itself: planned as it stands, it crosses what the
        # headline promises
        advised = dict(copy.deepcopy(CROSSED), grid=rows)
        layout, _ = flow.plan(advised, "widget", {}, draft=True)
        self.assertEqual(layout["crossings"], int(head["after"]), rows)

    def test_no_advice_prints_none(self):
        self.publish()
        code, out, err = self.run_cli(self.model(CROSSED), "--no-advice")
        self.assertEqual(code, 0, err)
        self.assertIn(f"предупреждение: пересечений линий: {CROSSED_CROSSINGS}", err)
        self.assertEqual(advice_blocks(err), [])

    def test_a_model_no_move_improves_prints_none(self):
        self.publish()
        code, out, err = self.run_cli(self.model(NO_MOVE))
        self.assertEqual(code, 0, err)
        self.assertIn("предупреждение: пересечений линий: 3", err)
        self.assertEqual(advice.search(copy.deepcopy(NO_MOVE), "widget", {}), [])
        self.assertEqual(advice_blocks(err), [])

    def test_a_model_without_the_trigger_is_not_advised(self):
        self.publish()
        # the premise: this example is offered a move, and is still said nothing about
        self.assertTrue(advice.search(json.loads(QUIET.read_text()), "widget", {}))
        code, out, err = self.run_cli(str(QUIET))
        self.assertEqual(code, 0, err)
        self.assertNotIn("пересечений линий", err)
        self.assertEqual(advice_blocks(err), [])

    def test_the_advice_names_its_model_in_a_batch(self):
        self.publish()
        out_dir = self.tmp / "out"
        crossed, good = self.model(CROSSED), self.model(GOOD)
        code, out, err = self.run_cli(crossed, good, "--out-dir", str(out_dir))
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(p.name for p in out_dir.iterdir()), ["crossed.html", "good.html"])
        self.read_block(err, prefix=f"{crossed}: ")

    def test_the_advice_keeps_the_all_or_nothing_of_out_dir(self):
        out_dir = self.tmp / "out"
        crossed, bad = self.model(CROSSED), self.model(WIDE)
        code, out, err = self.run_cli(crossed, bad, "--out-dir", str(out_dir))
        self.assertEqual((code, out), (1, ""), err)
        self.assertFalse(out_dir.exists())
        self.read_block(err, prefix=f"{crossed}: ")

    def test_an_error_run_prints_the_advice_once_after_the_map(self):
        code, out, err = self.run_cli(str(OVERFULL))
        self.assertEqual((code, out), (1, ""), err)
        head, steps, rows = self.read_block(err)
        # the trigger here is the group over its capacity, and that is what the headline counts
        self.assertEqual(head["term"], "лишних линий", err)
        self.assertEqual(head["after"], "0", err)
        self.assertLess(err.index("ошибка: "), err.index(head.group(0)), err)
        self.assertLess(err.index("[zayavka]"), err.index(head.group(0)), err)  # the map

    def test_check_and_the_text_formats_keep_their_stdout(self):
        self.publish()
        path = self.model(CROSSED)
        for argv in (("--check",), ("--format", "mermaid"), ("--format", "ascii")):
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(path, *argv)
                self.assertEqual(code, 0, err)
                self.assertEqual(out, self.run_cli(path, *argv, "--no-advice")[1])
                self.read_block(err)

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
