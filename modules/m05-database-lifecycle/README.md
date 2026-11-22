# M05 Database Lifecycle & Management

Provision, protect, tune and retire relational, NoSQL, cache, search, warehouse and streaming databases.

Owner: Data Platform · Phase: P2 · Shown on dashboard by default: yes

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| Database catalog | planned | Not built yet. |
| Database provisioning | partial | DynamoDB tables through M02/M03. Other engines not built yet. (from M02) |
| Instance and cluster configuration | planned | Not built yet. |
| Database version management | planned | Not built yet. |
| Schema management | planned | Not built yet. |
| Database user and role management | planned | Not built yet. |
| Credential rotation | planned | Not built yet. |
| Encryption | partial | DynamoDB server-side encryption always on. (from M03) |
| Backup and restore | planned | Not built yet. |
| Point-in-time recovery | partial | DynamoDB PITR on by default; required in production by policy FDE-009. (from M03) |
| Replication | planned | Not built yet. |
| High availability | planned | Not built yet. |
| Failover | planned | Not built yet. |
| Performance monitoring | planned | Not built yet. |
| Query analysis | planned | Not built yet. |
| Index recommendations | planned | Not built yet. |
| Capacity forecasting | planned | Not built yet. |
| Database patching | planned | Not built yet. |
| Database upgrades | planned | Not built yet. |
| Database migration | planned | Not built yet. |
| Data archival | planned | Not built yet. |
| Secure decommissioning | partial | DynamoDB deletion protection in production; destroy needs approval. (from M02) |

## Design inputs

```json
{
  "categories": {
    "relational": [
      "Aurora PostgreSQL/MySQL",
      "RDS PostgreSQL/MySQL"
    ],
    "nosql": [
      "DynamoDB",
      "DocumentDB"
    ],
    "cache": [
      "ElastiCache Valkey/Redis",
      "MemoryDB"
    ],
    "search": [
      "OpenSearch"
    ],
    "warehouse": [
      "Redshift Serverless"
    ],
    "streaming": [
      "MSK (Kafka)",
      "Kinesis Data Streams"
    ]
  }
}
```

## Building this module

Copy `modules/_template/backend` into this folder, implement `register(app, ctx)`, and flip each
capability's `status` in `manifest.json` as it becomes real. The core loads it on restart.
