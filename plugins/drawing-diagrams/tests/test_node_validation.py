"""Group, lane and node checks of flow.plan, each held by its exact message: model errors stay fatal
even when layout errors may be drafted, layout errors turn into draft warnings, warnings leave the
plan laid out. A fit error is a layout error that plan() also lists as a fit: fatal without draft,
a draft warning with it, and its message carries the numbers and the advice of each mode.

Node checks here are those of the node loop and those plan() runs over the described nodes after
it: where each node stands in the grid (placement, empty rows and columns, a swimlane row), and the
edges a node needs (a decision's exits and their labels, a step's way out and way in)."""
import copy
import unittest

import support  # noqa: F401
from diagrams import flow
from diagrams.common import ModelError

DRAFT = "черновик: "


def model():
    return {"kind": "flow", "groups": {"g": {"label": "G", "ramp": "teal"}},
            "nodes": [{"id": "a", "title": "A", "kind": "terminal"}], "grid": ["a"]}


def decision_model():
    return {"kind": "flow", "nodes": [{"id": "choose?", "title": "Choose?"},
                                      {"id": "yes", "title": "Yes", "kind": "terminal"},
                                      {"id": "no", "title": "No", "kind": "terminal"}],
            "grid": ["choose? .", "yes no"],
            "edges": ["choose? -> yes : yes", "choose? -> no : no"]}


def swimlane_model():
    return {"kind": "swimlane",
            "groups": {"g": {"label": "G", "ramp": "teal"},
                       "h": {"label": "H", "ramp": "purple"}},
            "lanes": ["g", "h"],
            "nodes": [{"id": "a", "title": "A"},
                      {"id": "b", "title": "B", "kind": "terminal"}],
            "grid": ["a .", ". b"], "edges": ["a -> b"]}


def wide_swimlane_model(count):
    ramps = ("teal", "purple", "coral", "pink", "gray", "blue", "green", "amber", "red")
    lanes = [f"l{i}" for i in range(count)]
    return {"kind": "swimlane",
            "groups": {lane: {"label": lane.upper(), "ramp": ramps[i % len(ramps)]} for i, lane in enumerate(lanes)},
            "lanes": lanes,
            "nodes": [{"id": f"n{i}", "title": "N", "kind": "terminal"} for i in range(count)],
            "grid": [" ".join(f"n{i}" for i in range(count))]}


def many_nodes_model(count):
    ids = [f"n{i}" for i in range(count)]
    return {"kind": "flow",
            "nodes": [{"id": nid, "title": nid.upper(), "kind": "terminal"} for nid in ids],
            "grid": [" ".join((ids + ["."] * 3)[r:r + 4]) for r in range(0, count, 4)]}


def block_model(items):
    return {"kind": "blocks", "nodes": [{"id": "a", "title": "A", "kind": "block", "items": items}], "grid": ["a"]}


def notes_model(**first):
    """Four notes in one row, the narrowest flow card of both modes; a note needs no edge, so the
    fields given to the first one are the only thing a check can object to."""
    nodes = [{"id": nid, "title": nid.upper(), "kind": "note"} for nid in "abcd"]
    nodes[0].update(first)
    return {"kind": "flow", "nodes": nodes, "grid": ["a b c d"]}


def blocks_row_model(items):
    """Three blocks in one row, the widest grid blocks take in widget; the items go to the first."""
    nodes = [{"id": nid, "title": nid.upper(), "kind": "block"} for nid in "abc"]
    nodes[0]["items"] = items
    return {"kind": "blocks", "nodes": nodes, "grid": ["a b c"]}


def many_blocks_model(count):
    ids = [f"n{i}" for i in range(count)]
    return {"kind": "blocks",
            "nodes": [{"id": nid, "title": nid.upper(), "kind": "block"} for nid in ids],
            "grid": [" ".join((ids + ["."] * 2)[r:r + 3]) for r in range(0, count, 3)]}


def lane_groups_model(count):
    """One lane among `count` groups, so the group count is the only thing past a limit."""
    ramps = ("teal", "purple", "coral", "pink", "gray", "blue", "green", "amber", "red")
    return {"kind": "swimlane",
            "groups": {f"l{i}": {"label": f"L{i}", "ramp": ramps[i]} for i in range(count)},
            "lanes": ["l0"], "nodes": [{"id": "n0", "title": "N", "kind": "terminal"}], "grid": ["n0"]}


