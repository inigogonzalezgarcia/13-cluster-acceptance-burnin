import unittest

from acceptance import checks
from acceptance.evidence import DiagResult, JobSummary
from tests.helpers import burnin, crit, evidence, good_node, inventory, nccl

C = crit(**{"nccl.rack.min_nodes": 2, "cluster.min_accepted_gpu_fraction": 0.5})


def status(result, name):
    return next(n for n in result.nodes if n.name == name)


class Stages(unittest.TestCase):
    def test_all_good(self):
        r = checks.evaluate(evidence([good_node("r01-n01"), good_node("r01-n02")]), C)
        self.assertTrue(r.handover_ready)
        self.assertEqual({n.status for n in r.nodes}, {"ACCEPTED"})
        self.assertEqual(r.accepted_gpus, 16)

    def test_failure_stops_later_stages(self):
        n = good_node("r01-n01")
        n.inventory = inventory("r01-n01", vbios="OLD")
        n.diag = [DiagResult("Memory", 0, "fail")]
        r = checks.evaluate(evidence([n, good_node("r01-n02")]), C)
        node = status(r, "r01-n01")
        self.assertEqual(node.status, "RETEST")  # firmware, not RMA: diag never ran
        self.assertEqual(node.reached, "inventory")
        self.assertFalse(any(f.stage == "diag" for f in node.findings))

    def test_diag_fail_is_rma_and_missing_test_is_collect(self):
        n = good_node("r01-n01")
        n.diag = [d for d in n.diag if d.test != "PCIe"] + [DiagResult("Memory", 3, "fail", "DBE")]
        node = status(checks.evaluate(evidence([n, good_node("r01-n02")]), C), "r01-n01")
        self.assertEqual(node.status, "REJECTED")
        self.assertEqual({f.disposition for f in node.findings if f.severity == "fail"}, {"rma", "collect"})

    def test_warn_policy(self):
        n = good_node("r01-n01")
        n.diag = n.diag + [DiagResult("Diagnostic", 2, "warn", "clocks")]
        ok = status(checks.evaluate(evidence([n, good_node("r01-n02")]), C), "r01-n01")
        self.assertEqual(ok.status, "ACCEPTED_WITH_OBSERVATIONS")
        strict = crit(**{"nccl.rack.min_nodes": 2, "diag.warn_counts_as_pass": False})
        self.assertEqual(status(checks.evaluate(evidence([n, good_node("r01-n02")]), strict), "r01-n01").status, "RETEST")

    def test_nccl(self):
        slow, corrupt = good_node("r01-n01"), good_node("r01-n02")
        slow.nccl = nccl(300)
        corrupt.nccl = nccl(470, wrong=1)
        r = checks.evaluate(evidence([slow, corrupt, good_node("r01-n03")]), C)
        self.assertEqual(status(r, "r01-n01").status, "RETEST")
        self.assertEqual(status(r, "r01-n02").status, "REJECTED")

    def test_burnin_rules(self):
        cases = {
            "r01-n01": (burnin(xids=[(30, 5, 79)]), "REJECTED"),
            "r01-n02": (burnin(xids=[(3, 1, 13)]), "ACCEPTED"),  # XID 13 is an application error, not hardware
            "r01-n03": (burnin(max_temp_c=92), "RETEST"),
            "r01-n04": (burnin(sbe_max_per_gpu=40), "ACCEPTED_WITH_OBSERVATIONS"),
            "r01-n05": (burnin(sbe_max_per_gpu=400), "REJECTED"),
            "r01-n06": (burnin(hours=48), "RETEST"),
            "r01-n07": (burnin(failures=20), "RETEST"),
        }
        nodes = []
        for name, (b, _) in cases.items():
            n = good_node(name)
            n.burnin = b
            nodes.append(n)
        r = checks.evaluate(evidence(nodes), C)
        for name, (_, want) in cases.items():
            self.assertEqual(status(r, name).status, want, name)


class RackAndCluster(unittest.TestCase):
    def test_rack_failure_blocks_burnin_and_points_at_ib_errors(self):
        bad = good_node("r01-n02")
        bad.inventory = inventory("r01-n02", symbol_errors=500)
        r = checks.evaluate(evidence([good_node("r01-n01"), bad], rack_busbw=200), C)
        self.assertFalse(r.racks[0].passed)
        self.assertEqual(status(r, "r01-n02").findings[-1].disposition, "fabric")
        self.assertEqual(status(r, "r01-n01").findings[-1].disposition, "rack")
        self.assertFalse(any(f.stage == "burnin" for n in r.nodes for f in n.findings))

    def test_too_few_nodes_for_the_rack_test(self):
        r = checks.evaluate(evidence([good_node("r01-n01")]), C)
        self.assertFalse(r.racks[0].passed)
        self.assertIn("only 1 node", r.racks[0].findings[0].message)

    def test_cluster_thresholds(self):
        nodes = [good_node("r01-n01"), good_node("r01-n02")]
        r = checks.evaluate(evidence(nodes, job=JobSummary(72, [("a", "x", None)] * 4, 0.95)), C)
        self.assertIn("MTBI 18.0 h", " ".join(f.message for f in r.findings))
        r = checks.evaluate(evidence(nodes, job=JobSummary(72, [], 0.80)), C)
        self.assertIn("goodput 80.0%", " ".join(f.message for f in r.findings))
        self.assertFalse(r.handover_ready)
        strict = crit(**{"nccl.rack.min_nodes": 2, "cluster.min_accepted_gpu_fraction": 1.0})
        nodes[0].burnin = burnin(dbe=1)
        r = checks.evaluate(evidence(nodes), strict)
        self.assertIn("8 of 16 GPUs accepted", r.findings[-1].message)


if __name__ == "__main__":
    unittest.main()
