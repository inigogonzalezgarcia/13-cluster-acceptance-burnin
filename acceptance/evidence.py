"""Parsers for the evidence collected from each node and rack.

Formats:
- inventory.json   one per node: GPUs, driver, VBIOS, InfiniBand ports (lab format, see docs/evidence.md)
- dcgm-diag.json   output of `dcgmi diag -r 3 -j`. The parser walks the document for `test_categories`
                   -> `tests` -> `results` and reads a status per GPU, so it tolerates the field-name
                   differences between DCGM versions. Tested only against the lab samples.
- nccl-*.txt       stdout of nccl-tests (`all_reduce_perf`): the results table and the
                   `# Avg bus bandwidth` line.
- burnin.jsonl     hourly per-GPU telemetry during burn-in (lab format)
- burnin-job.jsonl event log of the cluster-wide burn-in job, same format as repo 12 (gpu-goodput-mtbi)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# --- DCGM diagnostics ----------------------------------------------------------------------------

STATUS = {"pass": "pass", "passed": "pass", "fail": "fail", "failed": "fail", "warn": "warn", "warning": "warn",
          "skip": "skip", "skipped": "skip", "not run": "skip", "notrun": "skip"}


@dataclass
class DiagResult:
    test: str
    gpu: int | None  # None: applies to the whole node
    status: str  # pass / fail / warn / skip
    message: str = ""


def parse_dcgm_diag(doc: dict) -> list[DiagResult]:
    cats = _find(doc, "test_categories")
    if cats is None:
        raise ValueError("no test_categories in the DCGM diagnostic output")
    out = []
    for cat in cats:
        for test in cat.get("tests", []):
            name = str(test.get("name", "?"))
            for r in test.get("results", []):
                status = STATUS.get(str(r.get("status", "")).strip().lower())
                if status is None:
                    raise ValueError(f"test {name}: unknown status {r.get('status')!r}")
                gpu = r.get("gpu_id", r.get("entity_id"))
                msgs = [w.get("warning", "") if isinstance(w, dict) else str(w) for w in r.get("warnings", [])]
                out.append(DiagResult(name, int(gpu) if gpu not in (None, "") else None, status, "; ".join(m for m in msgs if m)))
    return out


def _find(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find(v, key)
            if found is not None:
                return found
    return None


# --- nccl-tests ----------------------------------------------------------------------------------

@dataclass
class NcclResult:
    ranks: int
    hosts: list[str]
    rows: list[dict]  # size, busbw (out-of-place), wrong
    avg_busbw: float | None

    @property
    def peak_busbw(self) -> float:
        return max((r["busbw"] for r in self.rows), default=0.0)

    @property
    def largest_busbw(self) -> float:
        """Bus bandwidth at the largest message size: the number to compare with a target."""
        return max(self.rows, key=lambda r: r["size"])["busbw"] if self.rows else 0.0

    @property
    def wrong(self) -> int:
        return sum(r["wrong"] for r in self.rows)


_ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+\w+\s+\w+\s+-?\d+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+|N/A)\s+"
                  r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+|N/A)\s*$")
_RANK = re.compile(r"^#\s+Rank\s+\d+\s+Group\s+\d+\s+Pid\s+\d+\s+on\s+(\S+)\s+device")
_AVG = re.compile(r"^#\s*Avg bus bandwidth\s*:\s*([\d.]+)")


def parse_nccl(text: str) -> NcclResult:
    rows, hosts, ranks, avg = [], [], 0, None
    for line in text.splitlines():
        if m := _RANK.match(line):
            ranks += 1
            if m.group(1) not in hosts:
                hosts.append(m.group(1))
        elif m := _AVG.match(line):
            avg = float(m.group(1))
        elif m := _ROW.match(line):
            wrong = 0 if m.group(6) == "N/A" else int(m.group(6))
            wrong += 0 if m.group(10) == "N/A" else int(m.group(10))
            rows.append({"size": int(m.group(1)), "busbw": float(m.group(5)), "wrong": wrong})
    if not rows:
        raise ValueError("no result rows found in the nccl-tests output")
    return NcclResult(ranks, hosts, rows, avg)


# --- burn-in -------------------------------------------------------------------------------------

@dataclass
class BurninSummary:
    hours: int
    max_temp_c: float
    throttle_fraction: float  # share of GPU-time with thermal throttling
    dbe: int
    sbe_max_per_gpu: int
    xids: list[tuple[int, int, int]] = field(default_factory=list)  # (hour, gpu, xid)
    iterations: int = 0
    failures: int = 0

    @property
    def pass_rate(self) -> float:
        return 1 - self.failures / self.iterations if self.iterations else 0.0


def summarize_burnin(lines) -> BurninSummary:
    hours, temps, throttle, gpu_hours, dbe, sbe, xids, it, fail = set(), [], 0.0, 0, 0, {}, [], 0, 0
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            h, g = int(d["hour"]), int(d["gpu"])
        except (ValueError, KeyError) as e:
            raise ValueError(f"burn-in line {n}: {e}") from None
        hours.add(h)
        gpu_hours += 1
        temps.append(float(d.get("max_temp_c", 0)))
        throttle += float(d.get("thermal_throttle_s", 0)) / 3600
        dbe += int(d.get("dbe", 0))
        sbe[g] = sbe.get(g, 0) + int(d.get("sbe", 0))
        xids += [(h, g, int(x)) for x in d.get("xid", [])]
        it += int(d.get("iterations", 0))
        fail += int(d.get("failures", 0))
    return BurninSummary(len(hours), max(temps, default=0), throttle / gpu_hours if gpu_hours else 0.0, dbe,
                         max(sbe.values(), default=0), sorted(xids), it, fail)


@dataclass
class JobSummary:
    hours: float
    interruptions: list[tuple[str, str, str | None]]  # (time, cause, node)
    goodput: float

    @property
    def mtbi_hours(self) -> float | None:
        return self.hours / len(self.interruptions) if self.interruptions else None


def summarize_job(lines) -> JobSummary:
    """Goodput and interruptions of the burn-in job. Same rules as repo 12: compute is productive once a
    checkpoint saves it (or the log ends); everything else is checkpoint, lost, detection or restart time."""
    evs = []
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if line and not line.startswith("#"):
            try:
                d = json.loads(line)
                evs.append((datetime.fromisoformat(d["time"].replace("Z", "+00:00")), d["event"], d))
            except (ValueError, KeyError) as e:
                raise ValueError(f"job log line {n}: {e}") from None
    if not evs or evs[0][1] != "start" or evs[-1][1] != "end":
        raise ValueError("job log must start with 'start' and end with 'end'")
    productive, pending, interruptions = 0.0, 0.0, []
    state, last = "compute", evs[0][0]
    for t, ev, d in evs[1:]:
        dt = (t - last).total_seconds() / 3600
        if state == "compute":
            pending += dt
        last = t
        if ev == "checkpoint_start":
            state = "checkpoint"
        elif ev == "checkpoint_end":
            productive, pending, state = productive + pending, 0.0, "compute"
        elif ev == "interrupt":
            interruptions.append((d["time"], d.get("cause", "unknown"), d.get("node")))
            pending, state = 0.0, "down"
        elif ev == "running":
            state = "compute"
        elif ev == "end":
            productive += pending
    total = (evs[-1][0] - evs[0][0]).total_seconds() / 3600
    return JobSummary(total, interruptions, productive / total if total else 0.0)


# --- loading a whole evidence directory ----------------------------------------------------------

@dataclass
class NodeEvidence:
    name: str
    rack: str
    inventory: dict | None = None
    diag: list[DiagResult] | None = None
    nccl: NcclResult | None = None
    burnin: BurninSummary | None = None


@dataclass
class Evidence:
    nodes: dict[str, NodeEvidence]
    racks: dict[str, NcclResult | None]
    job: JobSummary | None


def load(root: str | Path) -> Evidence:
    root = Path(root)
    nodes: dict[str, NodeEvidence] = {}
    for d in sorted((root / "nodes").glob("*")):
        if not d.is_dir():
            continue
        inv = _json(d / "inventory.json")
        ne = NodeEvidence(d.name, (inv or {}).get("rack", d.name.split("-")[0]), inv)
        if (p := d / "dcgm-diag.json").exists():
            ne.diag = parse_dcgm_diag(_json(p))
        if (p := d / "nccl-allreduce.txt").exists():
            ne.nccl = parse_nccl(p.read_text())
        if (p := d / "burnin.jsonl").exists():
            ne.burnin = summarize_burnin(p.read_text().splitlines())
        nodes[d.name] = ne
    if not nodes:
        raise ValueError(f"no node evidence under {root / 'nodes'}")
    racks = {}
    for rack in sorted({n.rack for n in nodes.values()}):
        p = root / "racks" / rack / "nccl-allreduce.txt"
        racks[rack] = parse_nccl(p.read_text()) if p.exists() else None
    p = root / "burnin-job.jsonl"
    job = summarize_job(p.read_text().splitlines()) if p.exists() else None
    return Evidence(nodes, racks, job)


def load_rounds(roots) -> tuple[Evidence, list[dict]]:
    """Load several test rounds. A later round replaces everything earlier rounds had for the same
    node or rack, and its burn-in job replaces the earlier one: a retest supersedes the old result."""
    merged, manifests = None, []
    for root in roots:
        ev = load(root)
        manifests.append(_json(Path(root) / "manifest.json") or {"round": len(manifests) + 1, "path": str(root)})
        if merged is None:
            merged = ev
            continue
        merged.nodes.update(ev.nodes)
        for rack, res in ev.racks.items():
            if res is not None or rack not in merged.racks:
                merged.racks[rack] = res
        if ev.job is not None:
            merged.job = ev.job
    if merged is None:
        raise ValueError("no evidence directories given")
    return merged, manifests


def _json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"{p}: {e}") from None
