"""The acceptance report for the customer (Markdown and HTML), the punch list (CSV) and the
machine-readable result (JSON)."""

from __future__ import annotations

import csv
import html
import io
import json

from acceptance.checks import DISPOSITIONS, ClusterResult
from acceptance.criteria import Criteria

LABEL = {"ACCEPTED": "Accepted", "ACCEPTED_WITH_OBSERVATIONS": "Accepted, observation",
         "RETEST": "Retest", "REJECTED": "Rejected (RMA)"}
SHORT = {"ACCEPTED": "OK", "ACCEPTED_WITH_OBSERVATIONS": "OBS", "RETEST": "RT", "REJECTED": "RMA"}


def punch_list(r: ClusterResult) -> list[dict]:
    rows = []
    for k in r.racks:
        for f in k.findings:
            if f.severity == "fail":
                owner, action = DISPOSITIONS.get(f.disposition, ("Platform team", ""))
                waiting = [n.name for n in r.nodes if n.rack == k.name and any(x.disposition == "rack" for x in n.findings)]
                note = f"; {len(waiting)} node(s) wait for it" if waiting else ""
                rows.append({"node": f"rack {k.name}", "status": "", "stage": f.stage, "severity": f.severity,
                             "finding": f.message + note, "owner": owner, "next_step": action})
    for n in r.nodes:
        for f in n.findings:
            if f.disposition == "rack":
                continue  # covered by the rack's line
            if f.severity == "fail" or (f.severity == "warn" and n.accepted):
                owner, action = DISPOSITIONS.get(f.disposition, ("Platform team", "Track until next review"))
                rows.append({"node": n.name, "status": n.status, "stage": f.stage, "severity": f.severity,
                             "finding": f.message, "owner": owner if f.severity == "fail" else "Platform team",
                             "next_step": action if f.severity == "fail" else "Watch in production; revisit at 30 days"})
    for f in r.findings:
        owner, action = DISPOSITIONS.get(f.disposition, ("Platform team", ""))
        rows.append({"node": "cluster", "status": "", "stage": f.stage, "severity": f.severity, "finding": f.message,
                     "owner": owner, "next_step": action})
    return rows


