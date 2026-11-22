# M13 Deployment & Change Management

Change requests, risk, approvals, windows, pipelines, verification and rollback.

Owner: Release Management · Phase: P2 · Shown on dashboard by default: yes

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| CI/CD integrations | partial | GitLab merge requests and a CI pipeline template. (from M03) |
| Change requests | live | Every infrastructure change is a tracked change request. (from M03) |
| Approval workflows | live | Auto-approve low-risk non-production; humans approve the rest. (from M03) |
| Risk classification | live | Low/medium/high from tier, operation and policy warnings. (from M03) |
| Deployment windows | planned | Not built yet. |
| Scheduling | planned | Not built yet. |
| Pipeline execution | partial | GitLab CI validate/plan/apply; production apply is manual. (from M03) |
| Deployment verification | planned | Not built yet. |
| Rollback | live | Roll back to a previous stack version. (from M03) |
| Change history | live | Stack versions and change log per environment. (from M03) |
| Conflict detection | live | Concurrent edits to the same component are detected; one open MR per environment. (from M03) |
| Release management | planned | Not built yet. |

## Building this module

Copy `modules/_template/backend` into this folder, implement `register(app, ctx)`, and flip each
capability's `status` in `manifest.json` as it becomes real. The core loads it on restart.
