# Acceptance report: lab-cluster-a

> Lab exercise: fictional cluster, generated evidence. Structure and rules are what this repository demonstrates; the numbers do not describe real hardware.

**Verdict: READY FOR HANDOVER.** 248 of 256 GPUs accepted (96.9%; 90% required).

| Round | Started | Finished | Nodes tested |
|---|---|---|---|
| 1 | 2026-09-07 | 2026-09-11 | 32 |
| 2 | 2026-09-16 | 2026-09-20 | 13 |

## Summary

| Nodes | Accepted | Accepted, observation | Retest | Rejected (RMA) |
|---|---|---|---|---|
| 32 | 30 | 1 | 0 | 1 |

Cluster burn-in job: 72 h, 2 interruption(s), MTBI 36.0 h (target 24 h), goodput 94.8% (target 90%).

## Racks

| Rack | Nodes accepted | Rack all_reduce | Result |
|---|---|---|---|
| r01 | 8 of 8 | bus bandwidth 359 GB/s (target 340) | pass |
| r02 | 7 of 8 | bus bandwidth 358 GB/s (target 340) | pass |
| r03 | 8 of 8 | bus bandwidth 354 GB/s (target 340) | pass |
| r04 | 8 of 8 | bus bandwidth 360 GB/s (target 340) | pass |

## Nodes

| Node | Result | Last stage | Main finding |
|---|---|---|---|
| r01-n01 | Accepted | burnin |  |
| r01-n02 | Accepted | burnin |  |
| r01-n03 | Accepted | burnin |  |
| r01-n04 | Accepted | burnin |  |
| r01-n05 | Accepted | burnin |  |
| r01-n06 | Accepted | burnin |  |
| r01-n07 | Accepted | burnin |  |
| r01-n08 | Accepted | burnin |  |
| r02-n01 | Accepted, observation | burnin | 36 correctable ECC errors on one GPU: watch it |
| r02-n02 | Accepted | burnin |  |
| r02-n03 | Accepted | burnin |  |
| r02-n04 | Accepted | burnin |  |
| r02-n05 | Rejected (RMA) | diag | Memory test failed on GPU 3: uncorrectable ECC error during the memory test |
| r02-n06 | Accepted | burnin |  |
| r02-n07 | Accepted | burnin |  |
| r02-n08 | Accepted | burnin |  |
| r03-n01 | Accepted | burnin |  |
| r03-n02 | Accepted | burnin |  |
| r03-n03 | Accepted | burnin |  |
| r03-n04 | Accepted | burnin |  |
| r03-n05 | Accepted | burnin |  |
| r03-n06 | Accepted | burnin |  |
| r03-n07 | Accepted | burnin |  |
| r03-n08 | Accepted | burnin |  |
| r04-n01 | Accepted | burnin |  |
| r04-n02 | Accepted | burnin |  |
| r04-n03 | Accepted | burnin |  |
| r04-n04 | Accepted | burnin |  |
| r04-n05 | Accepted | burnin |  |
| r04-n06 | Accepted | burnin |  |
| r04-n07 | Accepted | burnin |  |
| r04-n08 | Accepted | burnin |  |

## Punch list

| Node | Finding | Owner | Next step |
|---|---|---|---|
| r02-n01 | 36 correctable ECC errors on one GPU: watch it | Platform team | Watch in production; revisit at 30 days |
| r02-n05 | Memory test failed on GPU 3: uncorrectable ECC error during the memory test | Hardware vendor | Replace the failed part, then rerun from stage 1 |

## Criteria applied

| Stage | Criterion |
|---|---|
| inventory | 8 × LAB-GPU-80GB per node, driver lab-570.1, VBIOS LAB-96.00.A1 |
| inventory | 8 InfiniBand ports Active at 400 Gb/s |
| diag | dcgmi diag -r 3: Software, PCIe, Memory, Memory Bandwidth, Diagnostic, Targeted Stress, Targeted Power pass on every GPU |
| nccl-node | all_reduce bus bandwidth ≥ 450 GB/s across the node's GPUs, no wrong results |
| nccl-rack | all_reduce bus bandwidth ≥ 340 GB/s per rack, at least 6 nodes |
| burnin | 72 h: no hardware XID, uncorrectable ECC ≤ 0, correctable ECC ≤ 100 per GPU, ≤ 87 °C, throttling ≤ 1%, workload pass rate ≥ 99% |
| job | cluster burn-in job MTBI ≥ 24 h and goodput ≥ 90% |
| cluster | at least 90% of contracted GPUs accepted |

## Sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| Customer |  |  |  |
| Provider |  |  |  |
