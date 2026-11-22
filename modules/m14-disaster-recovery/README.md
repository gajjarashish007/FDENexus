# M14 Disaster Recovery & Business Continuity

Backup policy, recovery objectives, failover and DR exercises with evidence.

Owner: SRE · Phase: P2 · Shown on dashboard by default: yes

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| Backup policies | partial | Backups on by default: EFS AWS Backup, DynamoDB PITR, S3 versioning. (from M02) |
| Backup validation | planned | Not built yet. |
| Recovery objectives | planned | Not built yet. |
| RTO and RPO management | planned | Not built yet. |
| Cross-region recovery | planned | Not built yet. |
| Replication | planned | Not built yet. |
| Failover | planned | Not built yet. |
| Failback | planned | Not built yet. |
| Recovery runbooks | planned | Not built yet. |
| Disaster recovery exercises | planned | Not built yet. |
| Evidence collection | planned | Not built yet. |
| Platform-level disaster recovery | planned | Not built yet. |

## Building this module

Copy `modules/_template/backend` into this folder, implement `register(app, ctx)`, and flip each
capability's `status` in `manifest.json` as it becomes real. The core loads it on restart.
