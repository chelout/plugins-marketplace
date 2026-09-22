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

    def test_blank_title(self):
        # a title of white space alone draws a card lower than the least height the label model of
        # diagrams/labels.py reads every card at (CARD_LEAST), so it is refused as a missing one
        for title in (None, "", " ", "\t \n"):
            with self.subTest(title=title):
                nodes = [{"id": n, "title": n.upper()} for n in "abc"]
                if title is None:
                    del nodes[0]["title"]
                else:
                    nodes[0]["title"] = title
                exc = self.failure(flow, flow_model(nodes, ["a b c"]))
                self.assertEqual([e for e in exc.errors if e.startswith("узел a:")],
                                 ["узел a: нет title"])

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

    def test_edge_label_wide_glyphs(self):
        nodes = [{"id": "a?", "title": "Да?"}, {"id": "b", "kind": "terminal", "title": "B"},
                 {"id": "c", "kind": "terminal", "title": "C"}]
        exc = self.failure(flow, flow_model(nodes, ["a? b", "c ."], ["a? -> b : ШШШ", "a? -> c : вниз"]))
        msg = self.message(exc, "связь a? -> b:")
        self.assertBudget(msg, r"подпись 'ШШШ' (\d+) симв\. не помещается .*, влезает ~(\d+)")
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

    # -- floor-of-1 class (round 4): a budget must never be clamped to a minimum of 1 --

    def test_timeline_title_zero_budget(self):
        # title "a" next to a tag so wide that not even an empty title would fit.
        model = {"kind": "timeline", "entities": [{"id": "e", "label": "e"}],
                 "moments": [{"id": "m1", "label": "t1", "title": "a", "tag": "Ш" * 80, "states": {"e": "x"}},
                             {"id": "m2", "label": "t2", "title": "ок", "states": {"e": "y"}}]}
        exc = self.failure(timeline, model)
        msg = self.message(exc, "момент m1: заголовок")
        self.assertIn("заголовок 1 симв., влезает 0", msg)

    def test_schema_key_row_zero_budget(self):
        # a one-character key name next to a type so long the row overflows without the name at all.
        tables = [{"id": "t", "name": "t", "group": "g",
                   "columns": [{"name": "x", "type": "u" * 30, "flags": ["PK"]}]}]
        tables += [{"id": x, "name": x, "group": "g", "columns": [{"name": "id", "flags": ["PK"]}]} for x in "uvw"]
        _, warnings = schema.plan({"kind": "schema", "groups": {"g": {"label": "g", "ramp": "teal"}},
                                   "tables": tables, "grid": ["t u v w"]}, "page")
        msg = next(w for w in warnings if w.startswith("таблица t.x:"))
        self.assertIn("имя 1 симв., влезает ~0", msg)

    # -- word-overflow class: a word wider than its box is clipped, not wrapped --

    URL = "https://kyc.example.com/v2/applicants/verification_status_callback"

    def budget_of(self, message, pattern):
        self.assertBudget(message, pattern)
        return int(re.search(pattern, message).group(2))

    def assertNoMessage(self, exc, pattern):
        hit = [e for e in exc.errors if re.search(pattern, e)]
        self.assertFalse(hit, f"{pattern!r} should not be reported for a too-wide word: {hit}")

    def test_node_text_long_word(self):
        # the text box is 120 px on four widget columns; the token measures about 408
        nodes = [{"id": n, "title": n.upper(), **({"text": self.URL} if n == "a" else {})} for n in "abcd"]
        exc = self.failure(flow, flow_model(nodes, ["a b c d"]))
        msg = self.message(exc, "узел a: слово")
        budget = self.budget_of(msg, r"слово (\d+) симв\., влезает ~(\d+)")
        self.assertIn(msg, exc.fit)
        self.assertIn(msg, exc.layout)
        self.assertNoMessage(exc, r"узел a: текст")
        nodes[0]["text"] = self.URL[:budget]
        self.rerun_without(flow, flow_model(nodes, ["a b c d"]), "узел a:")

    def test_block_item_long_word(self):
        nodes = [{"id": n, "title": n.upper(), "items": [self.URL] if n == "a" else []} for n in "abc"]
        exc = self.failure(flow, flow_model(nodes, ["a b c"], kind="blocks"))
        msg = self.message(exc, "узел a: пункт 1 — слово")
        budget = self.budget_of(msg, r"пункт 1 — слово (\d+) симв\., влезает ~(\d+)")
        self.assertIn(msg, exc.fit)
        self.assertIn(msg, exc.layout)
        self.assertNoMessage(exc, r"пункт 1 — \d+ симв\.")
        nodes[0]["items"] = [self.URL[:budget]]
        self.rerun_without(flow, flow_model(nodes, ["a b c"], kind="blocks"), "узел a:")

    def timeline_model(self, text):
        return {"kind": "timeline", "entities": [{"id": "e", "label": "e"}],
                "moments": [{"id": "m1", "label": "t1", "title": "ок", "text": text, "states": {"e": "x"}},
                            {"id": "m2", "label": "t2", "title": "ок", "states": {"e": "y"}}]}

    def test_timeline_text_long_word(self):
        url = self.URL + "?attempt=4b&reason=document_unreadable"
        exc = self.failure(timeline, self.timeline_model(url))
        msg = self.message(exc, "момент m1: слово")
        budget = self.budget_of(msg, r"слово (\d+) симв\., влезает ~(\d+)")
        self.assertIn(msg, exc.fit)
        self.assertIn(msg, exc.layout)
        self.assertNoMessage(exc, r"момент m1: текст")
        self.rerun_without(timeline, self.timeline_model(url[:budget]), "момент m1:")

    def test_first_too_wide_word_only(self):
        second = self.URL + "/and_one_more_segment"
        nodes = [{"id": n, "title": n.upper(), **({"text": f"{self.URL} {second}"} if n == "a" else {})}
                 for n in "abcd"]
        exc = self.failure(flow, flow_model(nodes, ["a b c d"]))
        words = [e for e in exc.errors if e.startswith("узел a: слово")]
        self.assertEqual(len(words), 1, exc.errors)
        self.assertIn(f"слово {len(self.URL)} симв.", words[0])

    # -- the same class where the line count actually disagrees: one or two too-wide words wrap to
    # one and two lines, which the two-line check accepts anyway, so only three of them reach the
    # case where that check fails on its own and skipping it is what keeps its message away.

    def three_wide_words(self, base):
        """Three words, each wider than the box on its own, so each starts a line of its own."""
        return [base, base + "/second_segment", base + "/third_segment"]

    def assertOnlyFirstWord(self, exc, prefix, words):
        found = [e for e in exc.errors if e.startswith(prefix)]
        self.assertEqual(len(found), 1, exc.errors)
        self.assertIn(f"слово {len(words[0])} симв.", found[0])

    def test_node_text_three_wide_words(self):
        words = self.three_wide_words(self.URL)
        nodes = [{"id": n, "title": n.upper(), **({"text": " ".join(words)} if n == "a" else {})}
                 for n in "abcd"]
        exc = self.failure(flow, flow_model(nodes, ["a b c d"]))
        self.assertOnlyFirstWord(exc, "узел a: слово", words)
        self.assertNoMessage(exc, r"узел a: текст")

    def test_block_item_three_wide_words(self):
        words = self.three_wide_words(self.URL)
        nodes = [{"id": n, "title": n.upper(), "items": [" ".join(words)] if n == "a" else []}
                 for n in "abc"]
        exc = self.failure(flow, flow_model(nodes, ["a b c"], kind="blocks"))
        self.assertOnlyFirstWord(exc, "узел a: пункт 1 — слово", words)
        self.assertNoMessage(exc, r"пункт 1 — \d+ симв\.")

    def test_timeline_text_three_wide_words(self):
        words = self.three_wide_words(self.URL + "?attempt=4b&reason=document_unreadable")
        exc = self.failure(timeline, self.timeline_model(" ".join(words)))
        self.assertOnlyFirstWord(exc, "момент m1: слово", words)
        self.assertNoMessage(exc, r"момент m1: текст")

    # -- round trip: cutting a text to its reported budget must pass the same check again --

    def assertGone(self, errors, prefix):
        still = [e for e in errors if e.startswith(prefix)]
        self.assertFalse(still, f"message {prefix!r} still present: {still}")

    def rerun_without(self, mod, model, prefix):
        """Runs the same check again; returns the errors list if it still raises, else []."""
        try:
            mod.plan(model, "widget")
            return []
        except ModelError as exc:
            self.assertGone(exc.errors, prefix)
            return exc.errors

    def test_budget_round_trip(self):
        # site 1: flow.py node title
        with self.subTest(site="flow title"):
            title = "Очень длинный заголовок узла"
            nodes = [{"id": n, "kind": "terminal", "title": title if n == "a" else n.upper()} for n in "abcd"]
            exc = self.failure(flow, flow_model(nodes, ["a b c d"]))
            budget = int(re.search(r"заголовок (\d+) симв\., влезает (\d+)",
                                    self.message(exc, "узел a:")).group(2))
            nodes[0]["title"] = title[:budget]
            self.rerun_without(flow, flow_model(nodes, ["a b c d"]), "узел a: заголовок")

        # site 2: flow.py node text
        with self.subTest(site="flow text"):
            text = "Длинное описание шага, которое никак не помещается в две строки узкой карточки на четыре колонки"
            nodes = [{"id": n, "title": n.upper(), **({"text": text} if n == "a" else {})} for n in "abcd"]
            exc = self.failure(flow, flow_model(nodes, ["a b c d"]))
            budget = int(re.search(r"текст (\d+) симв\., в две строки влезает ~(\d+)",
                                    self.message(exc, "узел a:")).group(2))
            nodes[0]["text"] = text[:budget]
            self.rerun_without(flow, flow_model(nodes, ["a b c d"]), "узел a: текст")

        # site 3: flow.py block item
        with self.subTest(site="flow block item"):
            item = "очень длинный пункт блока, который займёт заметно больше двух строк в карточке шириной в треть виджета"
            nodes = [{"id": n, "title": n.upper(), "items": [item] if n == "a" else []} for n in "abc"]
            exc = self.failure(flow, flow_model(nodes, ["a b c"], kind="blocks"))
            budget = int(re.search(r"пункт 1 — (\d+) симв\., влезает ~(\d+)",
                                    self.message(exc, "узел a:")).group(2))
            nodes[0]["items"] = [item[:budget]]
            self.rerun_without(flow, flow_model(nodes, ["a b c"], kind="blocks"), "узел a: пункт 1")

        # site 4a: flow.py edge label, cyrillic
        with self.subTest(site="flow edge label"):
            nodes = [{"id": "a?", "title": "Да?"}, {"id": "b", "kind": "terminal", "title": "B"},
                     {"id": "c", "kind": "terminal", "title": "C"}]
            label = "вправо идём"
            model = flow_model(nodes, ["a? b", "c ."], [f"a? -> b : {label}", "a? -> c : вниз"])
            exc = self.failure(flow, model)
            budget = int(re.search(fr"подпись '{re.escape(label)}' (\d+) симв\. не помещается .*, влезает ~(\d+)",
                                    self.message(exc, "связь a? -> b:")).group(2))
            cut_model = flow_model(nodes, ["a? b", "c ."], [f"a? -> b : {label[:budget]}", "a? -> c : вниз"])
            self.rerun_without(flow, cut_model, "связь a? -> b: подпись")

        # site 4b: flow.py edge label, wide latin glyphs
        with self.subTest(site="flow edge label wide glyphs"):
            nodes = [{"id": "a?", "title": "Да?"}, {"id": "b", "kind": "terminal", "title": "B"},
                     {"id": "c", "kind": "terminal", "title": "C"}]
            label = "ШШШ"
            model = flow_model(nodes, ["a? b", "c ."], [f"a? -> b : {label}", "a? -> c : вниз"])
            exc = self.failure(flow, model)
            budget = int(re.search(fr"подпись '{re.escape(label)}' (\d+) симв\. не помещается .*, влезает ~(\d+)",
                                    self.message(exc, "связь a? -> b:")).group(2))
            cut_model = flow_model(nodes, ["a? b", "c ."], [f"a? -> b : {label[:budget]}", "a? -> c : вниз"])
            self.rerun_without(flow, cut_model, "связь a? -> b: подпись")

        # site 5: timeline.py title
        with self.subTest(site="timeline title"):
            title = ("Заголовок момента " * 5).strip()
            text = "слово " * 60
            model = {"kind": "timeline", "entities": [{"id": "e", "label": "e"}],
                     "moments": [{"id": "m1", "label": "t1", "title": title, "text": text, "states": {"e": "x"}},
                                 {"id": "m2", "label": "t2", "title": "ок", "states": {"e": "y"}}]}
            exc = self.failure(timeline, model)
            titles = [e for e in exc.errors if "заголовок" in e]
            budget = int(re.search(r"заголовок (\d+) симв\., влезает (\d+)", titles[0]).group(2))
            model["moments"][0]["title"] = title[:budget]
            errors = self.rerun_without(timeline, model, "момент m1: заголовок")
            self.assertGone(errors, "момент m1: заголовок")

        # site 6: timeline.py text
        with self.subTest(site="timeline text"):
            title = ("Заголовок момента " * 5).strip()
            text = "слово " * 60
            model = {"kind": "timeline", "entities": [{"id": "e", "label": "e"}],
                     "moments": [{"id": "m1", "label": "t1", "title": title, "text": text, "states": {"e": "x"}},
                                 {"id": "m2", "label": "t2", "title": "ок", "states": {"e": "y"}}]}
            exc = self.failure(timeline, model)
            texts = [e for e in exc.errors if "текст" in e]
            budget = int(re.search(r"текст (\d+) симв\., в две строки влезает ~(\d+)", texts[0]).group(2))
            model["moments"][0]["text"] = text[:budget]
            errors = self.rerun_without(timeline, model, "момент m1: текст")
            self.assertGone(errors, "момент m1: текст")

        # site 7: schema.py key row
        with self.subTest(site="schema key row"):
            name = "external_correlation_identifier"
            tables = [{"id": "t", "name": "t", "group": "g",
                       "columns": [{"name": name, "type": "uuid", "flags": ["PK"]}]}]
            tables += [{"id": x, "name": x, "group": "g", "columns": [{"name": "id", "flags": ["PK"]}]} for x in "uv"]
            _, warnings = schema.plan({"kind": "schema", "groups": {"g": {"label": "g", "ramp": "teal"}},
                                       "tables": tables, "grid": ["t u v"]}, "widget")
            msg = next(w for w in warnings if w.startswith(f"таблица t.{name}:"))
            budget = int(re.search(r"имя (\d+) симв\., влезает ~(\d+)", msg).group(2))
            tables2 = [{"id": "t", "name": "t", "group": "g",
                        "columns": [{"name": name[:budget], "type": "uuid", "flags": ["PK"]}]}]
            tables2 += [{"id": x, "name": x, "group": "g", "columns": [{"name": "id", "flags": ["PK"]}]}
                        for x in "uv"]
            _, warnings2 = schema.plan({"kind": "schema", "groups": {"g": {"label": "g", "ramp": "teal"}},
                                        "tables": tables2, "grid": ["t u v"]}, "widget")
            still = [w for w in warnings2 if w.startswith("таблица t.") and re.search(r"имя \d+ симв\.", w)]
            self.assertFalse(still, f"budget message still present after cut: {still}")


if __name__ == "__main__":
    unittest.main()
