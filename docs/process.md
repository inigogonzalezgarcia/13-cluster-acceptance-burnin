# The acceptance process

From "the racks are installed and powered" to "the customer runs production on it". The tool covers the evidence and the decision; the process around it matters as much.

## Stages

| # | Stage | Scope | What it proves | Typical tool |
|---|---|---|---|---|
| 1 | Inventory | node | The node is what was ordered: GPU count and model, driver and firmware on the agreed baseline, every InfiniBand port up at full rate | `nvidia-smi`, `ibstat`, `perfquery` |
| 2 | Diagnostics | node | Every GPU passes the vendor's diagnostics at the agreed level | `dcgmi diag -r 3` |
| 3 | Node collective | node | GPUs inside the node talk to each other at full speed, with no wrong results | `nccl-tests` `all_reduce_perf` |
| 4 | Rack collective | rack | The fabric between nodes performs | `nccl-tests` across the rack |
| 5 | Burn-in | node + cluster | Nothing fails under days of load: no hardware XIDs, no uncorrectable ECC, temperatures and throttling within limits | a training-like workload plus telemetry |
| 6 | Burn-in job | cluster | The cluster as a whole meets the agreed MTBI and goodput | the same job, measured as in repo 12 |

A node that fails a stage stops there. Testing it further only adds noise to the rack test and wastes days of burn-in on a node that has to be fixed anyway.

## Rounds

Round 1 tests everything. Its punch list goes to the owners: hardware vendor for RMAs, network team for fabric, facilities for cooling, platform team for firmware and anything that needs root-causing. Round 2 retests only what was fixed, plus the rack tests of racks that get nodes back, and a fresh cluster-wide burn-in job. A later round's evidence replaces the earlier one for the same node or rack (`accept evaluate round1 round2`).

In the lab cluster: round 1 accepts 144 of 256 GPUs (eight planted defects, and rack r04 blocked by one bad InfiniBand link). Round 2 reaches 248 of 256. One node waits for a replacement GPU and is listed as an exception in the handover.

## Shortening the time to the first production workload

- **Agree the criteria before the hardware arrives.** Every number in criteria.toml is a conversation with the customer. Agreeing them during testing turns each failure into a negotiation.
- **Run once, share the evidence.** Hardware bring-up, the managed-service intake and the customer's own team often each run their own diagnostics. One evidence set that all of them accept removes days.
- **Stop early, fix in parallel.** Stopping a node at its first failure frees it for repair while the others continue.
- **Hand over in parts.** A rack that passes can be released while another waits for a cable. The report shows accepted nodes per rack; a contract that allows partial handover lets the customer start earlier.
- **Make every finding actionable.** Each punch-list line has an owner and a next step, not just "failed".

## What the report is for

It is written for the customer, not for the people who ran the tests: a verdict at the top, a picture of the racks, the open items with owners, the criteria that were applied, and a sign-off table. The JSON and CSV are for tracking the punch list in a ticketing system.
