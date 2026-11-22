# M15 Software Supply Chain & Configuration Management

Artifacts, SBOM, signing, provenance and configuration baselines.

Owner: Platform Security · Phase: P2 · Shown on dashboard by default: yes

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| Artifact registries | planned | Not built yet. |
| Container image management | planned | Not built yet. |
| SBOM | planned | Not built yet. |
| Software signing | planned | Not built yet. |
| Provenance | planned | Not built yet. |
| Dependency scanning | planned | Not built yet. |
| Configuration baselines | partial | Account security baseline component applied with every environment. (from M02) |
| Configuration drift | partial | Terraform drift check per component (live mode). (from M03) |
| Patch compliance | planned | Not built yet. |
| Release artifact management | planned | Not built yet. |

## Building this module

Copy `modules/_template/backend` into this folder, implement `register(app, ctx)`, and flip each
capability's `status` in `manifest.json` as it becomes real. The core loads it on restart.
