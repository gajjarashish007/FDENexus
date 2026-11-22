# Pod Dashboard (EKSense)

Web portal for **EKS cluster operations**: pods, deployments, nodes, services, rollout restarts, version lookup, Route53 traffic migration, user/RBAC admin, and audit logging.

**Primary entry:** unified portal on **`http://<host>:5000`** — run from repo root:

```bash
bash run-portal.sh
# or: cd validator && ./run.sh
```

EKS features are at **`/eks/`** on the same port (embedded in the **EKS Pod Dashboard** tab). Standalone loopback **`http://127.0.0.1:8080`** is only used internally by the proxy.

| Item | Default |
|------|---------|
| **Unified portal** | `http://<host>:5000/` → **EKS Pod Dashboard** tab |
| **EKS direct path** | `http://<host>:5000/eks/dashboard.html` |
| **Legacy standalone** | `http://<host>:8080/login` (optional; `bash start-pod-server.sh start`) |
| **Port (public)** | `5000` via validator |
| **Default login** | `admin` (password in `.pod-dashboard.env`) |

When using `/eks/` on port 5000, the header **Cloud Portal** link returns to `/`. Nested validator iframe was removed.

> **Important:** Always start/stop the server with `start-pod-server.sh`. Do **not** run `python3 pod-server.py` directly (port conflicts and auth issues).

---

## Table of contents

