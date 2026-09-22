"""Group, lane and node checks of flow.plan, each held by its exact message: model errors stay fatal
even when layout errors may be drafted, layout errors turn into draft warnings, warnings leave the
plan laid out."""
import copy
import unittest

import support  # noqa: F401
from diagrams import flow
from diagrams.common import ModelError


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

    def assertWarning(self, model, message):
        for mode in ("widget", "page"):
            for draft in (False, True):
                with self.subTest(mode=mode, draft=draft):
                    layout, warnings = flow.plan(copy.deepcopy(model), mode, draft=draft)
                    self.assertFalse(layout["draft"])
                    self.assertEqual(warnings, [message])

    def assertLayout(self, model, **messages):
        """`messages` maps each mode to the layout errors it expects, in order: fatal without draft,
        the leading draft warnings with it."""
        for mode in ("widget", "page"):
            expected = messages[mode]
            with self.subTest(mode=mode, draft=False):
                with self.assertRaises(ModelError) as ctx:
                    flow.plan(copy.deepcopy(model), mode)
                self.assertEqual(ctx.exception.errors, expected)
                self.assertEqual(ctx.exception.layout, expected)
                self.assertEqual(ctx.exception.fit, [])
            with self.subTest(mode=mode, draft=True):
                layout, warnings = flow.plan(copy.deepcopy(model), mode, draft=True)
                self.assertTrue(layout["draft"])
                self.assertEqual([w for w in warnings if w.startswith("черновик: ")],
                                 ["черновик: " + m for m in expected])

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


if __name__ == "__main__":
    unittest.main()
