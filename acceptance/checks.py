"""The acceptance rules. Stages run in order; a node that fails a stage is not tested further,
because a broken node only adds noise to later tests (and wastes hours of burn-in).

    1 inventory   GPU count and model, driver and VBIOS versions, InfiniBand ports and errors
    2 diag        dcgmi diag at the agreed level, every required test passes on every GPU
    3 nccl-node   all_reduce bus bandwidth across the node's GPUs (NVLink)
    4 nccl-rack   all_reduce across the accepted nodes of each rack (InfiniBand)
    5 burnin      multi-day burn-in: hardware XIDs, uncorrectable ECC, correctable ECC growth,
                  temperature and throttling, workload pass rate
    6 job         the cluster-wide burn-in job meets the agreed MTBI and goodput

Every failure carries a disposition, so the punch list says who acts next.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acceptance.criteria import Criteria
from acceptance.evidence import Evidence, NodeEvidence

STAGES = ("inventory", "diag", "nccl-node", "nccl-rack", "burnin")

# disposition -> owner and what has to happen before a retest
DISPOSITIONS = {
    "rma": ("Hardware vendor", "Replace the failed part, then rerun from stage 1"),
    "firmware": ("Platform team", "Flash the baseline version, then rerun from stage 1"),
    "fabric": ("Network team", "Check cable, optics and switch port, then rerun the rack test"),
    "facility": ("Data centre facilities", "Fix airflow or cooling, then rerun burn-in"),
    "investigate": ("Platform team", "Root-cause before deciding on RMA or retest"),
    "collect": ("Platform team", "Collect the missing evidence"),
    "rack": ("Network team", "Waits for its rack to pass the rack test (see the rack's line)"),
    "close": ("Provider project lead", "Close the items above, then run a retest round"),
}


@dataclass
class Finding:
    stage: str
    severity: str  # fail / warn / info
    message: str
    disposition: str = ""


@dataclass
class NodeResult:
    name: str
    rack: str
    gpus: int
    findings: list[Finding] = field(default_factory=list)
    reached: str = ""  # last stage evaluated

    @property
    def status(self) -> str:
        fails = [f for f in self.findings if f.severity == "fail"]
        if not fails:
            return "ACCEPTED_WITH_OBSERVATIONS" if any(f.severity == "warn" for f in self.findings) else "ACCEPTED"
        return "REJECTED" if any(f.disposition == "rma" for f in fails) else "RETEST"

    @property
    def accepted(self) -> bool:
        return self.status.startswith("ACCEPTED")


@dataclass
class RackResult:
    name: str
    nodes: list[str]
    accepted_nodes: list[str]
    findings: list[Finding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(f.severity == "fail" for f in self.findings)


@dataclass
class ClusterResult:
    name: str
    nodes: list[NodeResult]
    racks: list[RackResult]
    findings: list[Finding]
    contracted_gpus: int
    accepted_gpus: int
    job: dict | None

    @property
    def handover_ready(self) -> bool:
        return not any(f.severity == "fail" for f in self.findings)


def evaluate(ev: Evidence, c: Criteria) -> ClusterResult:
    gpn = c["inventory"]["gpus_per_node"]
    nodes = [NodeResult(n.name, n.rack, gpn) for n in ev.nodes.values()]
    by_name = {n.name: n for n in nodes}

    for n in nodes:
        e = ev.nodes[n.name]
        for stage, fn in (("inventory", _inventory), ("diag", _diag), ("nccl-node", _nccl_node)):
            n.reached = stage
            new = fn(e, c)
            n.findings += new
            if any(f.severity == "fail" for f in new):
                break

    racks = []
    for rack in sorted({n.rack for n in nodes}):
        members = [n for n in nodes if n.rack == rack]
        ok = [n.name for n in members if n.accepted]
        r = RackResult(rack, [n.name for n in members], ok)
        res = ev.racks.get(rack)
        rc = c["nccl"]["rack"]
        if len(ok) < rc["min_nodes"]:
            r.findings.append(Finding("nccl-rack", "fail", f"only {len(ok)} node(s) passed stages 1-3, "
                                      f"the rack test needs {rc['min_nodes']}", "investigate"))
        elif res is None:
            r.findings.append(Finding("nccl-rack", "fail", "no rack-level nccl-tests result", "collect"))
        else:
            r.findings += _nccl_check(res, rc["min_busbw_gbps"], "nccl-rack", "fabric")
            missing = sorted(set(ok) - set(res.hosts)) if res.hosts else []
            if missing:
                r.findings.append(Finding("nccl-rack", "warn", f"test did not include accepted node(s) {', '.join(missing)}"))
        if not r.passed:
            # Attribute a rack failure to nodes with InfiniBand errors, if the inventory shows any.
            for name in ok:
                inv = ev.nodes[name].inventory or {}
                bad = [p["name"] for p in inv.get("ib_ports", []) if p.get("symbol_errors", 0) or p.get("link_downed", 0)]
                if bad:
                    by_name[name].findings.append(Finding("nccl-rack", "fail", f"rack test failed; InfiniBand errors on "
                                                          f"{', '.join(bad)}", "fabric"))
        racks.append(r)

    passed_racks = {r.name for r in racks if r.passed}
    for n in nodes:
        if n.accepted and n.rack in passed_racks:
            n.reached = "burnin"
            n.findings += _burnin(ev.nodes[n.name], c)
        elif n.accepted:
            n.findings.append(Finding("nccl-rack", "fail", f"rack {n.rack} did not pass; node not burned in", "rack"))

    findings, job = [], None
    if ev.job is None:
        findings.append(Finding("job", "fail", "no burn-in job log", "collect"))
    else:
        jc = c["burnin"]["job"]
        job = {"hours": ev.job.hours, "interruptions": len(ev.job.interruptions), "mtbi_hours": ev.job.mtbi_hours,
               "goodput": ev.job.goodput, "events": ev.job.interruptions}
        if ev.job.hours < c["burnin"]["hours"]:
            findings.append(Finding("job", "fail", f"burn-in job ran {ev.job.hours:.0f} h, {c['burnin']['hours']} h agreed", "investigate"))
        if ev.job.mtbi_hours is not None and ev.job.mtbi_hours < jc["min_mtbi_hours"]:
            findings.append(Finding("job", "fail", f"job MTBI {ev.job.mtbi_hours:.1f} h, target {jc['min_mtbi_hours']} h", "investigate"))
        if ev.job.goodput < jc["min_goodput"]:
            findings.append(Finding("job", "fail", f"job goodput {ev.job.goodput:.1%}, target {jc['min_goodput']:.0%}", "investigate"))

    contracted = len(nodes) * gpn
    accepted = sum(n.gpus for n in nodes if n.accepted)
    need = c["cluster"]["min_accepted_gpu_fraction"]
    if accepted < need * contracted:
        findings.append(Finding("cluster", "fail", f"{accepted} of {contracted} GPUs accepted, "
                                f"{need:.0%} ({need * contracted:.0f}) needed", "close"))
    return ClusterResult(c["cluster"]["name"], nodes, racks, findings, contracted, accepted, job)


def _inventory(e: NodeEvidence, c: Criteria) -> list[Finding]:
    ic, inv, out = c["inventory"], e.inventory, []
    if inv is None:
        return [Finding("inventory", "fail", "no inventory collected", "collect")]
    gpus = inv.get("gpus", [])
    if len(gpus) != ic["gpus_per_node"]:
        out.append(Finding("inventory", "fail", f"{len(gpus)} GPUs visible, {ic['gpus_per_node']} expected", "rma"))
    for g in gpus:
        if g.get("model") != ic["gpu_model"]:
            out.append(Finding("inventory", "fail", f"GPU {g.get('index')}: model {g.get('model')}", "rma"))
        if g.get("vbios") != ic["vbios_version"]:
            out.append(Finding("inventory", "fail", f"GPU {g.get('index')}: VBIOS {g.get('vbios')}, "
                               f"baseline {ic['vbios_version']}", "firmware"))
    if inv.get("driver_version") != ic["driver_version"]:
        out.append(Finding("inventory", "fail", f"driver {inv.get('driver_version')}, baseline {ic['driver_version']}", "firmware"))
    ports = inv.get("ib_ports", [])
    if len(ports) != ic["ib_ports_per_node"]:
        out.append(Finding("inventory", "fail", f"{len(ports)} InfiniBand ports, {ic['ib_ports_per_node']} expected", "fabric"))
    for p in ports:
        if p.get("state") != "Active" or p.get("rate_gbps") != ic["ib_rate_gbps"]:
            out.append(Finding("inventory", "fail", f"{p.get('name')}: {p.get('state')} at {p.get('rate_gbps')} Gb/s", "fabric"))
        elif p.get("symbol_errors", 0) > ic["max_ib_symbol_errors"]:
            out.append(Finding("inventory", "warn", f"{p.get('name')}: {p['symbol_errors']} symbol errors"))
    return out


def _diag(e: NodeEvidence, c: Criteria) -> list[Finding]:
    dc = c["diag"]
    if e.diag is None:
        return [Finding("diag", "fail", f"no dcgmi diag -r {dc['level']} result", "collect")]
    out = []
    seen = {r.test.lower() for r in e.diag}
    for t in dc["required_tests"]:
        if t.lower() not in seen:
            out.append(Finding("diag", "fail", f"required test {t} missing from the results", "collect"))
    for r in e.diag:
        where = f"GPU {r.gpu}" if r.gpu is not None else "the node"
        detail = f": {r.message}" if r.message else ""
        if r.status == "fail":
            out.append(Finding("diag", "fail", f"{r.test} test failed on {where}{detail}", "rma"))
        elif r.status == "warn" and not dc["warn_counts_as_pass"]:
            out.append(Finding("diag", "fail", f"{r.test} test warned on {where}{detail}", "investigate"))
        elif r.status == "warn":
            out.append(Finding("diag", "warn", f"{r.test} test warned on {where}{detail}"))
        elif r.status == "skip" and r.test.lower() in {t.lower() for t in dc["required_tests"]}:
            out.append(Finding("diag", "fail", f"{r.test} test skipped on {where}{detail}", "collect"))
    return out


def _nccl_node(e: NodeEvidence, c: Criteria) -> list[Finding]:
    if e.nccl is None:
        return [Finding("nccl-node", "fail", "no single-node nccl-tests result", "collect")]
    out = _nccl_check(e.nccl, c["nccl"]["node"]["min_busbw_gbps"], "nccl-node", "investigate")
    if e.nccl.ranks and e.nccl.ranks != c["inventory"]["gpus_per_node"]:
        out.append(Finding("nccl-node", "fail", f"test ran on {e.nccl.ranks} GPUs", "collect"))
    return out


def _nccl_check(res, target: float, stage: str, disposition: str) -> list[Finding]:
    out = []
    if res.wrong:
        out.append(Finding(stage, "fail", f"{res.wrong} wrong result(s): data corruption", "rma"))
    bw = res.largest_busbw
    if bw < target:
        out.append(Finding(stage, "fail", f"bus bandwidth {bw:.0f} GB/s at the largest size, target {target:.0f}", disposition))
    else:
        out.append(Finding(stage, "info", f"bus bandwidth {bw:.0f} GB/s (target {target:.0f})"))
    return out


def _burnin(e: NodeEvidence, c: Criteria) -> list[Finding]:
    bc, b = c["burnin"], e.burnin
    if b is None:
        return [Finding("burnin", "fail", "no burn-in telemetry", "collect")]
    out = []
    if b.hours < bc["hours"]:
        out.append(Finding("burnin", "fail", f"{b.hours} h of burn-in, {bc['hours']} h agreed", "investigate"))
    hw = [x for x in b.xids if x[2] in set(bc["hardware_xids"])]
    for h, g, x in hw:
        out.append(Finding("burnin", "fail", f"XID {x} on GPU {g} at hour {h}", "rma"))
    if b.dbe > bc["max_dbe"]:
        out.append(Finding("burnin", "fail", f"{b.dbe} uncorrectable ECC error(s)", "rma"))
    if b.sbe_max_per_gpu > bc["max_sbe_per_gpu"]:
        out.append(Finding("burnin", "fail", f"{b.sbe_max_per_gpu} correctable ECC errors on one GPU", "rma"))
    elif b.sbe_max_per_gpu > bc["sbe_warn_per_gpu"]:
        out.append(Finding("burnin", "warn", f"{b.sbe_max_per_gpu} correctable ECC errors on one GPU: watch it"))
    if b.max_temp_c > bc["max_gpu_temp_c"] or b.throttle_fraction > bc["max_throttle_fraction"]:
        out.append(Finding("burnin", "fail", f"max {b.max_temp_c:.0f} °C, thermal throttling {b.throttle_fraction:.1%} "
                           f"of GPU-time (limits {bc['max_gpu_temp_c']:.0f} °C, {bc['max_throttle_fraction']:.0%})", "facility"))
    if b.pass_rate < bc["min_workload_pass_rate"]:
        out.append(Finding("burnin", "fail", f"workload pass rate {b.pass_rate:.2%}", "investigate"))
    return out
