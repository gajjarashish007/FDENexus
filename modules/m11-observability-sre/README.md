# M11 Observability & SRE

Metrics, logs, traces, alerts, incidents, SLOs and reliability analytics.

Owner: SRE · Phase: P2 · Shown on dashboard by default: no

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| Centralized metrics | planned | Not built yet. |
| Logs | planned | Not built yet. |
| Distributed tracing | planned | Not built yet. |
| Alert management | planned | Not built yet. |
| Alert correlation | planned | Not built yet. |
| Incident management | planned | Not built yet. |
| Root cause analysis | planned | Not built yet. |
| SLO management | planned | Not built yet. |
| Error budgets | planned | Not built yet. |
| Service health | planned | Not built yet. |
| Dependency mapping | planned | Not built yet. |
| Runbook automation | planned | Not built yet. |
| Capacity planning | planned | Not built yet. |
| Reliability analytics | planned | Not built yet. |
| Post-incident reporting | planned | Not built yet. |

## Building this module

Copy `modules/_template/backend` into this folder, implement `register(app, ctx)`, and flip each
capability's `status` in `manifest.json` as it becomes real. The core loads it on restart.