1. [Quick start](#quick-start)
2. [How to run / stop / restart](#how-to-run--stop--restart)
3. [Login & users](#login--users)
4. [How to change cluster](#how-to-change-cluster)
5. [How to add a cluster (same account)](#how-to-add-a-cluster-same-account)
6. [How to add a cluster in a different AWS account](#how-to-add-a-cluster-in-a-different-aws-account)
7. [Multi-cluster rollout restart](#multi-cluster-rollout-restart)
8. [Activity / audit log](#activity--audit-log)
9. [Configuration](#configuration)
10. [Deploy updates to EC2](#deploy-updates-to-ec2)
11. [Troubleshooting](#troubleshooting)
12. [Project layout](#project-layout)

---

## Quick start

### First-time install (EC2 / Linux)

```bash
cd /root/cloud-infrastructure/pod   # or your clone path
bash install.sh
```

This installs Python dependencies, initializes the RBAC database, and starts the server.

Open in browser:

```
http://<EC2-PUBLIC-IP>:8080/login
```

### Dependencies only (no start)

```bash
bash install.sh --deps-only
bash start-pod-server.sh start
```

### Prerequisites

| Component | Required | Notes |
|-----------|----------|-------|
| **Python 3** | Yes | Auto-installed by `install.sh` |
| **kubectl** | Yes | For pods, deployments, nodes, etc. |
| **kubeconfig** | Yes | `~/.kube/config` or set `KUBECONFIG` |
| **AWS CLI** | Recommended | Cluster discovery + `update-kubeconfig` |
| **AWS credentials** | Yes | EC2 IAM role and/or `~/.aws/credentials` |
| **boto3** | Yes | Route53 traffic migration |

Verify:

```bash
kubectl version --client
kubectl config current-context
aws sts get-caller-identity
curl -s http://127.0.0.1:8080/api/health
```

---

## How to run / stop / restart

```bash
cd /root/cloud-infrastructure/pod

bash start-pod-server.sh start          # start (skip if already healthy)
bash start-pod-server.sh stop           # stop
bash start-pod-server.sh restart        # stop + start (after code changes)
bash start-pod-server.sh force-restart  # kill ALL instances + start (use after deploy)
bash start-pod-server.sh status         # health + port check
bash start-pod-server.sh diagnose       # full troubleshoot output
bash start-pod-server.sh reset-admin-password  # sync admin password from env
```

**Logs:** `pod-server.log` (or `$POD_LOGFILE`)

**Health check:**

```bash
curl -s http://127.0.0.1:8080/api/health | python3 -m json.tool
```

**Smoke test:**

```bash
bash check-server.sh
```

### Systemd (optional, auto-start on boot)

```bash
sudo cp pod-server.service /etc/systemd/system/
# Edit WorkingDirectory, User, POD_AUTH_PASSWORD, paths
sudo systemctl daemon-reload
sudo systemctl enable pod-server
sudo systemctl start pod-server
sudo systemctl status pod-server
```

---

## Login & users

Authentication is enabled by default. Credentials come from:

1. `$ROOT/.pod-dashboard.env` or `~/.pod-dashboard.env`
2. `data/auth.defaults` (written on each server start)

Example `.pod-dashboard.env`:

```bash
POD_AUTH_USER=admin
POD_AUTH_PASSWORD=YourSecurePassword
POD_AUTH_SESSION_HOURS=24
POD_RBAC_DB=/root/cloud-infrastructure/pod/data/rbac.db
```

**Admin panel** (sidebar → Admin Panel):

- Create / edit / delete users
- Set per-module permissions (pods, deployments, admin, etc.)
- **Activity Log** — login, logout, pod restarts, deployment restarts
- **Clusters tab** — manually register EKS clusters (★ in sidebar)

Reset admin password:

```bash
export POD_AUTH_PASSWORD='NewPassword'
bash start-pod-server.sh reset-admin-password
bash start-pod-server.sh force-restart
```

---

## How to change cluster

The portal manages **one active kubectl context** at a time. All sections (Pods, Deployments, Nodes, etc.) show data for the selected cluster.

### Method 1 — UI (recommended)

1. Log in to the dashboard.
2. In the **left sidebar**, find **EKS Cluster** dropdown (`envSelect`).
3. Select the target cluster.
4. Wait a few seconds — the page refreshes pods, namespaces, and overview.

The server runs:

```bash
aws eks update-kubeconfig --name <cluster> --region <region> --alias <cluster>
kubectl config use-context <cluster>
```

### Method 2 — CLI (manual)

```bash
aws eks update-kubeconfig --region us-east-2 --name my-cluster-name --alias my-cluster-name
kubectl config use-context my-cluster-name
kubectl get nodes
```

Then refresh the dashboard browser tab.

### Method 3 — API

```bash
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8080/api/clusters/switch \
  -H 'Content-Type: application/json' \
  -d '{"name":"my-cluster-name","region":"us-east-2","roleArn":"arn:aws:iam::123456789012:role/EKSReadRole"}'
```

### Cluster list sources

The dropdown merges clusters from:

| Source | How it appears |
|--------|----------------|
| **AWS EKS API** | Auto-discovered in configured regions |
| **kubeconfig** | Contexts already in `~/.kube/config` |
| **Admin registry** | Manually added (marked with ★) |

List clusters:

```bash
curl -s -b /tmp/cookies.txt http://127.0.0.1:8080/api/clusters | python3 -m json.tool
```

---

## How to add a cluster (same account)

Use this when the cluster is in the **same AWS account** the EC2 instance can already access.

### Option A — Let the portal discover it

1. Ensure the EC2 IAM role (or `aws configure`) can call `eks:ListClusters` and `eks:DescribeCluster`.
2. Set regions to scan (optional):

   ```bash
   # In .pod-dashboard.env
   export POD_EKS_REGIONS=us-east-2,us-east-1,us-west-2
   export POD_AWS_REGION=us-east-2
   ```

3. Restart server and refresh dashboard — cluster appears in sidebar.

### Option B — Add kubeconfig context once

```bash
aws eks update-kubeconfig --region us-east-2 --name NEW-CLUSTER-NAME --alias NEW-CLUSTER-NAME
kubectl config get-contexts
```

Refresh dashboard — cluster appears under kubeconfig discovery.

### Option C — Admin Panel registry

1. **Sidebar** → **Manage Clusters** (under the EKS cluster dropdown), **or** **Admin Panel** → **Clusters** tab.
2. Enter **Name**, **Region**, optional **Label**, and optional **IAM Role ARN** (for cross-account access).
3. Click **Add Cluster**.

> **Note:** Manage Clusters is visible to **admin** / **super_admin** users. Log in with the `admin` account (see `POD_AUTH_USER` in `.pod-dashboard.env`).

Registry file: `data/clusters_registry.json`

Example registry entry with IAM role:

```json
{
  "id": 1,
  "name": "cluster-b",
  "region": "us-east-2",
  "label": "Account B Production",
  "roleArn": "arn:aws:iam::123456789012:role/EKSReadRole",
  "enabled": true
}
```

When a role ARN is set, switching clusters runs:

```bash
aws eks update-kubeconfig --name cluster-b --region us-east-2 --role-arn arn:aws:iam::123456789012:role/EKSReadRole --alias cluster-b
```

This is useful when AWS discovery is slow, you want a friendly label, or you need cross-account EKS access without manual kubeconfig setup.

---

## How to add a cluster in a different AWS account

The dashboard uses the **AWS credentials available on the EC2 host** when switching clusters (`aws eks update-kubeconfig`). To work with another account you must give the server access to that account's EKS API.

### Understanding the limitation

- Switching cluster runs `aws eks update-kubeconfig` with the **current default credentials**.
- If cluster `prod-cluster` is in **Account B** but the server only has **Account A** credentials, the UI switch will fail with an access error.

### Pattern 1 — Multiple kubeconfig contexts (recommended)

Pre-register each cluster's context using the correct AWS profile, then use the sidebar to switch.

**On the EC2 host:**

```bash
# Account A (default profile — already configured)
aws eks update-kubeconfig --region us-east-2 --name cluster-a --alias cluster-a

# Account B (separate profile)
aws configure --profile account-b
# Enter Account B access key / secret (or use SSO: aws configure sso --profile account-b)

AWS_PROFILE=account-b aws eks update-kubeconfig \
  --region us-east-2 \
  --name cluster-b \
  --alias cluster-b

# Account C
AWS_PROFILE=account-c aws eks update-kubeconfig \
  --region eu-west-1 \
  --name cluster-c \
  --alias cluster-c

kubectl config get-contexts
```

**Add to portal registry (optional but recommended):**

1. Admin Panel → Clusters → add `cluster-b` / `us-east-2`, `cluster-c` / `eu-west-1`.
2. Or edit `data/clusters_registry.json` directly.

**Switch in UI:** select `cluster-b` from sidebar. The server runs `update-kubeconfig` for that name/region — **your default credentials must have cross-account EKS access**, OR contexts were already merged (see Pattern 2).

### Pattern 2 — Cross-account IAM role (recommended)

Best for EC2 in a **shared services account** accessing EKS in other accounts. The portal supports this directly via the **IAM Role ARN** field in Admin → Clusters.

1. In **Account B**, create an IAM role `EKSReadRole` trusted by Account A's EC2 role.
2. Attach policies allowing `eks:DescribeCluster`, `eks:ListClusters`, and STS `AssumeRole` from Account A.
3. In the portal: **Admin Panel** → **Clusters** → add the cluster with:
   - **Name:** `cluster-b`
   - **Region:** `us-east-2`
   - **IAM Role ARN:** `arn:aws:iam::ACCOUNT_B_ID:role/EKSReadRole`
4. Select `cluster-b` from the sidebar — the server runs:

   ```bash
   aws eks update-kubeconfig --name cluster-b --region us-east-2 \
     --role-arn arn:aws:iam::ACCOUNT_B_ID:role/EKSReadRole --alias cluster-b
   ```

Multi-cluster rollout restarts also use the stored role ARN when switching to each cluster.

**Alternative — AWS profile in `~/.aws/config`:**

   ```ini
   [profile account-b-eks]
   role_arn = arn:aws:iam::ACCOUNT_B_ID:role/EKSReadRole
   source_profile = default
   region = us-east-2
   ```

   ```bash
   AWS_PROFILE=account-b-eks aws eks update-kubeconfig --name cluster-b --region us-east-2 --alias cluster-b
   ```

   Then register the cluster in Admin → Clusters (role ARN optional if profile handles assume-role).

### Pattern 3 — Single alternate account via env

If **all** EKS and Route53 calls should use one non-default profile:

```bash
# .pod-dashboard.env
export AWS_PROFILE=account-b
export POD_AWS_REGION=us-east-2
```

```bash
bash start-pod-server.sh force-restart
```

> `POD_AWS_PROFILE` is used for **Route53** traffic migration. EKS commands use the standard `AWS_PROFILE` environment variable.

### Pattern 4 — Separate kubeconfig file per account

```bash
export KUBECONFIG=/root/.kube/config-account-a:/root/.kube/config-account-b
```

Merge order matters — first file wins on context name conflicts. Use unique `--alias` names per cluster.

### Checklist for a new cross-account cluster

| Step | Action |
|------|--------|
| 1 | Create/configure AWS profile or IAM role for target account |
| 2 | `AWS_PROFILE=... aws eks update-kubeconfig --name X --region Y --alias X` |
| 3 | `kubectl --context X get nodes` (verify access) |
| 4 | Admin Panel → Clusters → add name + region (★ in sidebar) |
| 5 | Select cluster in sidebar dropdown |
| 6 | Confirm Pods / Deployments load |

### Filter cluster list (optional)

Show only clusters matching a name prefix:

```bash
export POD_EKS_CLUSTER_PREFIX=arlo-
bash start-pod-server.sh restart
```

---

## Multi-cluster rollout restart

On the **Deployments** page:

1. Check one or more **Rollout restart clusters** at the top.
2. Select deployments with row checkboxes.
3. Click **Restart Selected (N)**.

Per-row **Restart** buttons restart a single deployment on selected clusters.

On the **Pods** page:

- Use **Restart** (per row) or **Restart Selected** — runs `kubectl delete pod` (controller recreates the pod).

---

## Activity / audit log

Track **logins**, **logouts**, **pod restarts**, and **deployment restarts**:

- **UI:** Admin Panel → **Activity Log** tab  
  Filter: `Login / Logout`, `Pods`, `Deployments`, or by username.

- **Database:**

  ```bash
  sqlite3 data/rbac.db "
    SELECT datetime(created_at,'unixepoch','localtime') AS time,
           actor_username, action, target_username, details
    FROM audit_logs
    ORDER BY created_at DESC LIMIT 50;"
  ```

| Action | Meaning |
|--------|---------|
| `auth.login` | User signed in |
| `auth.logout` | User signed out |
| `auth.login_failed` | Failed login attempt |
| `pod.delete` | Pod restart (delete) |
| `deployment.restart` | Single deployment rollout restart |
| `deployment.restart_batch` | Bulk deployment restart |
| `cluster.switch` | Cluster changed in UI |

---

## Configuration

Environment variables (set in `.pod-dashboard.env` or export before start):

### Server & auth

| Variable | Default | Description |
|----------|---------|-------------|
| `POD_PORT` | `8080` | HTTP port |
| `POD_AUTH_USER` | `admin` | Admin username |
| `POD_AUTH_PASSWORD` | _(required)_ | Admin password — set in `.pod-dashboard.env` (no hardcoded default) |
| `POD_AUTH_SESSION_HOURS` | `24` | Session lifetime (hours) |
| `POD_RBAC_DB` | `data/rbac.db` | SQLite RBAC + audit DB |
| `KUBECONFIG` | `~/.kube/config` | Kubernetes config path |

### AWS & clusters

| Variable | Default | Description |
|----------|---------|-------------|
| `POD_AWS_REGION` | `us-east-2` | Primary AWS region |
| `POD_AWS_PROFILE` | _(empty)_ | AWS profile for Route53 |
| `AWS_PROFILE` | _(empty)_ | AWS profile for CLI/EKS (standard AWS env) |
| `POD_EKS_REGIONS` | _(multi-region list)_ | Comma-separated regions for EKS discovery |
| `POD_EKS_CLUSTER_PREFIX` | _(empty)_ | Filter cluster names by prefix |
| `POD_CLUSTERS_REGISTRY` | `data/clusters_registry.json` | Manual cluster registry path |

### Infrastructure Validator (embedded)

Sidebar → **Infrastructure Validator** embeds the full validator UI (port **5000** by default). Pod auth and validator auth are separate — sign in inside the iframe when prompted.

| Variable | Default | Description |
|----------|---------|-------------|
| `POD_VALIDATOR_ENABLED` | `1` | Show validator nav + embed (`0` to hide) |
| `POD_VALIDATOR_UPSTREAM` | `http://127.0.0.1:5000` | Server-side health check URL |
| `POD_VALIDATOR_PORT` | `5000` | Browser iframe port when `POD_VALIDATOR_PUBLIC_URL` is empty (uses same host as dashboard) |
| `POD_VALIDATOR_PUBLIC_URL` | _(empty)_ | Override iframe URL (e.g. `https://ops.example.com:5000`) |
| `POD_VALIDATOR_AUTO_START` | `0` | Run `../validator/run.sh` on pod-server start if upstream is down |
| `POD_VALIDATOR_HTTPS` | `0` | Set `1` when dashboard is served over HTTPS (iframe scheme) |

Start validator manually:

```bash
cd ../validator && ./run.sh
```

Open **TCP 5000** in the security group if users reach the dashboard from outside the instance.

Grant access in **Admin Panel → user permissions → Infrastructure Validator (read)**.

### Caching (seconds)

| Variable | Default | Resource |
|----------|---------|----------|
| `POD_PODS_CACHE_TTL` | `45` | Pods |
| `POD_DEPLOYMENTS_CACHE_TTL` | `90` | Deployments |
| `POD_NODES_CACHE_TTL` | `180` | Nodes |
| `POD_SERVICE_CACHE_TTL` | `90` | All Services |
| `POD_K8S_HTML_CACHE_TTL` | `120` | Services/Ingress/CM/HPA |
| `POD_TRAFFIC_CACHE_TTL` | `300` | Route53 traffic |
| `POD_VERSION_CACHE_TTL` | `45` | Service versions |

Example `.pod-dashboard.env`:

```bash
POD_AUTH_USER=admin
POD_AUTH_PASSWORD=YourSecurePassword
POD_AUTH_SESSION_HOURS=24
POD_AWS_REGION=us-east-2
POD_EKS_REGIONS=us-east-2,us-east-1,us-west-2
AWS_PROFILE=default
POD_AWS_PROFILE=default
KUBECONFIG=/root/.kube/config
```

Apply changes:

```bash
bash start-pod-server.sh force-restart
```

---

## Deploy updates to EC2

```bash
cd /root/cloud-infrastructure/pod

# Copy updated files (git pull, scp, etc.)
git pull   # or scp/rsync from your workstation

bash start-pod-server.sh force-restart
bash check-server.sh
```

Hard-refresh browser: `Ctrl+Shift+R`

Typical files to deploy:

- `pod-server.py`, `pod_auth.py`, `pod_rbac.py`, `pod_clusters.py`, `pod_cache.py`
- `dashboard.html`, `login.html`
- `start-pod-server.sh`

---

## Troubleshooting

### Cannot log in / session expires immediately

```bash
bash start-pod-server.sh reset-admin-password
bash start-pod-server.sh force-restart
```

Use the **same URL** for login and dashboard (don't mix IP and hostname).

Check: `ls -la data/rbac.db` (must be writable).

### Port 8080 in use

```bash
bash start-pod-server.sh force-restart
# or
bash start-pod-server.sh kill-port
```

### Cluster switch fails

```bash
aws sts get-caller-identity
aws eks describe-cluster --name CLUSTER --region REGION
aws eks update-kubeconfig --name CLUSTER --region REGION --alias CLUSTER
kubectl get nodes
```

For cross-account: verify profile/role (see [different account](#how-to-add-a-cluster-in-a-different-aws-account)).

### No clusters in dropdown

- Check IAM: `eks:ListClusters` in scanned regions.
- Set `POD_EKS_REGIONS`.
- Add manually: Admin → Clusters.
- Pre-load kubeconfig: `aws eks update-kubeconfig ...`

### Pods / deployments empty

```bash
kubectl config current-context
kubectl get pods -A
```

### Permissions error in Admin Panel

```bash
bash start-pod-server.sh force-restart
# Ensure pod_rbac.py is latest (includes _empty_permission fix)
```

### Route53 traffic migration empty

```bash
aws sts get-caller-identity
export POD_AWS_PROFILE=your-profile   # if needed
bash start-pod-server.sh restart
```

---

## Project layout

```
pod/
├── install.sh                 # One-click install
├── start-pod-server.sh        # Start/stop/restart (USE THIS)
├── check-server.sh            # Health + login smoke test
├── pod-lib.sh                 # Shared install helpers
├── pod-server.py              # Main HTTP server
├── pod_auth.py                # Session login
├── pod_rbac.py                # Users, permissions, audit log
├── pod_clusters.py            # Manual cluster registry
├── pod_cache.py               # Per-resource cache TTLs
├── version_cache.py           # Service version SQLite cache
├── route53_traffic.py         # Route53 lookup
├── service_versions.py        # Version API
├── dashboard.html             # Main UI
├── login.html                 # Login page
├── requirements.txt           # Python deps (boto3)
├── data/
│   ├── rbac.db                # Users + audit log + sessions
│   ├── auth.defaults          # Persisted auth env
│   ├── clusters_registry.json # Manual clusters (★)
│   ├── traffic_migration_hosts.json
│   └── service_version_catalog.json
└── pod-server.service         # systemd unit (optional)
```

---

## Key API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /login` | Login page |
| `GET /dashboard.html` | Main dashboard |
| `POST /api/auth/login` | Sign in |
| `GET /api/auth/me` | Current user + permissions |
| `GET /api/clusters` | List clusters |
| `POST /api/clusters/switch` | Switch active cluster |
| `GET /api/pods` | Pod list (JSON, cached) |
| `GET /api/deployments` | Deployments (JSON, cached) |
| `POST /rollout-restart-deployment` | Restart one deployment |
| `POST /rollout-restart-deployments` | Bulk deployment restart |
| `POST /delete` | Delete/restart one pod |
| `GET /api/admin/audit` | Activity log |
| `GET /api/admin/users/{id}/permissions` | User permissions |
| `GET /api/health` | Server health |

---

## License

Internal infrastructure tooling — Arlo / Comcast.
