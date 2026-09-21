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
from bench_routing import ADVICE_MODE, seeded_models
from diagrams import advice, assets, flow
from diagrams.grid import parse_grid

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
# the advice. Its ids are the ones spec 6's own example moves. One swap clears all three: the two
# cards it exchanges end up in one row, which spec 6's downward rule allows.
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
# A shipped example the renderer must say nothing about: its plan crosses nothing, so nothing was
# asked of it.
QUIET = support.SKILL / "examples" / "kyc-trace.json"
# A flow that crosses exactly twice — one under the threshold — and that the search does improve.
# It is the lower edge of the trigger: nothing is printed although there is something to say.
TWICE_NODES = (("zapros", "Запрос", "step"), ("proverka", "Проверка", "step"),
               ("kesh", "Кэш", "step"), ("reshenie", "Решение", "step"),
               ("povtor", "Повтор", "step"), ("otvet", "Ответ", "step"),
               ("log", "Журнал", "terminal"), ("arhiv", "Архив", "terminal"))
TWICE = {"kind": "flow", "id": "twice", "groups": GROUPS,
         "nodes": [{"id": nid, "title": title, "kind": kind, "group": "g"}
                   for nid, title, kind in TWICE_NODES],
         "grid": ["zapros  proverka  .    kesh",
                  ".       reshenie  .    .",
                  "povtor  otvet     log  .",
                  ".       arhiv     .    ."],
         "edges": ["reshenie -> otvet", "zapros -> proverka", "povtor -> arhiv",
                   "kesh -> povtor", "proverka -> otvet", "otvet -> log",
                   "reshenie -> povtor", "zapros -> arhiv", "kesh -> reshenie"]}
TWICE_CROSSINGS = 2
# The model the byte form of an advised grid is read on: it crosses three times, two moves clear
# them, and the two moves change different rows. Its columns are wider than their longest token, and
# the first move carries `zayavka` into a column too narrow for it — so a map written per move would
# push the second move's row one column to the right, and a map written once at the end does not.
OFFSETS_TITLES = {"zayavka": "Заявка", "bot": "Бот", "dub": "Дубль", "otvet": "Ответ",
                  "otkaz": "Отказ", "log": "Журнал", "arhiv": "Архив"}
OFFSETS_TERMINALS = ("otvet", "otkaz", "arhiv")
OFFSETS = {"kind": "flow", "id": "offsets", "groups": GROUPS,
           "nodes": [{"id": nid, "group": "g", "title": title,
                      "kind": "terminal" if nid in OFFSETS_TERMINALS else "step"}
                     for nid, title in OFFSETS_TITLES.items()],
           "grid": ["zayavka  bot  .",
                    ".        dub  otvet",
                    "otkaz    log  arhiv"],
           "edges": ["zayavka -> dub", "bot -> otkaz", "bot -> otvet", "dub -> otkaz",
                     "log -> arhiv", "dub -> arhiv", "bot -> log", "dub -> otvet"]}
# The model the render's own overrides are read on (the plan gate's finding G2). It crosses three
# times, and a width moves neither that count nor the capacity of a line: both are read off the
# lattice, which the grid alone builds. What a width does move is the room a label has, and here the
# two widths part company over one. At the default 680 one swap clears all three crossings; at
# NARROW_WIDTH the cards are narrow enough that the very same swap leaves 'нет данных' nowhere to
# stand beside the line it labels — a message the author's own grid does not carry — so the search
# refuses it there and reaches zero by two other swaps.
NARROW_WIDTH = 440
NARROW_TITLES = {"arhiv": "Архив", "zayavka": "Заявка", "zvonok": "Звонок", "otkaz": "Отказ",
                 "otvet": "Ответ", "oplata": "Оплата", "anketa": "Анкета",
                 "proverka": "Проверка", "reshenie": "Решение"}
NARROW_STEPS = ("zayavka", "zvonok", "anketa", "proverka", "reshenie")
NARROW = {"kind": "flow", "id": "narrow", "groups": GROUPS,
          "nodes": [{"id": nid, "group": "g", "title": title,
                     "kind": "step" if nid in NARROW_STEPS else "terminal"}
                    for nid, title in NARROW_TITLES.items()],
          "grid": ["arhiv   zayavka   zvonok",
                   "otkaz   otvet     oplata",
                   "anketa  proverka  reshenie"],
          "edges": ["zayavka -> oplata", "zayavka -> anketa : нет данных", "zvonok -> otvet",
                    "anketa -> proverka", "proverka -> arhiv", "proverka -> reshenie",
                    "reshenie -> arhiv", "reshenie -> otkaz"]}
