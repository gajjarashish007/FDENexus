# M08 Security & Compliance Management

Policy-as-code, posture, vulnerabilities, secrets, encryption and audit evidence.

Owner: Security Engineering · Phase: P2 · Shown on dashboard by default: yes

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| Security policy engine | partial | Deny/warn engine for infrastructure changes. (from M03) |
| Policy-as-Code | partial | 16 IaC rules evaluated before every change. (from M03) |
| Cloud security posture management | planned | Not built yet. |
| Vulnerability scanning | planned | Not built yet. |
| Infrastructure security scanning | partial | Built-in rules; Checkov/Trivy when installed. (from M03) |
| Container security | planned | Not built yet. |
| Image signing | planned | Not built yet. |
| SBOM management | planned | Not built yet. |
| Secrets management | planned | Not built yet. |
| Certificate lifecycle | partial | ACM certificates with DNS validation; ACM renews automatically. (from M02) |
| KMS and encryption | partial | Components enforce encryption at rest (EBS, S3, EFS, DynamoDB, EKS secrets). (from M02) |
| Network security | planned | Not built yet. |
| Public exposure detection | partial | Rules block public SSH/RDP, public S3 websites in production, open EKS endpoints. (from M03) |
| Compliance monitoring | planned | Not built yet. |
| Security findings | planned | Not built yet. |
| Risk scoring | partial | Every change gets low/medium/high risk. (from M03) |
| Remediation workflows | planned | Not built yet. |
| Security audit evidence | planned | Not built yet. |

## Design inputs

```json
{
  "frameworks": [
    "CIS Benchmarks",
    "NIST CSF 2.0",
    "ISO 27001:2022",
    "SOC 2"
  ]
}
```

## Building this module

Copy `modules/_template/backend` into this folder, implement `register(app, ctx)`, and flip each
capability's `status` in `manifest.json` as it becomes real. The core loads it on restart.
