import copy
from pathlib import Path

from acceptance import criteria
from acceptance.evidence import BurninSummary, DiagResult, Evidence, NcclResult, NodeEvidence

ROOT = Path(__file__).parent.parent
BASE = criteria.load(ROOT / "criteria.toml")


def crit(**overrides):
    """The repo's criteria with some values replaced: crit(**{"nccl.rack.min_nodes": 2})."""
    raw = copy.deepcopy(BASE.raw)
    for key, value in overrides.items():
        *path, last = key.split(".")
        d = raw
        for p in path:
            d = d[p]
        d[last] = value
    return criteria.Criteria(raw)


def inventory(name, gpus=8, vbios="LAB-96.00.A1", symbol_errors=0):
    return {"hostname": name, "rack": name[:3], "driver_version": "lab-570.1",
            "gpus": [{"index": i, "model": "LAB-GPU-80GB", "vbios": vbios} for i in range(gpus)],
            "ib_ports": [{"name": f"mlx5_{i}", "state": "Active", "rate_gbps": 400,
                          "symbol_errors": symbol_errors if i == 0 else 0, "link_downed": 0} for i in range(8)]}


def diag_ok():
    tests = ["Software", "PCIe", "Memory", "Memory Bandwidth", "Diagnostic", "Targeted Stress", "Targeted Power"]
    return [DiagResult(t, g, "pass") for t in tests for g in range(8)]


def nccl(busbw, hosts=("x",), ranks=8, wrong=0):
    return NcclResult(ranks, list(hosts), [{"size": 8, "busbw": 0.0, "wrong": 0},
                                           {"size": 8 << 30, "busbw": busbw, "wrong": wrong}], busbw / 2)


def burnin(**kw):
    d = dict(hours=72, max_temp_c=75, throttle_fraction=0.0, dbe=0, sbe_max_per_gpu=0, xids=[], iterations=1000, failures=0)
    d.update(kw)
    return BurninSummary(**d)


def good_node(name):
    return NodeEvidence(name, name[:3], inventory(name), diag_ok(), nccl(470), burnin())


def evidence(nodes, rack_busbw=360.0, job=None):
    from acceptance.evidence import JobSummary
    racks = {}
    for n in nodes:
        racks.setdefault(n.rack, []).append(n.name)
    return Evidence({n.name: n for n in nodes},
                    {r: nccl(rack_busbw, hosts=members, ranks=8 * len(members)) for r, members in racks.items()},
                    job or JobSummary(72, [("t", "software_crash", None)], 0.95))
