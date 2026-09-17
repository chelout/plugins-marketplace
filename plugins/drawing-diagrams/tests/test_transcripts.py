import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import support  # noqa: F401
import transcripts


def assistant(mid, usage, effort="xhigh", model="claude-opus-5", content=None):
    return {"type": "assistant", "effort": effort,
            "message": {"id": mid, "model": model, "usage": usage, "content": content or []}}


def write(path, recs):
    # Claude Code writes compact JSON; the readers prefilter on '"type":"assistant"'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in recs) + "\n")


class RunMetrics(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.session = root / "run.jsonl"
        render = {"type": "tool_use", "id": "t1", "name": "Bash",
                  "input": {"command": "python3 /x/skills/drawing-diagrams/render.py m.json --mode widget"}}
        write(self.session, [
            # one message written as two records; the first carries a partial usage
            assistant("m1", {"input_tokens": 2, "output_tokens": 2, "cache_creation_input_tokens": 100}),
            assistant("m1", {"input_tokens": 2, "output_tokens": 150, "cache_creation_input_tokens": 100,
                             "cache_read_input_tokens": 1000, "output_tokens_details": {"thinking_tokens": 40},
                             "iterations": [{"input_tokens": 2, "output_tokens": 150, "cache_read_input_tokens": 1000,
                                             "cache_creation_input_tokens": 100}]},
                      effort="high", content=[render]),
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True,
                                                      "content": "Exit code 1\nошибка: узел a: заголовок 30 симв., влезает 19"}]}},
            # zeros at the top level, the real numbers only in iterations
            assistant("m2", {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                             "cache_creation_input_tokens": 0, "cache_creation": {"ephemeral_1h_input_tokens": 275},
                             "iterations": [{"input_tokens": 2, "output_tokens": 327, "cache_read_input_tokens": 988169,
                                             "cache_creation_input_tokens": 275}]}),
            assistant("m3", {"input_tokens": 0, "output_tokens": 0}, model="<synthetic>"),
        ])
        write(root / "run" / "subagents" / "agent-a1.jsonl", [
            assistant("s1", {"input_tokens": 3, "output_tokens": 50, "cache_read_input_tokens": 500},
                      effort="medium", model="claude-sonnet-5"),
        ])

    def test_counts_each_message_once_and_sums_iterations(self):
        calls = transcripts.api_calls(str(self.session))
        self.assertEqual([c["out"] for c in calls], [150, 327])
        self.assertEqual(calls[0]["think"], 40)
        self.assertEqual(calls[0]["ctx"], 2 + 100 + 1000)
        self.assertEqual(calls[0]["effort"], "high")
        self.assertEqual((calls[1]["cr"], calls[1]["cw"]), (988169, 275))

    def test_run_metrics_include_subagents_and_render_failures(self):
        m = transcripts.run_metrics(str(self.session))
        self.assertEqual((m["calls"], m["agents"]), (3, 1))
        self.assertEqual(m["out"], 150 + 327 + 50)
        self.assertEqual(m["peak_ctx"], 2 + 275 + 988169)
        self.assertEqual((m["renders"], m["renders_failed"]), (1, 1))
        self.assertEqual(dict(m["efforts"]), {"high": 1, "xhigh": 1, "medium": 1})
        self.assertEqual(dict(m["models"]), {"claude-opus-5": 2, "claude-sonnet-5": 1})

    def test_tokens_command_prints_one_line_per_run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = transcripts.main(["tokens", str(self.session)])
        self.assertEqual(code, 0)
        line = out.getvalue().strip().splitlines()[-1]
        self.assertIn("run.jsonl", line)
        self.assertIn("out=527", line)
        self.assertIn("renders=1/1", line)
        self.assertIn("mentions=1", line)

    def test_run_metrics_counts_mentions_within_a_compound_render_call(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        session = Path(tmp.name) / "compound.jsonl"
        compound = {"type": "tool_use", "id": "c1", "name": "Bash",
                    "input": {"command": "python3 /x/skills/drawing-diagrams/render.py a.json && "
                                          "python3 /x/skills/drawing-diagrams/render.py b.json"}}
        single = {"type": "tool_use", "id": "c2", "name": "Bash",
                  "input": {"command": "python3 /x/skills/drawing-diagrams/render.py c.json --mode widget"}}
        # a shell loop mentions render.py once in the command text but runs it three times; the
        # transcript cannot see the real execution count, so it must count as 1 mention, 1 call
        loop = {"type": "tool_use", "id": "c3", "name": "Bash",
                "input": {"command": 'for m in a b c; do python3 /x/skills/drawing-diagrams/render.py "$m.json"; done'}}
        write(session, [
            assistant("m1", {"input_tokens": 1, "output_tokens": 1}, content=[compound]),
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "c1", "is_error": True,
                                                      "content": "Exit code 1\nошибка: узел a: заголовок 30 симв., влезает 19"}]}},
            assistant("m2", {"input_tokens": 1, "output_tokens": 1}, content=[single]),
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "c2", "is_error": False,
                                                      "content": "OK"}]}},
            assistant("m3", {"input_tokens": 1, "output_tokens": 1}, content=[loop]),
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "c3", "is_error": False,
                                                      "content": "OK"}]}},
        ])
        renders = transcripts.render_commands(str(session))
        self.assertEqual(renders[2]["mentions"], 1)
        m = transcripts.run_metrics(str(session))
        self.assertEqual(m["renders"], 3)
        self.assertEqual(m["render_mentions"], 4)
        self.assertEqual(m["renders_failed"], 1)


class ShortProject(unittest.TestCase):
    def test_derives_encoding_from_home_instead_of_a_hardcoded_user(self):
        with mock.patch.object(transcripts, "HOME", "/home/alice"), \
             mock.patch.object(transcripts, "PROJECTS", "/home/alice/.claude/projects"):
            sub = "/home/alice/.claude/projects/-home-alice-work-myproj/session.jsonl"
            self.assertEqual(transcripts.short_project(sub), "work-myproj")
            bare = "/home/alice/.claude/projects/-home-alice/session.jsonl"
            self.assertEqual(transcripts.short_project(bare), "~")

    def test_scratch_workspaces_still_collapse(self):
        with mock.patch.object(transcripts, "HOME", "/home/alice"), \
             mock.patch.object(transcripts, "PROJECTS", "/home/alice/.claude/projects"):
            path = "/home/alice/.claude/projects/-home-alice-scratch-workspaces-xyz/session.jsonl"
            self.assertEqual(transcripts.short_project(path), "scratch")


class RunFiles(unittest.TestCase):
    def test_rejects_a_session_path_without_the_jsonl_suffix(self):
        with self.assertRaises(ValueError) as ctx:
            transcripts.run_files("/tmp/run.json")
        self.assertIn("/tmp/run.json", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
