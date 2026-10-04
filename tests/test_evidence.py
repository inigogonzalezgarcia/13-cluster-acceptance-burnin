import json
import unittest

from acceptance import evidence
from tests.helpers import ROOT

FIX = ROOT / "tests" / "fixtures"


class DCGM(unittest.TestCase):
    def test_v3_style(self):
        res = evidence.parse_dcgm_diag(json.loads((FIX / "dcgm-v3-style.json").read_text()))
        by = {(r.test, r.gpu): r for r in res}
        self.assertEqual(by[("Software", None)].status, "pass")
        self.assertEqual(by[("Memory", 1)].status, "fail")
        self.assertIn("uncorrectable", by[("Memory", 1)].message)
        self.assertEqual(by[("Diagnostic", 0)].status, "warn")
        self.assertEqual(by[("Diagnostic", 1)].status, "skip")

    def test_entity_style(self):
        res = evidence.parse_dcgm_diag(json.loads((FIX / "dcgm-entity-style.json").read_text()))
        self.assertEqual([(r.test, r.gpu, r.status) for r in res], [("memory", 0, "pass"), ("memory", 1, "pass")])

    def test_rejects_unknown_documents(self):
        with self.assertRaises(ValueError):
            evidence.parse_dcgm_diag({"something": "else"})
        with self.assertRaises(ValueError):
            evidence.parse_dcgm_diag({"test_categories": [{"tests": [{"name": "x", "results": [{"status": "Maybe"}]}]}]})


class NCCL(unittest.TestCase):
    def test_parse(self):
        r = evidence.parse_nccl((FIX / "nccl-2nodes.txt").read_text())
        self.assertEqual(r.ranks, 4)
        self.assertEqual(r.hosts, ["r09-n01", "r09-n02"])
        self.assertEqual(len(r.rows), 4)
        self.assertAlmostEqual(r.largest_busbw, 317.01)
        self.assertAlmostEqual(r.peak_busbw, 317.01)
        self.assertAlmostEqual(r.avg_busbw, 160.689)
        self.assertEqual(r.wrong, 2)  # the in-place column of the 256 MiB row; N/A counts as 0

    def test_no_rows(self):
        with self.assertRaises(ValueError):
            evidence.parse_nccl("# Avg bus bandwidth : 1.0\n")


class Burnin(unittest.TestCase):
    def test_summary(self):
        lines = [json.dumps({"hour": h, "gpu": g, "max_temp_c": 70 + g, "thermal_throttle_s": 360 if (h, g) == (0, 1) else 0,
                             "sbe": 1 if g == 1 else 0, "dbe": 0, "xid": [79] if (h, g) == (1, 0) else [],
                             "iterations": 10, "failures": 1 if (h, g) == (1, 0) else 0})
                 for h in range(2) for g in range(2)]
        s = evidence.summarize_burnin(lines)
        self.assertEqual(s.hours, 2)
        self.assertEqual(s.max_temp_c, 71)
        self.assertAlmostEqual(s.throttle_fraction, 0.1 / 4)
        self.assertEqual(s.sbe_max_per_gpu, 2)
        self.assertEqual(s.xids, [(1, 0, 79)])
        self.assertAlmostEqual(s.pass_rate, 1 - 1 / 40)

    def test_bad_line(self):
        with self.assertRaisesRegex(ValueError, "line 1"):
            evidence.summarize_burnin(['{"gpu": 0}'])


class Job(unittest.TestCase):
    def test_goodput_and_mtbi(self):
        def ev(h, m, event, **kw):
            return json.dumps({"time": f"2026-09-08T{h:02d}:{m:02d}:00Z", "job": "b", "event": event, **kw})
        lines = [ev(0, 0, "start"), ev(1, 0, "checkpoint_start"), ev(1, 6, "checkpoint_end"),
                 ev(1, 36, "interrupt", cause="gpu_xid79", node="r01-n08"), ev(1, 42, "detected"),
                 ev(1, 48, "nodes_ready"), ev(2, 0, "running"), ev(4, 0, "end")]
        j = evidence.summarize_job(lines)
        self.assertEqual(j.hours, 4)
        self.assertEqual(j.interruptions, [("2026-09-08T01:36:00Z", "gpu_xid79", "r01-n08")])
        self.assertEqual(j.mtbi_hours, 4)
        self.assertAlmostEqual(j.goodput, 3 / 4)  # 1 h saved by the checkpoint + 2 h until the end

    def test_must_start_and_end(self):
        with self.assertRaises(ValueError):
            evidence.summarize_job(['{"time": "2026-09-08T00:00:00Z", "event": "start"}'])


if __name__ == "__main__":
    unittest.main()
