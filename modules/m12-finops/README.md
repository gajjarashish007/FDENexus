# M12 FinOps & Resource Optimization

Estimate, allocate, forecast and optimize cloud spend.

Owner: FinOps · Phase: P2 · Shown on dashboard by default: yes

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| Cost estimation | live | Monthly estimate on every infrastructure change. (from M03) |
| Budgets | planned | Not built yet. |
| Cost allocation | partial | Tags allow allocation by team and environment; no billing import yet. (from M03) |
| Resource tagging | live | Team, owner, environment, tier and request id tags on every resource via provider default_tags. (from M03) |
| Cost forecasting | planned | Not built yet. |
| Anomaly detection | planned | Not built yet. |
| Idle resource identification | planned | Not built yet. |
| Rightsizing | planned | Not built yet. |
| Reserved capacity recommendations | planned | Not built yet. |
| Storage optimization | partial | S3 lifecycle rules and EFS Infrequent Access transitions by default. (from M02) |
| Cost center reporting | planned | Not built yet. |
| Unit economics | planned | Not built yet. |
| Cost governance | partial | Sandbox instance-size policy; cost shown to approvers. (from M03) |

## Building this module

Copy `modules/_template/backend` into this folder, implement `register(app, ctx)`, and flip each
capability's `status` in `manifest.json` as it becomes real. The core loads it on restart.
