# Evidence

`accept evaluate` reads one directory per test round:

```
evidence/round1/
  manifest.json                    round number, dates, nodes tested
  nodes/<host>/inventory.json      stage 1
  nodes/<host>/dcgm-diag.json      stage 2, output of `dcgmi diag -r 3 -j`
  nodes/<host>/nccl-allreduce.txt  stage 3, stdout of `all_reduce_perf`
  nodes/<host>/burnin.jsonl        stage 5, hourly per-GPU telemetry
  racks/<rack>/nccl-allreduce.txt  stage 4
  burnin-job.jsonl                 stage 6, event log of the cluster-wide burn-in job
```

Missing files are findings ("no … collected"), not crashes. `accept plan hosts.txt` prints the commands that would produce each file.

## Formats

**dcgm-diag.json.** The parser looks for `test_categories` anywhere in the document, then reads `tests[].name` and `tests[].results[]` with a `status` (Pass, Fail, Warn, Skip; any case) and a GPU in `gpu_id` or `entity_id` (no GPU means the result applies to the whole node). Warnings come from `results[].warnings[].warning`. This follows the general shape of `dcgmi diag -j`, and the tests cover two variants of field names, but **it has not been run against real DCGM output**: check it against your DCGM version first.

**nccl-allreduce.txt.** The standard `nccl-tests` table: the out-of-place `busbw` at the largest message size is compared with the target, `#wrong` must be 0 in both columns (`N/A` counts as 0), and the `# Rank … on <host>` lines give the participating hosts.

**inventory.json** (lab format):

```json
{"hostname": "r01-n01", "rack": "r01", "driver_version": "lab-570.1",
 "gpus": [{"index": 0, "model": "LAB-GPU-80GB", "vbios": "LAB-96.00.A1", "serial": "…"}],
 "ib_ports": [{"name": "mlx5_0", "state": "Active", "rate_gbps": 400, "symbol_errors": 0, "link_downed": 0}]}
```

**burnin.jsonl**, one line per GPU per hour:

```json
{"hour": 30, "gpu": 5, "max_temp_c": 71.2, "thermal_throttle_s": 0, "sbe": 0, "dbe": 0, "xid": [79], "iterations": 60, "failures": 1}
```

**burnin-job.jsonl**: the event log of repo 12 (start, checkpoint_start/end, interrupt, detected, nodes_ready, running, end), so goodput and MTBI mean the same thing in both repos.

## The lab evidence

`accept simulate --round 1|2` writes the evidence of the fictional `lab-cluster-a` (4 racks × 8 nodes × 8 GPUs) with the defects listed in `acceptance/sim.py`. It is deterministic, so the reports in `docs/sample-report-round*.md` can be regenerated exactly; a test fails if they drift from the code:

```bash
python -m acceptance simulate --round 1 -o evidence/round1
python -m acceptance simulate --round 2 -o evidence/round2
python -m acceptance evaluate evidence/round1 --out-dir report/round1 && cp report/round1/report.md docs/sample-report-round1.md
python -m acceptance evaluate evidence/round1 evidence/round2 --out-dir report/round2 && cp report/round2/report.md docs/sample-report-round2.md
```
