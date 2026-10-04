"""The lab cluster: round 1 finds every planted defect, round 2 reaches handover."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from acceptance import checks, evidence, sim
from acceptance.cli import main
from tests.helpers import BASE, ROOT

EXPECTED_ROUND1 = {
    "r01-n03": ("RETEST", "inventory"), "r01-n08": ("REJECTED", "burnin"),
    "r02-n01": ("ACCEPTED_WITH_OBSERVATIONS", "burnin"), "r02-n05": ("REJECTED", "diag"),
    "r02-n07": ("REJECTED", "inventory"), "r03-n02": ("RETEST", "nccl-node"),
    "r03-n06": ("RETEST", "burnin"), "r04-n06": ("RETEST", "nccl-node"),
}


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


class LabCluster(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)
        sim.generate(cls.d / "round1", 1)
        sim.generate(cls.d / "round2", 2)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_round1_finds_every_defect(self):
        r = checks.evaluate(evidence.load(self.d / "round1"), BASE)
        got = {n.name: (n.status, n.reached) for n in r.nodes}
        for name, want in EXPECTED_ROUND1.items():
            self.assertEqual(got[name], want, name)
        others = [n for n in r.nodes if n.name not in EXPECTED_ROUND1]
        self.assertTrue(all(n.status == "ACCEPTED" for n in others if not n.name.startswith("r04")))
        self.assertTrue(all(n.status == "RETEST" for n in others if n.name.startswith("r04")))
        self.assertEqual(r.accepted_gpus, 144)
        self.assertFalse(r.handover_ready)
        self.assertEqual([k.passed for k in r.racks], [True, True, True, False])

    def test_round2_reaches_handover(self):
        ev, manifests = evidence.load_rounds([self.d / "round1", self.d / "round2"])
        r = checks.evaluate(ev, BASE)
        self.assertTrue(r.handover_ready)
        self.assertEqual(r.accepted_gpus, 248)
        self.assertEqual([m["round"] for m in manifests], [1, 2])
        self.assertEqual({n.name for n in r.nodes if not n.accepted}, {"r02-n05"})
        self.assertAlmostEqual(r.job["mtbi_hours"], 36)

    def test_cli(self):
        out = self.d / "report"
        code, stdout, _ = run("evaluate", str(self.d / "round1"), "--criteria", str(ROOT / "criteria.toml"), "--out-dir", str(out))
        self.assertEqual(code, 1)
        self.assertIn("NOT READY", stdout)
        md = (out / "report.md").read_text()
        self.assertIn("Verdict: NOT READY FOR HANDOVER", md)
        self.assertIn("rack r04", (out / "punch-list.csv").read_text())
        self.assertIn("NOT READY FOR HANDOVER", (out / "report.html").read_text())
        self.assertEqual(json.loads((out / "result.json").read_text())["accepted_gpus"], 144)
        code, stdout, _ = run("evaluate", str(self.d / "round1"), str(self.d / "round2"), "--criteria", str(ROOT / "criteria.toml"))
        self.assertEqual(code, 0)
        self.assertIn("READY for handover, 248/256", stdout)

    def test_plan_and_errors(self):
        hosts = self.d / "hosts.txt"
        hosts.write_text("# lab\nr01-n01\nr01-n02\nr02-n01\n")
        code, stdout, _ = run("plan", str(hosts), "--criteria", str(ROOT / "criteria.toml"))
        self.assertEqual(code, 0)
        self.assertIn("dcgmi diag -r 3 -j", stdout)
        self.assertIn("mpirun -np 16 -H r01-n01:8,r01-n02:8", stdout)
        code, _, err = run("evaluate", str(self.d / "missing"), "--criteria", str(ROOT / "criteria.toml"))
        self.assertEqual(code, 2)
        self.assertIn("no node evidence", err)


if __name__ == "__main__":
    unittest.main()


class SampleReports(unittest.TestCase):
    """docs/sample-report-round*.md are generated; this fails if the code no longer produces them."""

    def test_committed_samples_are_current(self):
        from acceptance import report
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            sim.generate(d / "round1", 1)
            sim.generate(d / "round2", 2)
            for rounds, name in (([d / "round1"], "sample-report-round1.md"),
                                 ([d / "round1", d / "round2"], "sample-report-round2.md")):
                ev, manifests = evidence.load_rounds(rounds)
                md = report.markdown(checks.evaluate(ev, BASE), BASE, manifests)
                self.assertEqual(md, (ROOT / "docs" / name).read_text(), f"regenerate docs/{name} (see docs/evidence.md)")
