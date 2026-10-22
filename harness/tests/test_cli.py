import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from qed.cli import main

PROBLEMS = Path(__file__).resolve().parent.parent / "problems"


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        status = main(list(argv))
    return status, out.getvalue()


class CliTest(unittest.TestCase):
    def test_catalog_and_map(self):
        status, out = run("catalog", "--formalized")
        self.assertEqual(status, 0)
        self.assertIn("235 of 372 families", out)
        status, out = run("map", "--json")
        rows = json.loads(out)
        self.assertEqual(len(rows), 372)
        self.assertEqual({r["family"] for r in rows if r["readiness"] == "R3"}, {"076", "102", "131", "165", "179"})

    def test_require_gates_on_evidence(self):
        self.assertEqual(run("app", "crossbar", "--m", "4", "--n", "5", "--require", "formalized")[0], 0)
        self.assertEqual(run("app", "crossbar", "--m", "4", "--n", "5", "--require", "verified")[0], 2)

    def test_app_writes_reports(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(run("app", "crossbar", "--m", "3", "--n", "4", "--out", out)[0], 0)
            for name in ("report.md", "report.json", "crossbar-3x4.svg"):
                self.assertTrue((Path(out) / name).is_file(), name)

    def test_solve_exit_status(self):
        with tempfile.TemporaryDirectory() as runs:
            replay = PROBLEMS / "replays" / "psl2-length-28.json"
            status, out = run("solve", str(PROBLEMS / "psl2-length-28.toml"), "--provider", f"scripted:{replay}",
                              "--samples", "2", "--rounds", "1", "--workers", "1", "--runs-dir", runs)
            self.assertEqual(status, 0, out)
            status, _ = run("solve", str(PROBLEMS / "low-psl-code-64.toml"), "--provider",
                            f"scripted:{PROBLEMS / 'replays' / 'low-psl-code-64.json'}", "--samples", "1",
                            "--rounds", "1", "--runs-dir", runs)
            self.assertEqual(status, 3)  # the candidate is a program and --exec was not given

    def test_errors_exit_1(self):
        self.assertEqual(run("show", "999")[0], 1)
        self.assertEqual(run("kit", "check", "nope")[0], 1)


if __name__ == "__main__":
    unittest.main()
