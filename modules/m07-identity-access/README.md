# M07 Identity & Access Management

SSO, MFA, least privilege, just-in-time access and access reviews for people and workloads.

Owner: Identity & Access · Phase: P2 · Shown on dashboard by default: yes

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| SSO | planned | Not built yet. |
| MFA | planned | Not built yet. |
| SAML and OIDC | planned | Not built yet. |
| SCIM provisioning | planned | Not built yet. |
| RBAC | partial | Six portal roles enforced by the backend; custom roles not built. (from M01) |
| ABAC | planned | Not built yet. |
| IAM role management | partial | Cross-account roles registered per AWS account; instance and node roles created by components. (from M01/M02) |
| Just-in-time access | planned | Not built yet. |
| Privileged access management | planned | Not built yet. |
| Temporary permissions | planned | Not built yet. |
| Access expiration | planned | Not built yet. |
| Access reviews | planned | Not built yet. |
| Approval workflows | live | Requests and infrastructure changes need an approver; no self-approval. (from M01/M03) |
| Automatic revocation | planned | Not built yet. |
| Service identities | planned | Not built yet. |
| Workload identity | partial | EKS Pod Identity agent installed on every cluster. (from M02) |
| Session auditing | partial | Logins, failures and every change are in the audit log. (from M01) |

## Design inputs

```json
{
  "principles": [
    "least privilege",
    "separation of duties"
  ]
}
```

## Building this module

Copy `modules/_template/backend` into this folder, implement `register(app, ctx)`, and flip each
capability's `status` in `manifest.json` as it becomes real. The core loads it on restart.
