import re
import unittest

import support  # noqa: F401
from diagrams import flow, schema, timeline
from diagrams.common import ModelError


def flow_model(nodes, grid, edges=(), kind="flow"):
    return {"kind": kind, "groups": {"g": {"label": "g", "ramp": "teal"}}, "nodes": nodes, "grid": grid,
            "edges": list(edges)}


class FitMessages(unittest.TestCase):
    def failure(self, mod, model):
        with self.assertRaises(ModelError) as ctx:
            mod.plan(model, "widget")
        return ctx.exception

    def message(self, exc, prefix):
        found = [e for e in exc.errors if e.startswith(prefix)]
        self.assertTrue(found, f"no error starting with {prefix!r} in {exc.errors}")
        return found[0]

    def assertBudget(self, message, pattern):
        m = re.search(pattern, message)
        self.assertIsNotNone(m, message)
        self.assertLess(int(m.group(2)), int(m.group(1)), message)

    def test_title(self):
        nodes = [{"id": n, "kind": "terminal", "title": "Очень длинный заголовок узла" if n == "a" else n.upper()}
                 for n in "abcd"]
        exc = self.failure(flow, flow_model(nodes, ["a b c d"]))
        msg = self.message(exc, "узел a:")
        self.assertBudget(msg, r"заголовок (\d+) симв\., влезает (\d+)")
        self.assertIn(msg, exc.fit)
        self.assertIn(msg, exc.layout)

    def test_text(self):
        text = "Длинное описание шага, которое никак не помещается в две строки узкой карточки на четыре колонки"
        nodes = [{"id": n, "title": n.upper(), **({"text": text} if n == "a" else {})} for n in "abcd"]
        exc = self.failure(flow, flow_model(nodes, ["a b c d"]))
        msg = self.message(exc, "узел a:")
        self.assertBudget(msg, r"текст (\d+) симв\., в две строки влезает ~(\d+)")
        self.assertIn(msg, exc.fit)

    def test_block_item(self):
        item = "очень длинный пункт блока, который займёт заметно больше двух строк в карточке шириной в треть виджета"
        nodes = [{"id": n, "title": n.upper(), "items": [item] if n == "a" else []} for n in "abc"]
        exc = self.failure(flow, flow_model(nodes, ["a b c"], kind="blocks"))
        msg = self.message(exc, "узел a:")
        self.assertBudget(msg, r"пункт 1 — (\d+) симв\., влезает ~(\d+)")
        self.assertIn(msg, exc.fit)

    def test_edge_label(self):
        nodes = [{"id": "a?", "title": "Да?"}, {"id": "b", "kind": "terminal", "title": "B"},
                 {"id": "c", "kind": "terminal", "title": "C"}]
        exc = self.failure(flow, flow_model(nodes, ["a? b", "c ."], ["a? -> b : вправо идём", "a? -> c : вниз"]))
        msg = self.message(exc, "связь a? -> b:")
        self.assertBudget(msg, r"подпись 'вправо идём' (\d+) симв\. не помещается .*, влезает ~(\d+)")
        self.assertIn(msg, exc.fit)

    def test_schema_key_row_warning(self):
        tables = [{"id": "t", "name": "t", "group": "g",
                   "columns": [{"name": "external_correlation_identifier", "type": "uuid", "flags": ["PK"]}]}]
        tables += [{"id": x, "name": x, "group": "g", "columns": [{"name": "id", "flags": ["PK"]}]} for x in "uv"]
        _, warnings = schema.plan({"kind": "schema", "groups": {"g": {"label": "g", "ramp": "teal"}},
                                   "tables": tables, "grid": ["t u v"]}, "widget")
        msg = next(w for w in warnings if w.startswith("таблица t.external_correlation_identifier:"))
        self.assertBudget(msg, r"имя (\d+) симв\., влезает ~(\d+)")

    def test_timeline_title_and_text(self):
        model = {"kind": "timeline", "entities": [{"id": "e", "label": "e"}],
                 "moments": [{"id": "m1", "label": "t1", "title": ("Заголовок момента " * 5).strip(),
                              "text": "слово " * 60, "states": {"e": "x"}},
                             {"id": "m2", "label": "t2", "title": "ок", "states": {"e": "y"}}]}
        exc = self.failure(timeline, model)
        titles = [e for e in exc.errors if "заголовок" in e]
        texts = [e for e in exc.errors if "текст" in e]
        self.assertBudget(titles[0], r"момент m1: заголовок (\d+) симв\., влезает (\d+)")
        self.assertBudget(texts[0], r"момент m1: текст (\d+) симв\., в две строки влезает ~(\d+)")
        self.assertEqual(sorted(exc.fit), sorted(titles + texts))


if __name__ == "__main__":
    unittest.main()
