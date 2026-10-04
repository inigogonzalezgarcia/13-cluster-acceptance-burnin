"""accept: acceptance testing for a GPU cluster, from hardware handover to sign-off.

  accept simulate --round 1 -o evidence/round1     # fictional evidence for the lab cluster
  accept evaluate evidence/round1 [evidence/round2 ...] --criteria criteria.toml --out-dir report
  accept plan hosts.txt --criteria criteria.toml   # shell script with the collection commands

Exit code of evaluate: 0 ready for handover, 1 not ready, 2 error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from acceptance import __version__, checks, criteria, evidence, plan, report, sim


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="accept", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("simulate", help="generate fictional evidence for the lab cluster")
    s.add_argument("--round", type=int, choices=(1, 2), default=1)
    s.add_argument("-o", "--output", required=True)

    e = sub.add_parser("evaluate", help="apply the criteria and write the acceptance report")
    e.add_argument("evidence", nargs="+", help="evidence directories, oldest round first")
    e.add_argument("--criteria", default="criteria.toml")
    e.add_argument("--out-dir", help="write report.md, report.html, punch-list.csv and result.json here")

    pl = sub.add_parser("plan", help="print the collection commands as a shell script")
    pl.add_argument("hosts", help="file with one hostname per line (rack prefix before the first '-')")
    pl.add_argument("--criteria", default="criteria.toml")

    args = p.parse_args(argv)
    try:
        if args.cmd == "simulate":
            out = sim.generate(args.output, args.round)
            print(f"wrote round {args.round} evidence to {out}")
            return 0
        if args.cmd == "plan":
            hosts = [h.strip() for h in Path(args.hosts).read_text().splitlines() if h.strip() and not h.startswith("#")]
            sys.stdout.write(plan.render(hosts, criteria.load(args.criteria)))
            return 0
        c = criteria.load(args.criteria)
        ev, manifests = evidence.load_rounds(args.evidence)
        result = checks.evaluate(ev, c)
        md = report.markdown(result, c, manifests)
        if args.out_dir:
            out = Path(args.out_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / "report.md").write_text(md)
            (out / "report.html").write_text(report.html_report(result, c, manifests))
            (out / "punch-list.csv").write_text(report.to_csv(result))
            (out / "result.json").write_text(report.to_json(result, manifests))
            print(f"wrote {out}/report.md, report.html, punch-list.csv, result.json")
        counts = report._counts(result)
        print(f"{result.name}: {'READY' if result.handover_ready else 'NOT READY'} for handover, "
              f"{result.accepted_gpus}/{result.contracted_gpus} GPUs accepted; " +
              ", ".join(f"{report.LABEL[k].lower()} {v}" for k, v in counts.items()))
        return 0 if result.handover_ready else 1
    except (ValueError, OSError) as err:
        print(f"accept: {err}", file=sys.stderr)
        return 2
