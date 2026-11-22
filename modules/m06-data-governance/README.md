# M06 Enterprise Data Governance

Classification, ownership, lineage, quality, retention, residency and evidence for every data class.

Owner: Data Governance Office · Phase: P2 · Shown on dashboard by default: no

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| Data classification | planned | Not built yet. |
| Data ownership | planned | Not built yet. |
| Data stewardship | planned | Not built yet. |
| Metadata catalog | planned | Not built yet. |
| Data lineage | planned | Not built yet. |
| Data discovery | planned | Not built yet. |
| Data quality | planned | Not built yet. |
| Data retention | planned | Not built yet. |
| Data residency | planned | Not built yet. |
| Data masking | planned | Not built yet. |
| Encryption | planned | Not built yet. |
| Data access approval | planned | Not built yet. |
| Sensitive-data detection | planned | Not built yet. |
| Data archival | planned | Not built yet. |
| Secure data deletion | planned | Not built yet. |
| Compliance evidence | planned | Not built yet. |

## Design inputs

```json
{
  "governed_data": [
    "operational data",
    "application data",
    "audit records",
    "AI conversations",
    "embeddings",
    "prompts",
    "generated content"
  ]
}
```

## Building this module

Copy `modules/_template/backend` into this folder, implement `register(app, ctx)`, and flip each
capability's `status` in `manifest.json` as it becomes real. The core loads it on restart.