HEADLINE = re.compile(r"^совет: (?P<prefix>.*?)(?P<term>пересечений|лишних линий|длина линий) "
                      r"(?P<before>\d+) → (?P<after>\d+) за (?P<moves>\d+) ход(?:а|ов)? "
                      r"\(проверено трассировкой\)$")
# every step names the term of the score it moved, so no step of a block ever prints a count that
# stands still (spec 6 as amended)
STEP = re.compile(r"^  (?P<n>\d+)\. (?P<what>.+): (?P<term>пересечений|лишних линий|длина линий) "
                  r"(?P<before>\d+) → (?P<after>\d+)$")


def advice_blocks(err):
    """Every advice block in a stderr, each as its list of lines: the headline, the numbered moves,
    `grid:` and the rows under it, and `lanes:` with the lane order where a move changed it. The
    first line that is neither indented nor one of those two headings ends one."""
    blocks, block = [], None
    for line in err.splitlines():
        if line.startswith("совет:"):
            block = [line]
            blocks.append(block)
        elif block is not None and (line in ("grid:", "lanes:") or line.startswith("  ")):
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
        (the headline's match, the numbered moves' matches, the rows of the advised grid, the lane
        order under `lanes:` or None)."""
        blocks = advice_blocks(err)
        self.assertEqual(len(blocks), 1, err)
        head = HEADLINE.match(blocks[0][0])
        self.assertIsNotNone(head, blocks[0][0])
        self.assertEqual(head["prefix"], prefix, blocks[0][0])
        self.assertIn("grid:", blocks[0], blocks[0])
        cut = blocks[0].index("grid:")
        steps = [STEP.match(line) for line in blocks[0][1:cut]]
        self.assertTrue(all(steps), blocks[0][1:cut])
        self.assertEqual([step["n"] for step in steps],
                         [str(i) for i in range(1, len(steps) + 1)], blocks[0])
        self.assertEqual(head["moves"], str(len(steps)), blocks[0])
        # every step names the term it moved and the two numbers of that term differ: a step that
        # stood still is a step the author is asked for nothing by
        for step in steps:
            self.assertNotEqual(step["before"], step["after"], step.group(0))
        # the steps that carry the headline's own term are one chain, from its first number to its
        # last; a step that moved another term names that one and stands outside the chain
        chain = [step for step in steps if step["term"] == head["term"]]
        self.assertTrue(chain, blocks[0])
        self.assertEqual([head["before"]] + [step["after"] for step in chain],
                         [step["before"] for step in chain] + [head["after"]], blocks[0])
        tail = blocks[0][cut + 1:]
        lanes = None
        if "lanes:" in tail:
            at = tail.index("lanes:")
            lanes = json.loads(tail[at + 1].strip())
            tail = tail[:at]
        rows = [json.loads(line.strip()) for line in tail]
        self.assertTrue(rows, blocks[0])
        return head, steps, rows, lanes

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
        head, steps, rows, lanes = self.read_block(err)
        self.assertEqual((head["term"], head["before"]), ("пересечений", str(CROSSED_CROSSINGS)), err)
        self.assertLess(int(head["after"]), CROSSED_CROSSINGS, err)
        self.assertEqual(len(steps), 1, err)
        self.assertIsNone(lanes, "a flow has no lanes to print")
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
        code, out, err = self.run_cli(str(QUIET))
        self.assertEqual(code, 0, err)
        self.assertNotIn("пересечений линий", err)
        self.assertEqual(advice_blocks(err), [])

    # The lower edge of the crossings threshold, with a live premise under it: this model is offered
    # a move and is still said nothing about, because two crossings are one under the count the
    # warning is printed at. A threshold of two would advise it.
    def test_a_model_one_crossing_under_the_threshold_is_not_advised(self):
        self.publish()
        path = self.model(TWICE)
        layout, warnings = flow.plan(copy.deepcopy(TWICE), "widget", {}, draft=True)
        self.assertEqual((0, TWICE_CROSSINGS), (layout["overflow"], layout["crossings"]))
        self.assertEqual(TWICE_CROSSINGS, render.MANY_CROSSINGS - 1)
        found = advice.search(copy.deepcopy(TWICE), "widget", {})
        self.assertTrue(found, "harness: the search no longer improves this model")
        self.assertLess(found[-1][2][1], TWICE_CROSSINGS)
        code, out, err = self.run_cli(path)
        self.assertEqual(code, 0, err)
        self.assertEqual(advice_blocks(err), [])

    # The other half of the trigger, alone: a group drawn past the capacity of its line, with the
    # crossings under the threshold. `overfull-gutter.json` answers both at once, so it cannot tell
    # a trigger that reads the capacity from one that only counts crossings; the same model without
    # the two edges that make it cross three times can.
    def quiet_overfull(self):
        model = json.loads(OVERFULL.read_text())
        model["id"] = "overfull_quiet"
        model["edges"] = [e for e in model["edges"]
                          if e not in ("zayavka -> robot", "utochnenie -> peredano")]
        return model

    def test_a_group_over_its_capacity_is_advised_with_the_crossings_under_the_threshold(self):
        model = self.quiet_overfull()
        layout, _ = flow.plan(copy.deepcopy(model), "widget", {}, draft=True)
        self.assertGreater(layout["overflow"], 0)
        self.assertLess(layout["crossings"], render.MANY_CROSSINGS)
        code, out, err = self.run_cli(self.model(model))
        self.assertEqual((code, out), (1, ""), err)
        head, steps, rows, lanes = self.read_block(err)
        self.assertEqual((head["term"], head["after"]), ("лишних линий", "0"), err)

    # P2: a `lanes` move changes `lanes` and `grid` together, so the block prints both. Pasted
    # without the lane order, the grid alone hands the cards of one lane to the lane beside it —
    # and nothing says so, because here a lane is what colours a card and no node names a group of
    # its own.
    def lanes_of(self, grid, lanes):
        """The lane each card stands in: its column's, which is the whole of what a lane order
        changes."""
        cells = parse_grid(grid, [])[0]
        return {nid: lanes[c] for nid, (_, c) in cells.items()}

    def test_a_lane_order_is_printed_with_its_lanes(self):
        model = self.quiet_overfull()
        code, out, err = self.run_cli(self.model(model))
        self.assertEqual((code, out), (1, ""), err)
        head, steps, rows, lanes = self.read_block(err)
        self.assertEqual(len(model["lanes"]), len(lanes))
        self.assertNotEqual(model["lanes"], lanes, "harness: no move changed the lane order")
        pasted = dict(copy.deepcopy(model), grid=rows, lanes=lanes)
        layout, warnings = flow.plan(pasted, "widget", {}, draft=True)
        self.assertEqual(layout["overflow"], int(head["after"]), rows)
        self.assertEqual([], [w for w in warnings if "дорожк" in w or "группа" in w], warnings)
        # every card keeps the lane the author gave it, which is what the two printed together mean
        was = self.lanes_of(model["grid"], model["lanes"])
        self.assertEqual(was, self.lanes_of(rows, lanes))
        # and the premise: the grid pasted without them moves cards to other lanes, silently
        self.assertNotEqual(was, self.lanes_of(rows, model["lanes"]))

    def test_the_advice_names_its_model_in_a_batch(self):
        self.publish()
        out_dir = self.tmp / "out"
        crossed, good = self.model(CROSSED), self.model(GOOD)
        code, out, err = self.run_cli(crossed, good, "--out-dir", str(out_dir))
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(p.name for p in out_dir.iterdir()), ["crossed.html", "good.html"])
        self.read_block(err, prefix=f"{crossed}: ")

    # the model the block names is the one the block is about, and not whichever model the batch
    # was given first
    def test_the_advice_names_its_own_model_when_it_is_not_the_first(self):
        self.publish()
        out_dir = self.tmp / "out"
        good, crossed = self.model(GOOD), self.model(CROSSED)
        code, out, err = self.run_cli(good, crossed, "--out-dir", str(out_dir))
        self.assertEqual(code, 0, err)
        self.read_block(err, prefix=f"{crossed}: ")
        self.assertNotIn(f"совет: {good}", err)

    def test_no_advice_holds_across_a_batch(self):
        self.publish()
        out_dir = self.tmp / "out"
        crossed, good = self.model(CROSSED), self.model(GOOD)
        code, out, err = self.run_cli(crossed, good, "--out-dir", str(out_dir), "--no-advice")
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(p.name for p in out_dir.iterdir()), ["crossed.html", "good.html"])
        self.assertIn(f"предупреждение: пересечений линий: {CROSSED_CROSSINGS}", err)
        self.assertEqual(advice_blocks(err), [])

    # The advised grid is written once, from the placement the moves leave behind, at the column
    # offsets the author's own map used — not once per move from the map the move before it wrote.
    # On this model the two differ: the first move carries a card into a column too narrow for it,
    # and a per-move map would carry that column's new offset into the row the second move rewrites.
    def test_the_advised_grid_after_several_moves_keeps_the_authors_offsets(self):
        self.publish()
        code, out, err = self.run_cli(self.model(OFFSETS))
        self.assertEqual(code, 0, err)
        head, steps, rows, lanes = self.read_block(err)
        self.assertEqual(len(steps), 2, err)
        self.assertEqual(['bot      zayavka .',
                          '.        otvet dub',
                          'otkaz    log  arhiv'], rows)
        # and the same placement written per move, which is what the rows above must not be
        stepped = copy.deepcopy(OFFSETS)
        for move, _, _ in advice.search(copy.deepcopy(OFFSETS), "widget", {}):
            stepped = move.apply(stepped)
        self.assertNotEqual(stepped["grid"], rows,
                            "harness: on this model the two ways of writing the map agree")

    # The plan gate's finding G2: every verifying plan of the search is made in the geometry of the
    # render, so the overrides `render.main` was given — `--width` here — travel with it. A label
    # that fits at 680 px need not fit at 440, and a search that checked another geometry would
    # offer a move whose picture this render will not draw.
    def advice_lines(self, model, found):
        """The block `advise` prints for a search result, built the way it builds it."""
        return render.advice_block(found, render.advised_grid(model, found),
                                   render.advised_lanes(found), "")

    def test_the_advice_is_searched_at_the_width_the_render_was_given(self):
        self.publish()
        overrides = {"total": NARROW_WIDTH}
        wide = advice.search(copy.deepcopy(NARROW), "widget", {})
        thin = advice.search(copy.deepcopy(NARROW), "widget", overrides)
        self.assertTrue(wide and thin, "harness: the search no longer improves this model")
        path = self.model(NARROW)
        code, out, err = self.run_cli(path)
        self.assertEqual(code, 0, err)
        code, out, narrow = self.run_cli(path, "--width", str(NARROW_WIDTH))
        self.assertEqual(code, 0, narrow)
        # the trigger is the same at both widths: the crossings are read off the lattice, which a
        # width does not move, so what parts the two blocks is the geometry the moves were verified
        # in and nothing else
        for stderr in (err, narrow):
            self.assertIn(f"предупреждение: пересечений линий: {render.MANY_CROSSINGS}", stderr)
        head, steps, _, _ = self.read_block(err)
        self.assertEqual((head["term"], head["after"]), ("пересечений", "0"), err)
        self.assertEqual(len(steps), 1, err)
        move = steps[0]["what"]
        # the one move the author is offered at the default width is not offered at the narrow one
        head, steps, _, _ = self.read_block(narrow)
        self.assertEqual((head["term"], head["after"]), ("пересечений", "0"), narrow)
        self.assertNotIn(move, [step["what"] for step in steps], narrow)
        # and each block is the one the search finds under that render's own overrides
        self.assertEqual(advice_blocks(err)[0], self.advice_lines(NARROW, wide), err)
        self.assertEqual(advice_blocks(narrow)[0], self.advice_lines(NARROW, thin), narrow)
        # the premise, read off the geometry rather than off the two blocks: at the narrow width
        # that move brings a label message the author's own grid does not carry, which is what the
        # search refuses it for, and at the default width it brings none
        for ov, refused in ((overrides, True), ({}, False)):
            brought = (advice.evaluate(wide[0][0].apply(NARROW), "widget", ov)[1]
                       - advice.evaluate(copy.deepcopy(NARROW), "widget", ov)[1])
            self.assertEqual(bool([m for m in brought if "подпись" in m]), refused, brought)

    # Spec 6 as amended, over the population the search is measured on: every step of a block names
    # the term of the score it moved, and a sequence never ends in a move that only shortened the
    # lines.
    def test_no_step_of_the_seeded_populations_blocks_stands_still(self):
        for k, model in seeded_models():
            found = advice.search(model, ADVICE_MODE)
            with self.subTest(instance=k):
                self.assertTrue(found)
                lines = render.advice_block(found, render.advised_grid(model, found),
                                            render.advised_lanes(found), "")
                cut = lines.index("grid:")
                steps = [STEP.match(line) for line in lines[1:cut]]
                self.assertTrue(all(steps), lines[1:cut])
                for step in steps:
                    self.assertNotEqual(step["before"], step["after"], step.group(0))
                self.assertLess(found[-1][2][:2], found[-1][1][:2], lines[cut - 1])

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
        head, steps, rows, lanes = self.read_block(err)
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
