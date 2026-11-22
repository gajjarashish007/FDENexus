# M04 Kubernetes & Container Platform Management

Day-2 operations for EKS and any kubeconfig cluster, inside the central portal (`kubernetes.html`).
Cluster creation, node group sizing and version upgrades are Terraform changes in M02/M03; this module operates what is running.

## Connecting clusters
- **From M02:** every `eks-cluster` component in an environment appears automatically (same account, region, tier).
- **Existing EKS:** Admin, then Add cluster, then EKS. Pick the AWS account, region and name (List clusters calls eks:ListClusters in live mode).
  The portal calls `eks:DescribeCluster` with the account role and writes a per-cluster kubeconfig (`data/m04/<id>.kubeconfig`, mode 600)
  whose auth is `aws eks get-token` run with that role's temporary credentials. The role needs an **EKS access entry** (e.g. `AmazonEKSClusterAdminPolicy`, or a read-only policy plus the actions you allow).
- **kubeconfig context:** any context in the portal host user's kubeconfig (kind, k3s, other clouds). Works in simulation mode too.

Needs `kubectl` on the host (`M04_KUBECTL` to override) and, for EKS, the `aws` CLI.

## Who can do what
| Action | Roles |
|---|---|
| Overview, pod/node/workload/network/storage lists, events, diagnose | everyone signed in |
| Logs, YAML, ConfigMap contents | everyone except viewer |
| Delete pod, rollout restart, scale | admin, operator, developer (developer not in production; scale to 0 in production: admin) |
| Failed-pod cleanup | admin, operator |
| Run command in pod | admin, operator (production: admin only); admins can switch exec off |
| Register / remove clusters | admin |

Every change is in the audit log (`k8s_*` actions). Exec commands are logged with password/token-looking values masked.

## API (`/api/m04`)
`GET /clusters`, `POST /clusters`, `DELETE /clusters/<id>`, `POST /clusters/<id>/test`, `GET /contexts`, `GET /discover?account=&region=`,
`GET /c/<id>/overview`, `GET /c/<id>/list/<kind>` (pods, deployments, statefulsets, daemonsets, cronjobs, nodes, services, ingresses, configmaps, hpa, pvc, resourcequotas),
`GET /c/<id>/events`, `GET /c/<id>/describe/<kind>/<name>`, `GET /c/<id>/yaml/<kind>/<name>`, `GET /c/<id>/logs/<ns>/<pod>`, `GET /c/<id>/diagnose/<ns>/<pod>`,
`POST /c/<id>/pods/<ns>/<pod>/delete`, `POST /c/<id>/restart`, `POST /c/<id>/scale`, `POST /c/<id>/cleanup`, `POST /c/<id>/exec`, `PUT /settings`.

## Capabilities
| Capability | Status | Notes |
|---|---|---|
| Cluster lifecycle | partial | Create and delete EKS through M02/M03 (Terraform); register existing EKS or kubeconfig clusters and test the connection here. |
| Node pool management | partial | Node list with instance type, zone, node group, capacity type, taints and pressure. Size and type changes go through the EKS Terraform change. |
| Autoscaling | partial | HPA view with current vs target metrics and an at-max flag. Cluster Autoscaler/Karpenter setup not built. |
| Workload deployment | partial | Rollout restart (deployment, statefulset, daemonset) with rollout wait, scale, describe, YAML. New deployments through GitOps are not built. |
| Namespace management | partial | Namespace filter and system-namespace hiding. Creating namespaces with quotas is not built. |
| RBAC | partial | Portal roles decide who can read logs, change workloads and run commands in pods; EKS access uses each account's IAM role. Kubernetes RoleBindings are not managed. |
| Network policies | planned | Not built yet. |
| Ingress management | partial | Ingress and Service list with class, hosts, load balancer address and TLS flag; describe. |
| Storage and PVC lifecycle | partial | PVC list with status, capacity, storage class; describe. |
| Container image scanning | planned | Not built yet. |
| Resource quotas | partial | Quota usage per namespace (read-only). |
| Pod health | live | Pod status rules match kubectl, problem-pod list, diagnosis hints (OOMKilled, crash loop, image pull, config errors, readiness), logs with previous container, failed-pod cleanup. |
| Scheduling analysis | live | Pending pods are explained from FailedScheduling events: insufficient CPU/memory, taints/affinity, unbound PVCs. |
| Kubernetes upgrades | partial | Version skew warning between control plane and nodes; the version change itself is an M02/M03 Terraform update. |
| Cluster backup and recovery | planned | Not built yet. |

`reference/pod-legacy/` holds the original pod dashboard; see `reference/README.md` for what was ported and what was left out.