def to_csv(r: ClusterResult) -> str:
    buf = io.StringIO()
    rows = punch_list(r)
    w = csv.DictWriter(buf, fieldnames=["node", "status", "stage", "severity", "finding", "owner", "next_step"],
                       lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def to_json(r: ClusterResult, manifests: list[dict]) -> str:
    return json.dumps({
        "cluster": r.name, "handover_ready": r.handover_ready, "contracted_gpus": r.contracted_gpus,
        "accepted_gpus": r.accepted_gpus, "rounds": manifests,
        "job": {k: v for k, v in (r.job or {}).items() if k != "events"} or None,
        "racks": [{"rack": k.name, "passed": k.passed, "accepted_nodes": k.accepted_nodes,
                   "findings": [vars(f) for f in k.findings]} for k in r.racks],
        "nodes": [{"node": n.name, "rack": n.rack, "status": n.status, "reached": n.reached,
                   "findings": [vars(f) for f in n.findings]} for n in r.nodes],
        "cluster_findings": [vars(f) for f in r.findings],
    }, indent=2) + "\n"


def _verdict(r: ClusterResult) -> str:
    return "READY FOR HANDOVER" if r.handover_ready else "NOT READY FOR HANDOVER"


def _counts(r: ClusterResult) -> dict[str, int]:
    out = {k: 0 for k in LABEL}
    for n in r.nodes:
        out[n.status] += 1
    return out


def _key_finding(n) -> str:
    for sev in ("fail", "warn"):
        for f in n.findings:
            if f.severity == sev:
                return f.message
    return ""


def markdown(r: ClusterResult, c: Criteria, manifests: list[dict]) -> str:
    pct = r.accepted_gpus / r.contracted_gpus
    job = r.job or {}
    out = [f"# Acceptance report: {r.name}", "",
           "> Lab exercise: fictional cluster, generated evidence. Structure and rules are what this repository "
           "demonstrates; the numbers do not describe real hardware.", "",
           f"**Verdict: {_verdict(r)}.** {r.accepted_gpus} of {r.contracted_gpus} GPUs accepted ({pct:.1%}; "
           f"{c['cluster']['min_accepted_gpu_fraction']:.0%} required).", ""]
    if manifests:
        out += ["| Round | Started | Finished | Nodes tested |", "|---|---|---|---|"]
        for m in manifests:
            out.append(f"| {m.get('round', '?')} | {str(m.get('started', ''))[:10]} | {str(m.get('finished', ''))[:10]} | "
                       f"{len(m.get('nodes', []))} |")
        out.append("")
    cnt = _counts(r)
    out += ["## Summary", "",
            "| Nodes | " + " | ".join(LABEL.values()) + " |", "|---|" + "---|" * len(LABEL),
            f"| {len(r.nodes)} | " + " | ".join(str(cnt[k]) for k in LABEL) + " |", ""]
    if job:
        jc = c["burnin"]["job"]
        mtbi = f"{job['mtbi_hours']:.1f} h" if job.get("mtbi_hours") else "no interruptions"
        out += [f"Cluster burn-in job: {job['hours']:.0f} h, {job['interruptions']} interruption(s), MTBI {mtbi} "
                f"(target {jc['min_mtbi_hours']} h), goodput {job['goodput']:.1%} (target {jc['min_goodput']:.0%}).", ""]
    if r.findings:
        out += ["Blocking items at cluster level:", ""] + [f"- {f.message}" for f in r.findings] + [""]
    out += ["## Racks", "", "| Rack | Nodes accepted | Rack all_reduce | Result |", "|---|---|---|---|"]
    for k in r.racks:
        bw = next((f.message for f in k.findings if f.stage == "nccl-rack" and "bandwidth" in f.message), "")
        out.append(f"| {k.name} | {len(k.accepted_nodes)} of {len(k.nodes)} | {bw} | {'pass' if k.passed else 'FAIL'} |")
    out += ["", "## Nodes", "", "| Node | Result | Last stage | Main finding |", "|---|---|---|---|"]
    for n in r.nodes:
        out.append(f"| {n.name} | {LABEL[n.status]} | {n.reached} | {_key_finding(n)} |")
    rows = punch_list(r)
    out += ["", "## Punch list", ""]
    if rows:
        out += ["| Node | Finding | Owner | Next step |", "|---|---|---|---|"]
        out += [f"| {p['node']} | {p['finding']} | {p['owner']} | {p['next_step']} |" for p in rows]
    else:
        out.append("Nothing open.")
    out += ["", "## Criteria applied", "", "| Stage | Criterion |", "|---|---|"]
    out += [f"| {s} | {t} |" for s, t in _criteria_rows(c)]
    out += ["", "## Sign-off", "",
            "| Role | Name | Date | Signature |", "|---|---|---|---|",
            "| Customer |  |  |  |", "| Provider |  |  |  |", ""]
    return "\n".join(out)


def _criteria_rows(c: Criteria) -> list[tuple[str, str]]:
    i, d, n, b = c["inventory"], c["diag"], c["nccl"], c["burnin"]
    return [
        ("inventory", f"{i['gpus_per_node']} × {i['gpu_model']} per node, driver {i['driver_version']}, VBIOS {i['vbios_version']}"),
        ("inventory", f"{i['ib_ports_per_node']} InfiniBand ports Active at {i['ib_rate_gbps']} Gb/s"),
        ("diag", f"dcgmi diag -r {d['level']}: {', '.join(d['required_tests'])} pass on every GPU"),
        ("nccl-node", f"all_reduce bus bandwidth ≥ {n['node']['min_busbw_gbps']:g} GB/s across the node's GPUs, no wrong results"),
        ("nccl-rack", f"all_reduce bus bandwidth ≥ {n['rack']['min_busbw_gbps']:g} GB/s per rack, at least {n['rack']['min_nodes']} nodes"),
        ("burnin", f"{b['hours']} h: no hardware XID, uncorrectable ECC ≤ {b['max_dbe']}, correctable ECC ≤ {b['max_sbe_per_gpu']} per GPU, "
                   f"≤ {b['max_gpu_temp_c']:g} °C, throttling ≤ {b['max_throttle_fraction']:.0%}, workload pass rate ≥ {b['min_workload_pass_rate']:.0%}"),
        ("job", f"cluster burn-in job MTBI ≥ {b['job']['min_mtbi_hours']:g} h and goodput ≥ {b['job']['min_goodput']:.0%}"),
        ("cluster", f"at least {c['cluster']['min_accepted_gpu_fraction']:.0%} of contracted GPUs accepted"),
    ]


CSS = """
:root{--surface:#fcfcfb;--panel:#fff;--text:#0b0b0b;--text2:#52514e;--rule:#e4e3df;
--good:#0a7d38;--good-bg:#e3f4e9;--warn:#8a5a00;--warn-bg:#fdf1d6;--bad:#b42318;--bad-bg:#fde7e5;--retest:#1f5fae;--retest-bg:#e3eefb;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--surface:#1a1a19;--panel:#222221;--text:#fff;--text2:#c3c2b7;--rule:#3a3a37;
--good:#6fd394;--good-bg:#173323;--warn:#f0c062;--warn-bg:#3a2f14;--bad:#ff8a80;--bad-bg:#3d1c1a;--retest:#8cb8f2;--retest-bg:#1b2c42;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--surface);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1000px;margin:0 auto;padding:24px 16px 48px}h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 8px}
p{color:var(--text2);margin:4px 0 12px}.note{font-size:13px}
.verdict{border-radius:8px;padding:14px 16px;margin:16px 0;font-weight:600;border:1px solid var(--rule)}
.verdict.ok{background:var(--good-bg);color:var(--good)}.verdict.no{background:var(--bad-bg);color:var(--bad)}
.verdict span{display:block;font-weight:400;color:var(--text2);margin-top:2px}
.grid{display:grid;grid-template-columns:56px repeat(8,minmax(0,1fr));gap:4px;align-items:center;margin:8px 0 4px}
.grid .rk{font-size:13px;color:var(--text2)}.cell{border-radius:6px;padding:6px 2px;text-align:center;font-size:11px;font-weight:600;border:1px solid var(--rule)}
.s-ACCEPTED{background:var(--good-bg);color:var(--good)}.s-ACCEPTED_WITH_OBSERVATIONS{background:var(--warn-bg);color:var(--warn)}
.s-RETEST{background:var(--retest-bg);color:var(--retest)}.s-REJECTED{background:var(--bad-bg);color:var(--bad)}
.legend{display:flex;flex-wrap:wrap;gap:8px;font-size:12px;margin:6px 0 0}.legend .cell{padding:2px 8px}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--rule);vertical-align:top}th{color:var(--text2);font-weight:600}
td:first-child{white-space:nowrap}
"""


def html_report(r: ClusterResult, c: Criteria, manifests: list[dict]) -> str:
    e = html.escape
    pct = r.accepted_gpus / r.contracted_gpus
    job = r.job or {}
    parts = [f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
             f"<title>Acceptance report {e(r.name)}</title><style>{CSS}</style></head><body><main>",
             f"<h1>Acceptance report: {e(r.name)}</h1>",
             "<p class=\"note\">Lab exercise: fictional cluster and generated evidence. The numbers do not describe real hardware.</p>",
             f"<div class=\"verdict {'ok' if r.handover_ready else 'no'}\">{'✓' if r.handover_ready else '✕'} {_verdict(r)}"
             f"<span>{r.accepted_gpus} of {r.contracted_gpus} GPUs accepted ({pct:.1%}; "
             f"{c['cluster']['min_accepted_gpu_fraction']:.0%} required)"]
    if job:
        mtbi = f"{job['mtbi_hours']:.1f} h" if job.get("mtbi_hours") else "no interruptions"
        parts.append(f" · burn-in job MTBI {mtbi}, goodput {job['goodput']:.1%}")
    parts.append("</span></div>")
    parts.append("<h2>Nodes by rack</h2><div class=\"grid\">")
    for k in r.racks:
        parts.append(f"<div class=\"rk\">{e(k.name)}</div>")
        for name in k.nodes:
            n = next(x for x in r.nodes if x.name == name)
            parts.append(f"<div class=\"cell s-{n.status}\" title=\"{e(name)}: {e(LABEL[n.status])}. {e(_key_finding(n))}\">"
                         f"{e(name[-3:])}<br>{SHORT[n.status]}</div>")
    parts.append("</div><div class=\"legend\">" + "".join(f"<span class=\"cell s-{k}\">{SHORT[k]} · {LABEL[k]}</span>" for k in LABEL) + "</div>")
    rows = punch_list(r)
    parts.append("<h2>Punch list</h2>")
    if rows:
        parts.append("<div class=\"wrap\"><table><tr><th>Node</th><th>Finding</th><th>Owner</th><th>Next step</th></tr>")
        parts += [f"<tr><td>{e(p['node'])}</td><td>{e(p['finding'])}</td><td>{e(p['owner'])}</td><td>{e(p['next_step'])}</td></tr>" for p in rows]
        parts.append("</table></div>")
    else:
        parts.append("<p>Nothing open.</p>")
    parts.append("<h2>Racks</h2><div class=\"wrap\"><table><tr><th>Rack</th><th>Nodes accepted</th><th>Rack all_reduce</th><th>Result</th></tr>")
    for k in r.racks:
        bw = next((f.message for f in k.findings if f.stage == "nccl-rack" and "bandwidth" in f.message), "")
        parts.append(f"<tr><td>{e(k.name)}</td><td>{len(k.accepted_nodes)} of {len(k.nodes)}</td><td>{e(bw)}</td>"
                     f"<td>{'pass' if k.passed else 'FAIL'}</td></tr>")
    parts.append("</table></div>")
    if manifests:
        parts.append("<h2>Test rounds</h2><div class=\"wrap\"><table><tr><th>Round</th><th>Started</th><th>Finished</th><th>Nodes tested</th></tr>")
        parts += [f"<tr><td>{m.get('round', '?')}</td><td>{e(str(m.get('started', ''))[:10])}</td><td>{e(str(m.get('finished', ''))[:10])}</td>"
                  f"<td>{len(m.get('nodes', []))}</td></tr>" for m in manifests]
        parts.append("</table></div>")
    parts.append("<h2>Criteria applied</h2><div class=\"wrap\"><table><tr><th>Stage</th><th>Criterion</th></tr>")
    parts += [f"<tr><td>{e(s)}</td><td>{e(t)}</td></tr>" for s, t in _criteria_rows(c)]
    parts.append("</table></div></main></body></html>\n")
    return "".join(parts)
