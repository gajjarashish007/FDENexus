# M01 · Platform Experience & Self-Service Portal

The first module of **FDE Nexus**: the governed front door where engineers request,
approve, deploy and track cloud resources. Real, runnable code (Flask + SQLite +
vanilla JS). Infrastructure actions are **simulated in demo mode**, so it runs with
zero AWS setup.

> This module implements all eleven M01 capabilities from the specification:
> unified dashboard, role-based navigation, service catalog, request management,
> approval center, deployment dashboard, resource inventory, operational health,
> notifications, global search, and an AI conversational assistant.

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.10+** | `python3 --version` |
| **pip** | ships with Python |
| A modern **web browser** | Chrome, Edge, Firefox, Safari |
| (Optional) **AWS account/CLI** | Only if you later set `M01_DEMO=0` to wire real backends. Not needed for the demo. |

Python packages (installed by `run.sh` or `pip install -r requirements.txt`):
`Flask`, `flask-cors`, `PyJWT`, `boto3` (boto3 is only used when demo mode is off).

## Run it

```bash
cd modules/m01-self-service-portal
./run.sh
# then open http://localhost:5001
```

Or manually:

```bash
cd modules/m01-self-service-portal
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python backend/app.py
```

**First-run login:** `admin` / `admin` (change via env vars below). The bootstrap
admin is created only when the database is empty.

## How the flow works

1. **Sign in** (or request access → an admin approves you).
2. **Service Catalog** → pick an item → fill the guided form → **Submit**.
3. Low-risk items are **auto-approved**; others go to the **Approval Center**.
4. An approver reviews the plan and approves (a requester cannot approve their own
   request — separation of duties).
5. The request **deploys** (simulated), a resource is registered in the
   **Inventory**, and the requester is **notified**.
6. Everything is written to the **Activity & Audit Log**.

## Roles

`viewer` < `developer` < `operator` / `approver` / `security` < `admin`.
Approver-capable roles and admins see the **Approval Center**; admins also see the
**Admin** panel (approve signups, change roles).

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `M01_PORT` | `5001` | HTTP port |
| `M01_HOST` | `0.0.0.0` | Bind address |
| `M01_DEMO` | `1` | `1` simulates infrastructure actions; `0` expects real backends (not wired yet) |
| `JWT_SECRET` | dev value | **Set this in any real deployment** |
| `M01_ADMIN_USER` / `M01_ADMIN_PASSWORD` / `M01_ADMIN_EMAIL` | `admin` / `admin` / … | Bootstrap admin (first run only) |
| `M01_DB_PATH` | `backend/data/m01.db` | SQLite database file |
| `AWS_REGION` | `us-east-1` | Display hint |

## Project layout

```
m01-self-service-portal/
├── backend/
│   ├── app.py          # Flask entry point, serves API + frontend
│   ├── api.py          # all REST routes, JWT auth, role guards
│   ├── store.py        # SQLite store: users, catalog, requests, approvals,
│   │                   #   deployments, resources, notifications, audit
│   ├── middleware.py   # YAML generation, plan/apply simulation, AI assistant
│   ├── validators.py   # input validation against catalog item schemas
│   └── config.py       # env-driven settings
├── frontend/
│   ├── login.html      # login + request-access
│   ├── index.html      # portal shell (all views)
│   ├── app.js          # SPA controller for the eleven capabilities
│   ├── api.js          # API client + render helpers
│   └── app.css         # styles (light + dark)
├── requirements.txt
├── run.sh
└── README.md
```

## API (selected endpoints)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/login`, `/api/auth/signup` | Auth |
| GET | `/api/overview` | Dashboard KPIs, health, recent activity |
| GET | `/api/catalog`, `/api/catalog/<id>` | Service catalog |
| GET/POST | `/api/requests` | List / create requests |
| GET | `/api/requests/<id>/manifest` | Generated YAML manifest |
| GET | `/api/requests/<id>/plan` | Streamed plan preview (SSE) |
| GET | `/api/approvals` | Pending approvals (approver roles) |
| POST | `/api/requests/<id>/approve` \| `/reject` | Decide a request |
| GET | `/api/deployments` | Deployment history |
| GET | `/api/resources` | Resource inventory (search/filter) |
| GET | `/api/health-summary` | Operational health |
| GET/POST | `/api/notifications` | List / mark read |
| GET | `/api/search?q=` | Global, permission-aware search |
| POST | `/api/assistant` | AI assistant reply |
| GET | `/api/audit` | Activity & audit log |
| GET/POST | `/api/users...` | Admin: list, approve, reject, role change |

## M01 acceptance criteria (from the specification)

| Capability | Where it lives | Met by |
|---|---|---|
| Unified dashboard | Overview view, `/api/overview` | KPIs, health, recent activity and requests |
| Role-based navigation | `app.js` NAV filter + API role guards | Menu and endpoints enforce roles |
| Service catalog | Catalog view, `/api/catalog` | Versioned items with input schemas |
| Request management | Requests view, `/api/requests` | Guided forms, validation, status timeline, cancel |
| Approval center | Approvals view, `/api/approvals` | Tiered approval, separation of duties |
| Deployment dashboard | Deployments view, `/api/deployments` | Live status and logs |
| Resource inventory | Inventory view, `/api/resources` | Searchable, filterable, owner + health |
| Operational health | Health view, `/api/health-summary` | Resource health and request throughput |
| Notifications | Bell drawer, `/api/notifications` | Per-user and broadcast, unread badge |
| Global search | Header search, `/api/search` | Permission-aware across catalog/requests/resources |
| AI conversational assistant | Assistant view, `/api/assistant` | Guided help over portal concepts |

## Security notes (demo scope)

- Passwords are salted PBKDF2-HMAC-SHA256; never stored in plaintext.
- JWT bearer auth; set a strong `JWT_SECRET` in production.
- Separation of duties: a requester cannot approve or reject their own request.
- New accounts require admin approval before first sign-in.
- Every state change writes an audit entry.
- Demo mode makes **no AWS calls**. Wiring Terraform/Atmos/Argo CD and real
  identity is a later module; the seams are in `middleware.py`.

Author: Ashish Gajjar.

## EC2 launch (GUI)

Open **EC2 Instances** in the portal. A four-step wizard (image, size, network and storage, review) creates a
request for the `ec2-instance` catalog item. Non-production launches are approved automatically and run at once;
production launches wait for an approver. The Instances tab offers start, stop, reboot and terminate (terminate needs admin or operator).

- `M01_DEMO=1` (default): instances are simulated and stored in SQLite. No AWS call is made. The UI says so.
- `M01_DEMO=0` (`./start-portal.sh --prod`): boto3 calls `ec2:RunInstances` in the active AWS account (AssumeRole or
  instance role). Images come from public SSM parameters, volumes are gp3 and encrypted, IMDSv2 is required, and
  instances are tagged `ManagedBy=fde-nexus`. Only tagged instances can be changed.
- IAM permissions: `ec2:RunInstances`, `ec2:DescribeInstances`, `ec2:Start/Stop/Reboot/TerminateInstances`, `ec2:CreateTags`,
  `ec2:DescribeKeyPairs`, `ec2:DescribeSubnets`, `ec2:DescribeSecurityGroups`, `ssm:GetParameter`. Not tested against a real AWS account.

## Persistence

AWS accounts, users, requests, approvals, instances and audit log are stored in SQLite (`backend/data/m01.db`,
override with `M01_DATA_DIR`). Back up that file.

`reference/` holds a copy of the legacy `selfservice` prototype; see `reference/README.md`.
