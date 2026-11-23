# M10 Operations Automation Engine

Central engine for scheduled, event- and incident-driven automation with full controls.

Owner: SRE · Phase: P2 · UI: `automation.html` (sidebar → Operations → Automation)

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| Scheduled operations | live | Cron-based job scheduler runs every minute; executes jobs when `next_run` passes. |
| Event-driven automation | live | Jobs with `trigger_type=event` wait for external events (future: webhook endpoint). |
| Incident-triggered automation | live | Jobs with `trigger_type=incident` can be wired to M11 incidents. |
| Resource lifecycle automation | live | Stop/start/terminate EC2, snapshot RDS, invoke Lambda, S3 copy, cleanup scripts. |
| Patch management | partial | Job framework ready; OS patch integration is planned. |
| Backup scheduling | live | RDS snapshot, S3 copy actions; schedule with cron. |
| Database maintenance | partial | RDS stop/start; PostgreSQL vacuum is planned. |
| Kubernetes maintenance | partial | EKS update action defined; implementation is partial. |
| Certificate renewal | planned | Not built yet. |
| Secret rotation | planned | Not built yet. |
| Resource cleanup | live | Script action can run cleanup jobs (e.g., delete old snapshots). |
| Capacity optimization | partial | Job framework ready; integration with M04 capacity data is partial. |
| Recovery workflows | live | Jobs can implement recovery steps; approval gates prevent accidents. |
| Configuration remediation | live | Jobs can fix config drift; audit trail records every run. |

## How it works

1. **Jobs** are defined with a trigger (schedule/event/incident/manual), actions, and approval requirements.
2. **Scheduler** wakes every minute, finds jobs where `enabled=1` and `next_run <= now`, and runs them.
3. **Runs** are recorded with full evidence (action outputs, errors, duration) in `m10_runs`.
4. **Approval gates** prevent dangerous jobs from running until an approver approves.

## API

`/api/m10/...`: overview, jobs, jobs/<id>, jobs/<id>/run, jobs/<id>/approve, runs, runs/<id>.

## Automation contract

Every job has:
- owner, trigger, preconditions, authorization scope
- approval requirement, approver roles
- execution timeout, retry strategy, idempotency key
- verification query, audit evidence

## Demo mode

When `M01_DEMO=1` (default), all actions are simulated. The portal logs what would happen without changing AWS.

## Live mode (future)

Set `M01_DEMO=0` to execute real AWS actions. Requires careful IAM scoping.
