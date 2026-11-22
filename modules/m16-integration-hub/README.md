# M16 Enterprise Integration Hub

Standard connectors for identity, CI/CD, ITSM, monitoring, messaging, docs, source control, cloud, security and cost tools.

Owner: Platform Engineering · Phase: P2 · Shown on dashboard by default: yes

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| Identity providers | planned | Not built yet. |
| CI/CD systems | partial | GitLab CI pipeline template. (from M03) |
| ITSM platforms | planned | Not built yet. |
| Change management | planned | Not built yet. |
| Monitoring platforms | planned | Not built yet. |
| Messaging systems | planned | Not built yet. |
| Documentation systems | planned | Not built yet. |
| Source control | partial | GitLab: commit, merge request, status and merge. (from M03) |
| Cloud-native services | partial | AWS through boto3 (accounts, EC2, regions) and Terraform. (from M01/M02) |
| Security tools | planned | Not built yet. |
| Cost management systems | planned | Not built yet. |

## Building this module

Copy `modules/_template/backend` into this folder, implement `register(app, ctx)`, and flip each
capability's `status` in `manifest.json` as it becomes real. The core loads it on restart.
