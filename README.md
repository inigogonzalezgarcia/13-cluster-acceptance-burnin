# GPU Cluster Acceptance and Burn-in

Acceptance testing for a new GPU cluster, from hardware handover to a platform the customer signs off: staged validation per node and per rack, a multi-day burn-in, agreed criteria in one file, a punch list with owners, and an acceptance report written for the customer.

**Inventory → DCGM diagnostics → NCCL per node → NCCL per rack → burn-in → cluster burn-in job → report and punch list**

![ci](https://github.com/inigogonzalezgarcia/13-cluster-acceptance-burnin/actions/workflows/ci.yml/badge.svg)

> A learning-in-public lab about bringing up GPU clusters. I don't have production GPU fleet experience; this project is how I am learning the problem. There is no GPU here: the evidence comes from a simulator of a fictional 256-GPU cluster with planted defects, in the general formats of `dcgmi diag -j` and `nccl-tests`. The parsers are tested on those samples only.

Fifth in a series: [09 – node remediation](https://github.com/inigogonzalezgarcia/09-gpu-node-remediation), [10 – fleet observability](https://github.com/inigogonzalezgarcia/10-gpu-fleet-observability), [11 – fleet lifecycle](https://github.com/inigogonzalezgarcia/11-gpu-fleet-lifecycle), [12 – goodput and MTBI](https://github.com/inigogonzalezgarcia/12-gpu-goodput-mtbi). Those run a cluster in production; this one decides when a cluster is ready to get there.

## The lab cluster, two rounds

`lab-cluster-a`: 4 racks × 8 nodes × 8 GPUs. Round 1 has eight planted defects. Round 2 retests what was fixed.

| | Round 1 | Round 1 + 2 |
|---|---|---|
| Verdict | **Not ready** | **Ready for handover** |
| GPUs accepted | 144 of 256 (56%) | 248 of 256 (97%; 90% required) |
| Racks passing the rack test | 3 of 4 | 4 of 4 |
| Burn-in job | MTBI 36 h, goodput 94.2% | MTBI 36 h, goodput 94.8% |
| Open items | 10 | 2 (one RMA pending, one observation) |

What round 1 caught, and who it went to:

| Node | Finding | Result | Owner |
|---|---|---|---|
| r01-n03 | GPU 4 on a non-baseline VBIOS | Retest | Platform team |
| r01-n08 | XID 79 (GPU fell off the bus) at hour 30 of burn-in | Rejected (RMA) | Hardware vendor |
| r02-n01 | Correctable ECC errors growing, below the limit | Accepted, observation | Platform team |
| r02-n05 | DCGM memory test failed on GPU 3 | Rejected (RMA) | Hardware vendor |
| r02-n07 | 7 of 8 GPUs visible | Rejected (RMA) | Hardware vendor |
| r03-n02 | Node all_reduce at 311 GB/s, target 450 | Retest | Platform team |
| r03-n06 | 92 °C and thermal throttling in burn-in | Retest | Facilities |
| rack r04 | Rack all_reduce at 248 GB/s, target 340; r04-n06 has InfiniBand symbol errors | Retest (8 nodes) | Network team |

Full reports: [round 1](docs/sample-report-round1.md), [rounds 1 + 2](docs/sample-report-round2.md). CI regenerates both and fails if they no longer match the code. The HTML version (verdict, rack grid, punch list) is attached to every CI run as the `acceptance-reports` artifact.

## Run it

Python 3.11+, standard library only.

```bash
python -m acceptance simulate --round 1 -o evidence/round1
python -m acceptance evaluate evidence/round1 --out-dir report/round1          # exit 1: not ready
python -m acceptance simulate --round 2 -o evidence/round2
python -m acceptance evaluate evidence/round1 evidence/round2 --out-dir report/round2   # exit 0: ready
python -m acceptance plan hosts.txt          # the collection commands for a real cluster, as a shell script
python -m unittest -v
```

`evaluate` writes `report.md` and `report.html` for the customer, `punch-list.csv` for the ticketing system and `result.json` for automation.

## How it decides

| Stage | Scope | Passes when |
|---|---|---|
| Inventory | node | GPU count and model, driver and VBIOS on the baseline, every InfiniBand port Active at full rate |
| Diagnostics | node | Every required `dcgmi diag -r 3` test passes on every GPU |
| Node collective | node | `all_reduce_perf` bus bandwidth at the largest size ≥ target, no wrong results |
| Rack collective | rack | Same across the rack's accepted nodes, with enough of them to mean something |
| Burn-in | node | 72 h without hardware XIDs or uncorrectable ECC; temperature, throttling and correctable ECC within limits |
| Burn-in job | cluster | MTBI and goodput of the cluster-wide job meet the targets |

A node stops at its first failure. Each failure has a disposition (RMA, firmware, fabric, facility, investigate, collect) that sets the owner and the next step. Hardware faults reject a node; everything else is a retest. All thresholds live in [criteria.toml](criteria.toml).

## Documentation

- [docs/process.md](docs/process.md): stages, rounds, and how to shorten the time from handover to the first production workload
- [docs/criteria.md](docs/criteria.md): every criterion and why it exists
- [docs/evidence.md](docs/evidence.md): the evidence layout and file formats
- [docs/decisions.md](docs/decisions.md): design decisions

## Roadmap

- Run the parsers against real `dcgmi diag` and `nccl-tests` output and fix what differs.
- Pairwise node tests to locate a bad link inside a failing rack without relying on port counters.
- Storage acceptance (throughput and metadata rates against the agreed targets).
- Feed the punch list into a ticketing system.

## Customisation and contact

Want to talk about GPU cluster bring-up, acceptance testing or a lab like this for your team? Get in touch:

- Email: [inigogonzalezgarcia@yahoo.es](mailto:inigogonzalezgarcia@yahoo.es)
- LinkedIn: [linkedin.com/in/igonzalez93](https://www.linkedin.com/in/igonzalez93)

## License

MIT
