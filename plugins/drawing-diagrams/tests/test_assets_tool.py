import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import support  # noqa: F401
import assets as tool
from diagrams import assets


class AssetsTool(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dist = Path(tmp.name)
        patcher = mock.patch.object(assets, "DIST", self.dist)
        patcher.start()
        self.addCleanup(patcher.stop)

    def quiet(self, fn, *args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            code = fn(*args)
        return code, err.getvalue()

    def test_check_passes_after_build_and_fails_after_a_change(self):
        self.assertEqual(self.quiet(tool.build)[0], 0)
        self.assertEqual(self.quiet(tool.check)[0], 0)
        (self.dist / "dg.js").write_text("changed")
        code, err = self.quiet(tool.check)
        self.assertEqual(code, 1)
        self.assertIn("dg.js", err)

    def test_verify_cdn_compares_bytes_at_ref(self):
        self.quiet(tool.build)
        (self.dist / "REF").write_text("b" * 40 + "\n")
        local = {name: (self.dist / name).read_bytes() for name in tool.FILES}
        seen = []

        def good(url):
            seen.append(url)
            return 200, local[url.rsplit("/", 1)[1]]

        self.assertEqual(self.quiet(tool.verify_cdn, good)[0], 0)
        self.assertTrue(all("@" + "b" * 40 + "/" in url for url in seen))
        self.assertEqual(self.quiet(tool.verify_cdn, lambda url: (200, b"other"))[0], 1)
        self.assertEqual(self.quiet(tool.verify_cdn, lambda url: (404, b""))[0], 1)

    def test_verify_cdn_needs_ref(self):
        self.quiet(tool.build)
        code, err = self.quiet(tool.verify_cdn, lambda url: (200, b""))
        self.assertEqual(code, 1)
        self.assertIn("REF", err)


class ShippedDist(unittest.TestCase):
    """The shipped build, not a temporary one: template/dist is what jsDelivr serves, and a widget
    links to it instead of carrying the fragments, so a change under template/css or template/js
    that skips the rebuild publishes assets its sources no longer describe."""

    def test_dist_matches_a_fresh_build(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            code = tool.check()
        self.assertEqual(code, 0, err.getvalue())


if __name__ == "__main__":
    unittest.main()
