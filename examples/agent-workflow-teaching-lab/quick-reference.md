# Quick reference

| Check | Required observation | Why it matters |
| --- | --- | --- |
| Transport status | Request classification such as `ok` | Shows the request returned, not that the task succeeded |
| Semantic outcome | `completed` or an explicit escalation | Prevents empty or incomplete results from being reported as success |
| Workflow identity | Stable synthetic workflow identifier | Lets one run's observations be correlated |
| Retry budget | Observed retries at or below the ceiling | Prevents silent amplification |
| Cost budget | Estimated usage at or below the ceiling | Makes bounded execution visible |
| Independent breaker | Known degraded path is rejected | Tests evaluator validity, not just agent behavior |
| Human approval | Escalated result remains reviewable | Keeps automation separate from consequential approval |

The table describes the synthetic contract. It is not a production telemetry
schema and does not authorize an external action.