def terminals_model(grid):
    return {"kind": "flow", "nodes": [{"id": "a", "title": "A", "kind": "terminal"},
                                      {"id": "b", "title": "B", "kind": "terminal"}], "grid": grid}


class NodeValidation(unittest.TestCase):
    def assertValid(self, model):
        for mode in ("widget", "page"):
            for draft in (False, True):
                with self.subTest(mode=mode, draft=draft):
                    _, warnings = flow.plan(copy.deepcopy(model), mode, draft=draft)
                    self.assertEqual(warnings, [])

    def assertInvalid(self, model, message):
        for mode in ("widget", "page"):
            for draft in (False, True):
                with self.subTest(mode=mode, draft=draft):
                    with self.assertRaises(ModelError) as ctx:
                        flow.plan(copy.deepcopy(model), mode, draft=draft)
                    self.assertEqual(ctx.exception.errors, [message])
                    self.assertEqual(ctx.exception.layout, [])
                    self.assertEqual(ctx.exception.fit, [])

    def assertWarning(self, model, message=None, **messages):
        """`message` is the one warning both modes raise; where the warning names a limit of its mode,
        `messages` maps each mode to the whole list it expects instead, [] for a mode within it."""
        for mode in ("widget", "page"):
            expected = [message] if message is not None else messages[mode]
            for draft in (False, True):
                with self.subTest(mode=mode, draft=draft):
                    layout, warnings = flow.plan(copy.deepcopy(model), mode, draft=draft)
                    self.assertFalse(layout["draft"])
                    self.assertEqual(warnings, expected)

    def assertDrafted(self, model, messages, fit, alone):
        """`messages` maps each mode to the layout errors it expects, in order: fatal without draft,
        each of them also a fit error when `fit`; with draft the plan is laid out as a draft and the
        leading warnings are those errors behind the draft prefix. `alone` holds them to be every
        warning the plan raises, otherwise the warnings without the prefix are not compared."""
        for mode in ("widget", "page"):
            expected = messages[mode]
            with self.subTest(mode=mode, draft=False):
                with self.assertRaises(ModelError) as ctx:
                    flow.plan(copy.deepcopy(model), mode)
                self.assertEqual(ctx.exception.errors, expected)
                self.assertEqual(ctx.exception.layout, expected)
                self.assertEqual(ctx.exception.fit, expected if fit else [])
            with self.subTest(mode=mode, draft=True):
                layout, warnings = flow.plan(copy.deepcopy(model), mode, draft=True)
                self.assertTrue(layout["draft"])
                drafted = [DRAFT + m for m in expected]
                if alone:
                    self.assertEqual(warnings, drafted)
                else:
                    self.assertEqual([w for w in warnings if w.startswith(DRAFT)], drafted)

    def assertLayout(self, model, **messages):
        """Layout errors that are no fit errors; warnings besides the drafted ones may come too."""
        self.assertDrafted(model, messages, fit=False, alone=False)

    def assertFit(self, model, **messages):
        """Fit errors, each the whole message of its mode, with nothing else raised beside them."""
        self.assertDrafted(model, messages, fit=True, alone=True)

    def test_group_id_charset(self):
        valid = model()
        self.assertValid(valid)
        for gid, message in (("G", "группа 'G': id только из строчных латинских букв, цифр и _"),
                             ("g?", "группа 'g?': id только из строчных латинских букв, цифр и _")):
            with self.subTest(gid=gid):
                invalid = copy.deepcopy(valid)
                invalid["groups"][gid] = {"label": "X", "ramp": "teal"}
                self.assertInvalid(invalid, message)

    def test_group_ramp(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["groups"]["g"]["ramp"] = "violet"
        self.assertInvalid(invalid, "группа g: ramp должен быть одним из "
                           "purple, teal, coral, pink, gray, blue, green, amber, red")

    def test_too_many_groups_warns(self):
        valid = model()
        valid["groups"].update({f"g{i}": {"label": f"G{i}", "ramp": "teal"} for i in range(1, 4)})
        self.assertValid(valid)
        crowded = copy.deepcopy(valid)
        crowded["groups"]["g4"] = {"label": "G4", "ramp": "teal"}
        self.assertWarning(crowded, "групп 5: больше 4 цветов читаются плохо")

    def test_swimlane_needs_lanes(self):
        valid = swimlane_model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        del invalid["lanes"]
        self.assertInvalid(invalid, "swimlane: нужен список lanes с id групп, по одной на столбец")

    def test_lane_count_matches_grid_columns(self):
        valid = swimlane_model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["lanes"] = ["g"]
        self.assertInvalid(invalid, "swimlane: дорожек 1, а столбцов в grid 2; каждая дорожка это столбец")

    def test_too_many_lanes(self):
        # max_lanes equals max_cols in both swimlane modes and the lanes must equal the grid's
        # columns, so a lane over the limit always comes with a grid too wide, reported first
        self.assertLayout(
            wide_swimlane_model(8),
            widget=["grid шириной 8: режим widget для swimlane допускает от 1 до 5 столбцов",
                    "swimlane: дорожек 8, режим widget допускает до 5; "
                    "объедините второстепенных участников в одну дорожку"],
            page=["grid шириной 8: режим page для swimlane допускает от 1 до 7 столбцов",
                  "swimlane: дорожек 8, режим page допускает до 7; "
                  "объедините второстепенных участников в одну дорожку"])

    def test_lane_must_be_a_group(self):
        valid = swimlane_model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["lanes"] = ["g", "x"]
        self.assertInvalid(invalid, "swimlane: дорожка 'x' не описана в groups")

    def test_too_many_nodes(self):
        self.assertValid(many_nodes_model(16))
        self.assertLayout(
            many_nodes_model(31),
            widget=["узлов 31, режим widget допускает до 16: разбейте схему на обзор и детали"],
            page=["узлов 31, режим page допускает до 30: разбейте схему на обзор и детали"])

    def test_node_id_charset(self):
        valid = model()
        self.assertValid(valid)
        # a node with an invalid id is skipped before placement, so it stays out of grid, where it
        # would otherwise be reported as placed but not described
        for nid, message in (("Bad", "узел 'Bad': id только из строчных латинских букв, цифр и _, "
                                     "знак ? допустим последним"),
                             ("a-b", "узел 'a-b': id только из строчных латинских букв, цифр и _, "
                                     "знак ? допустим последним")):
            with self.subTest(nid=nid):
                invalid = copy.deepcopy(valid)
                invalid["nodes"].append({"id": nid, "title": "B"})
                self.assertInvalid(invalid, message)

    def test_duplicate_node_id(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["nodes"].append({"id": "a", "title": "A2", "kind": "terminal"})
        self.assertInvalid(invalid, "узел a: id повторяется")

    def test_invalid_kind(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["nodes"][0]["kind"] = "triangle"
        self.assertInvalid(invalid, "узел a: kind 'triangle' не из "
                           "('step', 'decision', 'terminal', 'note', 'state', 'block')")

    def test_decision_id_requires_decision_kind(self):
        # Both labelled exits are present, so the mismatch is the only invalid field.
        valid = decision_model()
        self.assertValid(valid)
        valid["nodes"][0]["kind"] = "decision"
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["nodes"][0]["kind"] = "step"
        self.assertInvalid(invalid, "узел choose?: id с ? на конце это развилка, а kind = step")

    def test_unknown_group(self):
        valid = model()
        self.assertValid(valid)
        valid["nodes"][0]["group"] = "g"
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["nodes"][0]["group"] = "missing"
        self.assertInvalid(invalid, "узел a: группа 'missing' не описана в groups")

    def test_swimlane_group_must_match_lane(self):
        valid = swimlane_model()
        self.assertValid(valid)
        valid["nodes"][0]["group"] = "g"
        valid["nodes"][1]["group"] = "h"
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        # The other group exists; only its disagreement with the lane is invalid.
        invalid["nodes"][0]["group"] = "h"
        self.assertInvalid(invalid, "узел a: стоит в дорожке g, а group = h; цвет узла задаёт дорожка")

    def test_node_footnote_must_be_described(self):
        valid = model()
        valid["nodes"][0].update(kind="note", text="Текст [1]")
        valid["footnotes"] = ["Пояснение"]
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        del invalid["footnotes"]
        self.assertInvalid(invalid, "узел a: сноска [1] не описана в footnotes")

    def test_items_only_on_block_warns(self):
        valid = model()
        self.assertValid(valid)
        shown = copy.deepcopy(valid)
        shown["nodes"][0]["items"] = ["Пункт"]
        self.assertWarning(shown, "узел a: items показываются только у block")

    def test_at_most_five_items(self):
        self.assertValid(block_model([f"Пункт {i}" for i in range(1, 6)]))
        message = "узел a: пунктов 6, допустимо пять"
        self.assertLayout(block_model([f"Пункт {i}" for i in range(1, 7)]), widget=[message], page=[message])

    def test_terminal_text_warns(self):
        valid = model()
        self.assertValid(valid)
        hidden = copy.deepcopy(valid)
        hidden["nodes"][0]["text"] = "Текст"
        self.assertWarning(hidden, "узел a: у terminal текст не показывается, только заголовок")

    def test_swimlane_lanes_null_or_empty(self):
        valid = swimlane_model()
        self.assertValid(valid)
        for lanes in (None, []):
            with self.subTest(lanes=lanes):
                invalid = copy.deepcopy(valid)
                invalid["lanes"] = lanes
                self.assertInvalid(invalid, "swimlane: нужен список lanes с id групп, по одной на столбец")

    def test_swimlane_group_count_warns(self):
        # a swimlane's colour limit is its lane limit, 5 in widget and 7 in page, not the 4 of flow
        self.assertValid(lane_groups_model(5))
        self.assertWarning(lane_groups_model(7), widget=["групп 7: больше 5 цветов читаются плохо"], page=[])
        self.assertWarning(lane_groups_model(8), widget=["групп 8: больше 5 цветов читаются плохо"],
                           page=["групп 8: больше 7 цветов читаются плохо"])

    def test_too_many_blocks(self):
        self.assertValid(many_blocks_model(12))
        self.assertLayout(
            many_blocks_model(21),
            widget=["узлов 21, режим widget допускает до 12: разбейте схему на обзор и детали"],
            page=["узлов 21, режим page допускает до 20: разбейте схему на обзор и детали"])

    def test_node_id_missing_or_empty(self):
        valid = model()
        self.assertValid(valid)
        for nid, message in ((None, "узел None: id только из строчных латинских букв, цифр и _, "
                                    "знак ? допустим последним"),
                             ("", "узел '': id только из строчных латинских букв, цифр и _, "
                                  "знак ? допустим последним")):
            with self.subTest(nid=nid):
                invalid = copy.deepcopy(valid)
                invalid["nodes"].append({"title": "B"} if nid is None else {"id": nid, "title": "B"})
                self.assertInvalid(invalid, message)

    def test_title_required(self):
        # absent, null, empty and white space alone are one missing title
        valid = model()
        self.assertValid(valid)
        for case, title in (("absent", None), ("null", None), ("empty", ""), ("blank", " \t ")):
            with self.subTest(title=case):
                invalid = copy.deepcopy(valid)
                if case == "absent":
                    del invalid["nodes"][0]["title"]
                else:
                    invalid["nodes"][0]["title"] = title
                self.assertInvalid(invalid, "узел a: нет title")

    def test_title_must_fit(self):
        self.assertValid(notes_model())
        self.assertFit(notes_model(title="A" * 80),
                       widget=["узел a: заголовок 80 симв., влезает 13; сократите заголовок или сузьте grid"],
                       page=["узел a: заголовок 80 симв., влезает 25; сократите заголовок или сузьте grid"])

    def test_text_word_must_fit(self):
        # of several words too wide only the first is named, and no line count is reported beside it
        for text, length in (("W" * 80, 80), ("W" * 40 + " " + "W" * 80 + " " + "W" * 60, 40)):
            with self.subTest(text=text[:12], length=length):
                self.assertFit(notes_model(text=text),
                               widget=[f"узел a: слово {length} симв., влезает ~15"],
                               page=[f"узел a: слово {length} симв., влезает ~28"])

    def test_text_must_fit_two_lines(self):
        self.assertValid(notes_model(text="Короткий текст"))
        self.assertFit(notes_model(text=("word " * 40).strip()),
                       widget=["узел a: текст 199 симв., в две строки влезает ~41; сократите или вынесите в сноску"],
                       page=["узел a: текст 199 симв., в две строки влезает ~73; сократите или вынесите в сноску"])

    def test_item_word_must_fit(self):
        self.assertValid(blocks_row_model(["Пункт"]))
        for items, pos, length in ((["W" * 80], 1, 80), (["Пункт", "W" * 80], 2, 80),
                                   (["W" * 40 + " " + "W" * 80 + " " + "W" * 60], 1, 40)):
            with self.subTest(pos=pos, length=length):
                self.assertFit(blocks_row_model(items),
                               widget=[f"узел a: пункт {pos} — слово {length} симв., влезает ~21"],
                               page=[f"узел a: пункт {pos} — слово {length} симв., влезает ~39"])

    def test_item_must_fit_two_lines(self):
        long = ("word " * 60).strip()
        for items, pos in (([long], 1), (["Пункт", long], 2)):
            with self.subTest(pos=pos):
                self.assertFit(blocks_row_model(items),
                               widget=[f"узел a: пункт {pos} — 299 симв., влезает ~53"],
                               page=[f"узел a: пункт {pos} — 299 симв., влезает ~102"])

    def test_node_must_be_placed(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["nodes"].append({"id": "b", "title": "B", "kind": "terminal"})
        self.assertInvalid(invalid, "узел b описан, но не стоит в grid")

    def test_placed_node_must_be_described(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["grid"] = ["a b"]
        self.assertInvalid(invalid, "grid: b стоит в карте, но не описан")

    def test_empty_row_warns(self):
        self.assertValid(terminals_model(["a", "b"]))
        self.assertWarning(terminals_model(["a", ".", "b"]), "пустые ряды в grid: [1]")

    def test_empty_column_warns(self):
        self.assertValid(terminals_model(["a b"]))
        self.assertWarning(terminals_model(["a . b"]), "пустые столбцы в grid: [1]")

    def test_swimlane_same_row_warns(self):
        valid = swimlane_model()
        self.assertValid(valid)
        crowded = copy.deepcopy(valid)
        crowded["grid"] = ["a b"]
        self.assertWarning(crowded, "swimlane, ряд 0: узлы ['a', 'b'] стоят в одном ряду, "
                                    "читается как одновременность; так задумано?")

    def test_decision_needs_two_exits(self):
        valid = decision_model()
        self.assertValid(valid)
        for kept, message in ((1, "развилка choose?: исходящих связей 1, нужно не меньше двух"),
                              (0, "развилка choose?: исходящих связей 0, нужно не меньше двух")):
            with self.subTest(exits=kept):
                invalid = copy.deepcopy(valid)
                invalid["edges"] = invalid["edges"][:kept]
                self.assertInvalid(invalid, message)

    def test_decision_branch_needs_label(self):
        # both exits stay, so the missing label is the only thing wrong
        valid = decision_model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["edges"][1] = "choose? -> no"
        self.assertInvalid(invalid, "развилка choose?: ветка в no без подписи")

    def test_step_without_exit_warns(self):
        valid = model()
        self.assertValid(valid)
        note = copy.deepcopy(valid)
        note["nodes"][0]["kind"] = "note"
        self.assertValid(note)
        step = copy.deepcopy(valid)
        del step["nodes"][0]["kind"]
        self.assertWarning(step, "узел a: нет исходящих связей, а это не terminal")

    def test_unreachable_node_warns(self):
        def reach(grid, edges, b_kind="step"):
            return {"kind": "flow", "nodes": [{"id": "a", "title": "A", "kind": "terminal"},
                                              {"id": "b", "title": "B", "kind": b_kind},
                                              {"id": "s", "title": "S"}],
                    "grid": grid, "edges": edges}
        # s starts in row zero; b is reached from it, or stands in row zero itself, or is a note
        self.assertValid(reach(["s", "b", "a"], ["s -> b", "b -> a"]))
        self.assertValid(reach(["s b", ". a"], ["s -> a", "b -> a"]))
        self.assertValid(reach(["s", "b", "a"], ["s -> a", "b -> a"], b_kind="note"))
        self.assertWarning(reach(["s", "b", "a"], ["s -> a", "b -> a"]), "узел b: нет входящих связей, недостижим")


if __name__ == "__main__":
    unittest.main()
