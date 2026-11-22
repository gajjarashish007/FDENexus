# M02 Cloud Account & Infrastructure Lifecycle

Create, register, baseline and retire accounts and infrastructure. M02 decides **what** to build and validates the
request; M03 turns it into a reviewed Terraform/Atmos change. M02 never creates AWS resources directly.

## Pages
- `environments.html`: environments list, create wizard (account and tier, region and AZs, CIDR plan and NAT, review), details, stack versions, rollback, decommission, AWS account provisioning (admins).
- `launch.html`: launch EC2, DynamoDB, S3 static website, S3 bucket, EFS, EKS, ALB, Route 53 zone or ACM certificate into an environment.
- `aws-accounts.html` (M01): onboarding and registration of AWS accounts.

## API (`/api/m02`)
| Method | Path | Notes |
|---|---|---|
| GET | `/regions?account=` | Built-in list in simulation; `describe_regions`/`describe_availability_zones` per account in live mode |
| GET | `/cidr-plan?cidr=&azs=&account=` | Subnet plan + overlap check; `/cidr-suggest?account=` returns a free /16 |
| GET | `/resource-types` | Field schema that drives the launch wizard |
| GET/POST | `/environments`, `/environments/preview` | Create = VPC + account baseline change |
| GET | `/environments/<id>` | Components, in-flight changes, versions |
| POST | `/resources`, `/resources/preview` | One component instance in an environment |
| POST | `/environments/<id>/decommission` | `{instance}` for one resource, `{confirm: <id>}` for the whole environment (admin/operator) |
| POST | `/accounts/provision` | New member account via AWS Organizations (admin) |

## Rules enforced here
- Viewers are read-only. Only admins and operators request production changes or decommission.
- Production needs 2+ AZs. CIDRs must be private /16-/24 and not overlap another environment in the account.
- VPC and baseline are removed last (decommission the whole environment).

## Capabilities
| Capability | Status | How |
|---|---|---|
| Cloud account onboarding | live | Connect accounts with a cross-account IAM role (AssumeRole + external ID) or the instance role; connection test. |
| Account provisioning | partial | New member accounts through AWS Organizations (aws-account component). Needs the management account and a live apply. |
| Account registration | live | Registered accounts are stored, tested and selectable per user. |
| Environment creation | live | Wizard creates VPC + security baseline as one reviewed change. |
| Region and availability zone management | live | Region and AZ picker; real AZs and zone IDs per account in live mode, built-in list in simulation. |
| VPC and networking | live | CIDR planner, overlap check per account, NAT none/single/per-AZ, flow logs, S3 endpoint, locked default SG. |
| Compute provisioning | live | EC2 with IMDSv2, encrypted gp3, Session Manager role, dedicated security group. |
| Storage provisioning | live | S3 bucket, S3 static website (CloudFront or website endpoint), EFS. |
| Kubernetes infrastructure | live | EKS with private API, KMS secrets, audit logs, managed node group, core add-ons. |
| Load balancing | live | ALB with HTTPS redirect and TLS 1.3 policy. |
| DNS and certificates | live | Route 53 zones and ACM certificates with automatic DNS validation. |
| Infrastructure decommissioning | live | Remove one resource or a whole environment; destroys run in dependency order after approval. |
