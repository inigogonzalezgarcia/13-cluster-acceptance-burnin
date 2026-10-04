# Acceptance criteria

`criteria.toml` holds every threshold. Unknown keys are rejected, so a typo cannot silently relax a criterion. **The values are lab assumptions**: in a real project they come from the contract, the vendor's reference values for the exact system, and the customer's workload.

| Key | Lab value | Why it exists |
|---|---|---|
| `cluster.min_accepted_gpu_fraction` | 0.90 | Handover with a few nodes in RMA is normal; how many is a contract question |
| `inventory.gpus_per_node`, `gpu_model` | 8, LAB-GPU-80GB | A GPU that is not visible is the most common day-one failure |
| `inventory.driver_version`, `vbios_version` | lab baseline | Mixed firmware makes every later result harder to trust |
| `inventory.ib_*` | 8 ports at 400 Gb/s, 0 symbol errors | A port at the wrong rate or with errors shows up later as a slow rack |
| `diag.level`, `required_tests` | 3, seven tests | Level 3 runs the stress and memory tests; a required test that is skipped counts as missing |
| `diag.warn_counts_as_pass` | true | Warnings are reported as observations instead of blocking; some customers want them to block |
| `nccl.node.min_busbw_gbps` | 450 | all_reduce bus bandwidth across the GPUs of one node, at the largest message size |
| `nccl.rack.min_busbw_gbps`, `min_nodes` | 340, 6 | Same across a rack over InfiniBand; with fewer than 6 healthy nodes the test says little |
| `burnin.hours` | 72 | Long enough for early-life failures to show |
| `burnin.hardware_xids` | 48, 63, 64, 74, 79, 92, 95, 119, 120 | Same list as repos 09–12; application XIDs (13, 31, 43, 45) do not fail a node |
| `burnin.max_dbe`, `max_sbe_per_gpu`, `sbe_warn_per_gpu` | 0, 100, 10 | Uncorrectable ECC fails the node; a growing correctable count is watched or fails it |
| `burnin.max_gpu_temp_c`, `max_throttle_fraction` | 87 °C, 1% | Heat problems are usually the room, not the GPU: facilities own them |
| `burnin.min_workload_pass_rate` | 0.99 | The burn-in workload validates its own results |
| `burnin.job.min_mtbi_hours`, `min_goodput` | 24 h, 90% | The cluster-wide job: the same metrics as repo 12 (gpu-goodput-mtbi) |

## Outcomes

| Node result | Meaning |
|---|---|
| Accepted | Every stage passed |
| Accepted, observation | Passed, with something to watch (a warning, correctable errors) |
| Retest | Failed for a reason that can be fixed without replacing hardware: firmware, fabric, cooling, missing evidence, or its rack failed |
| Rejected (RMA) | A hardware fault: replace the part, then test again from stage 1 |
