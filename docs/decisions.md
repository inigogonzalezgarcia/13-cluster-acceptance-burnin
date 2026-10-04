# Design decisions

## 1. Evidence first, verdict second

Collection (commands on the cluster) and evaluation (rules on files) are separate. The evaluation can be rerun when a criterion changes, reviewed by the customer, and tested without hardware. The same files are what the customer keeps as proof of what was tested.

## 2. Stop a node at its first failure

A node that fails inventory is not worth an hour of diagnostics, and a node with a bad GPU must not be in the rack test, where it would make the whole rack look slow. The cost is that a node with two problems shows one at a time; in practice the fix for the first usually changes the second.

## 3. Every failure has a disposition

"Failed" is not actionable. RMA, firmware, fabric, facility, investigate and collect each map to an owner and a next step, which is what turns a test report into a punch list. Only hardware faults make a node "Rejected"; everything else is "Retest".

## 4. Rack failures are attributed when the evidence allows

A slow rack test does not say which link is bad. If a node in the rack shows InfiniBand errors in its inventory, the failure is pinned on it; the other nodes wait for the rack instead of each getting its own ticket.

## 5. Rounds replace, not append

A retest supersedes the old result for that node or rack. The report always shows the current state, and the rounds table shows the history.

## 6. Criteria in a file the customer signs

TOML, read with the standard library, with unknown keys rejected. The report repeats the criteria that were applied, so the document is self-contained.

## 7. Same metrics as the rest of the series

The burn-in job uses the event log and goodput rules of repo 12, and the hardware-XID list of repos 09–11. One definition of "interruption" across the series.

## 8. Standard library only

Python 3.11+ (for `tomllib`), no dependencies, so it runs on a bastion host without installing anything.
