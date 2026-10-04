# Acceptance report: lab-cluster-a

> Lab exercise: fictional cluster, generated evidence. Structure and rules are what this repository demonstrates; the numbers do not describe real hardware.

**Verdict: NOT READY FOR HANDOVER.** 144 of 256 GPUs accepted (56.2%; 90% required).

| Round | Started | Finished | Nodes tested |
|---|---|---|---|
| 1 | 2026-09-07 | 2026-09-11 | 32 |

## Summary

| Nodes | Accepted | Accepted, observation | Retest | Rejected (RMA) |
|---|---|---|---|---|
| 32 | 17 | 1 | 11 | 3 |

Cluster burn-in job: 72 h, 2 interruption(s), MTBI 36.0 h (target 24 h), goodput 94.2% (target 90%).

Blocking items at cluster level:

- 144 of 256 GPUs accepted, 90% (230) needed

## Racks

| Rack | Nodes accepted | Rack all_reduce | Result |
|---|---|---|---|
| r01 | 7 of 8 | bus bandwidth 365 GB/s (target 340) | pass |
| r02 | 6 of 8 | bus bandwidth 357 GB/s (target 340) | pass |
| r03 | 7 of 8 | bus bandwidth 358 GB/s (target 340) | pass |
| r04 | 8 of 8 | bus bandwidth 248 GB/s at the largest size, target 340 | FAIL |

## Nodes

| Node | Result | Last stage | Main finding |
|---|---|---|---|
| r01-n01 | Accepted | burnin |  |
| r01-n02 | Accepted | burnin |  |
| r01-n03 | Retest | inventory | GPU 4: VBIOS LAB-96.00.9F, baseline LAB-96.00.A1 |
| r01-n04 | Accepted | burnin |  |
| r01-n05 | Accepted | burnin |  |
| r01-n06 | Accepted | burnin |  |
| r01-n07 | Accepted | burnin |  |
| r01-n08 | Rejected (RMA) | burnin | XID 79 on GPU 5 at hour 30 |
| r02-n01 | Accepted, observation | burnin | 36 correctable ECC errors on one GPU: watch it |
| r02-n02 | Accepted | burnin |  |
| r02-n03 | Accepted | burnin |  |
| r02-n04 | Accepted | burnin |  |
| r02-n05 | Rejected (RMA) | diag | Memory test failed on GPU 3: uncorrectable ECC error during the memory test |
| r02-n06 | Accepted | burnin |  |
| r02-n07 | Rejected (RMA) | inventory | 7 GPUs visible, 8 expected |
| r02-n08 | Accepted | burnin |  |
| r03-n01 | Accepted | burnin |  |
| r03-n02 | Retest | nccl-node | bus bandwidth 311 GB/s at the largest size, target 450 |
| r03-n03 | Accepted | burnin |  |
| r03-n04 | Accepted | burnin |  |
| r03-n05 | Accepted | burnin |  |
| r03-n06 | Retest | burnin | max 92 °C, thermal throttling 1.7% of GPU-time (limits 87 °C, 1%) |
| r03-n07 | Accepted | burnin |  |
| r03-n08 | Accepted | burnin |  |
| r04-n01 | Retest | nccl-node | rack r04 did not pass; node not burned in |
| r04-n02 | Retest | nccl-node | rack r04 did not pass; node not burned in |
| r04-n03 | Retest | nccl-node | rack r04 did not pass; node not burned in |
| r04-n04 | Retest | nccl-node | rack r04 did not pass; node not burned in |
| r04-n05 | Retest | nccl-node | rack r04 did not pass; node not burned in |
| r04-n06 | Retest | nccl-node | rack test failed; InfiniBand errors on mlx5_3 |
| r04-n07 | Retest | nccl-node | rack r04 did not pass; node not burned in |
| r04-n08 | Retest | nccl-node | rack r04 did not pass; node not burned in |

## Punch list

| Node | Finding | Owner | Next step |
|---|---|---|---|
| rack r04 | bus bandwidth 248 GB/s at the largest size, target 340; 7 node(s) wait for it | Network team | Check cable, optics and switch port, then rerun the rack test |
| r01-n03 | GPU 4: VBIOS LAB-96.00.9F, baseline LAB-96.00.A1 | Platform team | Flash the baseline version, then rerun from stage 1 |
| r01-n08 | XID 79 on GPU 5 at hour 30 | Hardware vendor | Replace the failed part, then rerun from stage 1 |
| r02-n01 | 36 correctable ECC errors on one GPU: watch it | Platform team | Watch in production; revisit at 30 days |
| r02-n05 | Memory test failed on GPU 3: uncorrectable ECC error during the memory test | Hardware vendor | Replace the failed part, then rerun from stage 1 |
| r02-n07 | 7 GPUs visible, 8 expected | Hardware vendor | Replace the failed part, then rerun from stage 1 |
| r03-n02 | bus bandwidth 311 GB/s at the largest size, target 450 | Platform team | Root-cause before deciding on RMA or retest |
| r03-n06 | max 92 °C, thermal throttling 1.7% of GPU-time (limits 87 °C, 1%) | Data centre facilities | Fix airflow or cooling, then rerun burn-in |
| r04-n06 | rack test failed; InfiniBand errors on mlx5_3 | Network team | Check cable, optics and switch port, then rerun the rack test |
| cluster | 144 of 256 GPUs accepted, 90% (230) needed | Provider project lead | Close the items above, then run a retest round |

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
