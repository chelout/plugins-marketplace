"""Node model errors stay fatal even when layout errors may be drafted."""
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


if __name__ == "__main__":
    unittest.main()
