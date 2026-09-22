"""Exact CLI regressions for every shipped example in both HTML modes.

Run from plugins/drawing-diagrams:
    python3 -m unittest discover -s tests -p test_examples.py

For an intentional output change, inspect the affected render's stdout/stderr:
    python3 skills/drawing-diagrams/render.py <example.json> --mode <mode> --assets none
Then explicitly update the fixture and review the resulting diff:
    python3 tests/test_examples.py --update-fixture
    git diff -- tests/models/shipped-examples.json

Hashes cover raw UTF-8 bytes, including IDs, label coordinates and warnings.
Only CSS/JS assets are excluded; their build and browser tests cover them.
Normal test runs never update the fixture.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import support

EXAMPLES = support.SKILL / "examples"
FIXTURE = Path(__file__).resolve().parent / "models" / "shipped-examples.json"
MODES = ("page", "widget")


def example_cases():
    return {
        f"{path.relative_to(EXAMPLES).as_posix()}:{mode}": (path, mode)
        for path in sorted(EXAMPLES.rglob("*.json"))
        for mode in MODES
    }


def render_record(path, mode):
    result = subprocess.run(
        [sys.executable, str(support.SKILL / "render.py"), str(path),
         "--mode", mode, "--assets", "none"],
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=30,
    )
    return {
        "exit_status": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
    }


class ShippedExamples(unittest.TestCase):
    def test_exact_cli_outputs(self):
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cases = example_cases()
        self.assertTrue(cases, "No shipped examples discovered")
        self.assertEqual(
            set(cases), set(expected),
            "Shipped example/mode set changed; review additions/removals before updating the fixture",
        )
        for key, (path, mode) in cases.items():
            actual = render_record(path, mode)
            with self.subTest(example=key, stream="record fields"):
                self.assertEqual(set(actual), set(expected[key]))
            for stream, value in actual.items():
                with self.subTest(example=path.relative_to(EXAMPLES).as_posix(),
                                  mode=mode, stream=stream):
                    self.assertEqual(value, expected[key][stream],
                                     f"{key} {stream} changed; inspect the exact CLI output")


if __name__ == "__main__":
    if sys.argv[1:] == ["--update-fixture"]:
        records = {key: render_record(path, mode)
                   for key, (path, mode) in example_cases().items()}
        if not records:
            raise SystemExit("No shipped examples discovered; fixture unchanged")
        FIXTURE.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
        print(f"Updated {FIXTURE}; review every changed record before accepting it.")
    else:
        unittest.main()
