# SmartOps Portal: The Complete Guide to Self-Service AWS Infrastructure & Application Deployment

**Blog type:** Product walkthrough / technical blog  
**Product:** SmartOps Portal  
**URL:** `http://localhost:5000` (local) or your deployed URL  
**Audience:** Developers, DevOps engineers, platform teams, and non-technical operators  
**Estimated read time:** 22–26 minutes  

**Document structure:** Introduction → Advantages → Disadvantages → Walkthrough (§4–§16) → Conclusion → Quick Start

---

## Screenshot Index (Quick Reference)

Use this table when preparing images for the blog. Each section below references one screenshot by ID.

| ID | Suggested filename | What to capture | Used in section |
|----|-------------------|-----------------|-----------------|
| **SS-01** | `01-login-page.png` | Sign-in screen with 3D cube, username/password, "Request access" link | §4 Getting Started |
| **SS-02** | `02-signup-request-access.png` | Request Access form (username, email, password, confirm) | §4 Getting Started |
| **SS-03** | `03-portal-navigation.png` | Full portal after login — sidebar (Chat, Dashboard, Services, Logs, Deployments, Guide) | §5 Portal Overview |
| **SS-04** | `04-infrastructure-chat-workflow.png` | Chat left + Terraform plan / PR / Apply right — full workflow complete | §6 Infrastructure Chat |
| **SS-05** | `05-yaml-diff-review.png` | YAML Before/After diff with Confirm & Reject buttons | §6 Infrastructure Chat |
| **SS-06** | `06-terraform-plan-output.png` | Plan Output panel showing resource changes (add/change/destroy lines) | §6 Infrastructure Chat |
| **SS-07** | `07-pull-request-approval.png` | PR widget showing APPROVED status and approval bar filled | §6 Infrastructure Chat |
| **SS-08** | `08-apply-complete.png` | Apply Output showing "Apply complete! Resources updated" + green status | §6 Infrastructure Chat |
| **SS-09** | `09-resource-dashboard.png` | Resource Dashboard (EC2, S3, DynamoDB lists inside iframe) | §7 Resource Dashboard |
| **SS-10** | `10-service-catalog.png` | Service Catalog grid — all service cards (EC2, ALB, S3, ASG, deploy cards) | §8 Service Catalog |
| **SS-11** | `11-ec2-launch-modal.png` | EC2 Launch modal — OS tabs, AMI dropdown, instance types, cost summary | §9 AWS Resource Creation |
| **SS-12** | `12-dynamodb-create-modal.png` | DynamoDB modal — billing mode cards, schema preview, key types | §9 AWS Resource Creation |
| **SS-13** | `13-asg-create-modal.png` | ASG modal — launch template, subnet checkboxes, Min/Desired/Max bar | §9 AWS Resource Creation |
| **SS-14** | `14-static-website-deploy.png` | Static Website deploy modal — app name, domain, folder upload | §10 Application Deployment |
| **SS-15** | `15-code-upload-deploy.png` | Code Upload modal — ZIP, language, container port, platform | §10 Application Deployment |
| **SS-16** | `16-custom-docker-pipeline.png` | Custom Docker Image modal — 4-step 3D pipeline + .tar upload | §10 Application Deployment |
| **SS-17** | `17-manage-deployments-table.png` | Deployments table — name, type, status, URL, actions (rerun/edit/destroy) | §11 Manage Deployments |
| **SS-18** | `18-audit-log-history.png` | Log History filtered by "Infrastructure workflow" with readable action labels | §12 Audit & Compliance |
| **SS-19** | `19-user-guide-aws-deploy.png` | User Guide open on "How to Deploy to AWS" section | §13 User Guide |
| **SS-20** | `20-admin-user-approvals.png` | Admin Users view — pending signup requests, Approve/Reject buttons | §14 Admin & Security |
| **SS-21** | `21-workflow-stepper.png` | 5-step workflow bar: Select → Describe → YAML → Plan → Apply | §6 Infrastructure Chat |
| **SS-22** | `22-service-architecture-diagram.png` | Any service modal showing 3D architecture diagram (e.g. ECS or EC2) | §8 Service Catalog |
| **SS-GIF** | `smartops-architecture-flow.gif` | **Animated** architecture + workflow (auto-generated — see below) | §16 Architecture, §17 Conclusion |

> **Animated GIF (ready to use):** Run `python generate_architecture_gif.py` to create `screenshots/smartops-architecture-flow.gif` — 29 frames showing system architecture layers, chat workflow, deploy paths, and data flow.

> **Tip for bloggers:** Save all screenshots in a `/screenshots/` folder next to this file. Use consistent resolution (1920×1080 or 1440×900). Crop to the relevant UI area — avoid full desktop with taskbar unless showing the whole portal shell.

---

## 1. Introduction

Every growing team hits the same wall with cloud infrastructure: **AWS is powerful, but getting things done is slow.** A developer needs a VPC — they open a ticket. A product manager wants a staging website deployed — they wait for DevOps. An engineer copies Terraform snippets from a wiki, prays nothing breaks in production, and hopes someone remembered to log the change.

The result is predictable: bottlenecks, shadow IT, inconsistent environments, and audit gaps that show up only when something goes wrong.

**SmartOps Portal** is a self-service platform built to break that cycle. It gives every approved user — from seasoned engineers to non-technical operators — a single, governed front door to Amazon Web Services. Instead of juggling the AWS Console, a ticket queue, and half a dozen internal tools, teams work in one place:

- **Describe infrastructure in plain language** and walk through a safe, reviewable workflow (YAML diff → Terraform plan → PR approval → apply)
- **Create AWS resources directly** from a visual dashboard (EC2, S3, DynamoDB, load balancers, auto scaling, certificates)
- **Deploy applications** via static website upload, source-code ZIP, or custom Docker image
- **Track every action** in a searchable audit log with export to CSV

This blog is a complete walkthrough of SmartOps Portal — what it does, how to deploy to AWS step by step, where to place screenshots, and an honest look at what it does well and where it has limits. Whether you are evaluating the platform for your organization, writing an internal launch announcement, or onboarding your first users, this document is designed to be copy-ready for publication.

> **📸 Optional hero image:** SS-04 (Infrastructure Chat full workflow) or SS-GIF (`smartops-architecture-flow.gif`)

**Who this is for:** Developers, DevOps engineers, platform teams, IT administrators, and business users who need cloud resources without becoming AWS experts.

**What you will learn by the end:**
- How to get access and run your first deployment
- The three ways to put workloads on AWS through the portal
- Which screenshots to capture for a blog or presentation
- The platform's strengths, limitations, and recommended use cases

---

## 2. Advantages of SmartOps Portal

SmartOps Portal is not just another dashboard pasted on top of AWS. It is designed around how real teams request, review, and ship infrastructure. Here are the main benefits.

### For teams and operators

| Advantage | What it means in practice |
|-----------|---------------------------|
| **No ticket queue for routine work** | Users request VPCs, scale EC2, or deploy apps themselves — within guardrails — instead of waiting days for a manual change. |
| **Plain-language infrastructure requests** | The Chat assistant lets users type *"create vpc"* or *"scale to 2 replicas"* instead of writing Terraform or clicking through dozens of console screens. |
| **Governed workflow by default** | Every chat-driven change passes through YAML review, plan preview, PR approval, and apply — reducing accidental production changes. |
| **Three deployment paths in one UI** | Static websites, code ZIPs, and Docker images are all supported without switching tools. |
| **Built-in user guide** | Non-technical users get searchable, step-by-step help inside the portal — no external wiki required. |
| **Full audit trail** | Log History records chat messages, plan/apply steps, deployments, and logins — with filters and CSV export for compliance. |

### For platform and security teams

| Advantage | What it means in practice |
|-----------|---------------------------|
| **Admin-controlled access** | Signup requires approval; roles separate admins from operators; accounts can be rejected or disabled. |
| **Destructive change protection** | Plans that delete or destroy resources block the Apply button automatically. |
| **Input validation everywhere** | Forms validate app names, domains, AMI IDs, bucket names, ports, and capacity — on both frontend and backend — before anything reaches AWS. |
| **JWT-based sessions** | Authenticated SSP workflows; audit logs tied to usernames. |
| **Region switching** | Operators can target eu-west-1, us-east-1, and other regions from the Chat toolbar. |
| **Real-time feedback** | WebSocket streaming for plan/apply with REST fallback — users see progress live, not a frozen screen. |

### For developers and DevOps

| Advantage | What it means in practice |
|-----------|---------------------------|
| **Live AWS catalog integration** | EC2 modals fetch AMIs, instance types, key pairs, launch templates, and subnets from AWS (with sensible fallbacks offline). |
| **Rich service modals** | 3D architecture diagrams and field guides in every create/deploy dialog reduce guesswork. |
| **Manage Deployments table** | Rerun, edit, and destroy app deployments from a single view — no hunting through console tabs. |
| **Single codebase, one port** | Flask backend serves portal, dashboard, APIs, and WebSocket on port 5000 — simple to run locally or package for internal hosting. |
| **Extensible middleware** | SSP layer (`ssp_api.py`, `ssp_middleware.py`) is separate from direct AWS CRUD — easy to swap simulated plans for real Terraform later. |

### Compared to alternatives

| Approach | SmartOps Portal | AWS Console alone | Ticket-only process |
|----------|-----------------|-------------------|---------------------|
| Time to first deploy | Minutes (after approval) | Hours (learning curve) | Days (queue wait) |
| Change review | Built-in YAML + plan + PR | Manual / none | Email or ticket thread |
| Audit log | Automatic, searchable | CloudTrail (separate) | Scattered |
| Non-technical users | Supported via Chat + Guide | Poor fit | Depends on engineer |
| App deployment | Static + code + Docker | Multiple services manually | Custom pipeline per team |

---

## 3. Disadvantages & Limitations

No platform is perfect. Being upfront about limitations builds trust in a blog and helps teams set realistic expectations before adoption.

### Current technical limitations

| Limitation | Detail | Mitigation |
|------------|--------|------------|
| **Simulated Terraform workflow** | Chat plan/apply uses middleware output — not live `terraform apply` against remote state (yet). | Use Dashboard for real boto3 CRUD; treat Chat as a governed preview workflow until Terraform backend is wired. |
| **AWS dashboard routes are unauthenticated** | Direct `/api/ec2`, `/api/s3`, etc. endpoints do not require JWT today. | Deploy behind VPN or internal network; add auth middleware before internet exposure. |
| **Deploy flows are partially simulated** | App deployments save files locally and return mock URLs — they do not always push to real ECR/ECS/CloudFront in every environment. | Confirm with your team which deploy paths are wired to production AWS in your fork. |
| **Single-server SQLite auth store** | Users and audit logs live in `ssp_data.db` on one machine. | For HA production, migrate to PostgreSQL/RDS and add backup strategy. |
| **No multi-cloud support** | AWS only (EC2, S3, DynamoDB, ELB, ASG, ACM, ECS patterns). | Not suitable as-is for Azure or GCP teams. |
| **WebSocket uses polling transport** | Socket.IO configured without upgrade — works everywhere but not optimal for high-latency networks. | REST SSE fallback already exists for plan/apply. |

### Operational considerations

| Limitation | Detail |
|------------|--------|
| **Requires AWS credentials on server** | The backend needs `aws configure` (or IAM role) on the host — operators cannot use the Dashboard meaningfully without this setup. |
| **Admin bootstrap not in user guide UI** | First admin password appears in server console on first run — must be communicated securely out of band. |
| **AWS costs still apply** | Self-service does not mean free — EC2, S3, and other resources incur real charges; the portal does not enforce budget caps. |
| **Learning curve for Chat workflow** | Users must understand YAML diff, plan review, and PR approval — simpler than Terraform CLI, but not zero training. |
| **English-only UI** | All labels, guide text, and errors are in English. |

### When SmartOps Portal is *not* the right fit

- **Large enterprise multi-tenant IDP** — If you need full Backstage, Service Catalog, or org-wide service templates with hundreds of microservices, this portal is a starting point, not a replacement.
- **Production Terraform state management** — Until real Terraform/OpenTofu integration is added, do not rely on Chat apply as your sole source of truth for production infra state.
- **Public internet SaaS** — Default JWT secret, open AWS routes, and local deploy storage are designed for internal/trusted networks, not public multi-customer hosting without hardening.
- **Teams that never want self-service** — If your organization mandates that every change goes through a central platform team with no exceptions, the portal's value is reduced.

> **Blog tip:** Acknowledging these limits in your post makes the article credible. Pair each disadvantage with your team's roadmap or workaround where possible.

---

## 4. Getting Started — Access & First Login

Before using the portal, every user goes through a controlled onboarding flow. This keeps the platform secure while remaining easy for non-technical users.

### Step 1: Open the portal

Navigate to your SmartOps Portal URL (e.g. `http://localhost:5000`). You land on the sign-in page.

> **📸 Use screenshot: SS-01 — Login Page**  
> Show the SmartOps Portal title, 3D animated cube, Sign In button, and "Request access" link at the bottom.

### Step 2: Request access (first-time users)

Click **Request access** and fill in:

| Field | Rules |
|-------|-------|
| Username | 3–32 characters, letters, numbers, underscore only |
| Email | Valid work email |
| Password | Minimum 8 characters |
| Confirm password | Must match password |

Submit the form. You will see a success message — but you **cannot sign in yet**.

> **📸 Use screenshot: SS-02 — Signup / Request Access**  
> Show the Request Access form with all four fields visible and the "Submit Request" button.

### Step 3: Wait for admin approval

An administrator reviews your request under **Users** in the sidebar. Once approved, return to the login page and sign in with your credentials.

### Step 4: Admin one-time server setup (for operators)

On the machine running the portal:

```bash
aws configure          # Enter AWS Access Key, Secret Key, region
pip install -r requirements.txt
python backend-api.py  # Or run start.bat on Windows
```

The portal connects to AWS via boto3. Without credentials, the dashboard still loads but uses catalog fallbacks.

---

## 5. Portal Overview — Navigation & Layout

After login, you enter the main portal shell: a **3D sidebar** on the left and your active workspace on the right.

> **📸 Use screenshot: SS-03 — Portal Navigation**  
> Capture the full layout: sidebar with all menu items, top bar (theme, API status, WebSocket badge), and Chat view active.

### Left menu modules

| Menu item | Purpose |
|-----------|---------|
| **Chat** | Infrastructure requests in plain language (Provisioner) |
| **Dashboard** | View and create AWS resources (EC2, S3, DynamoDB, ALB, ASG, ACM) |
| **Services** | Deploy applications (static site, code ZIP, Docker image) |
| **Log History** | Audit trail — search, filter, export CSV |
| **Deployments** | Manage deployed apps — rerun, edit, destroy |
| **Users** *(admin only)* | Approve or reject signup requests |
| **Guide** | Built-in user guide for non-technical users |

### Top bar indicators

- **Theme** — Dark, Light, or Ocean
- **WebSocket / Live** — Real-time plan/apply streaming status
- **API status** — Shows if backend and AWS are connected

---

## 6. Infrastructure Chat — Deploy AWS Resources with Plain Language

The **Provisioner (Chat)** view is the flagship feature. It turns requests like *"create vpc"* or *"scale EC2 to 2 replicas"* into a governed, reviewable deployment workflow.

> **📸 Use screenshot: SS-21 — Workflow Stepper**  
> Show the 5-step bar at the top: Select Service → Describe Change → Review YAML → Review Plan → Apply.

### The 5-step workflow

#### Step 1 — Select Service, Account & Region

At the top of the Chat view, choose:

- **Service** — EC2, VPC, S3, DynamoDB, ECS, Lambda, and more
- **Account** — Production, Staging, Dev, Sandbox (with AWS account IDs)
- **Region** — eu-west-1, us-east-1, us-west-2, ap-southeast-1 (changes live AWS region)

Use **Quick actions** chips for common tasks: Scale Up, Create New, Update Config, Add Monitoring, Secure Resource.

#### Step 2 — Describe your change

Type your request in the chat box or click a quick action. Examples:

- `create vpc`
- `Scale EC2 to 2 replicas with monitoring`
- `Update instance type to t3.medium`

Press **Send** or `Ctrl+Enter`. The assistant responds with a contextual reply and automatically generates a YAML diff.

> **📸 Use screenshot: SS-04 — Infrastructure Chat Full Workflow** *(hero image for the blog)*  
> **This is the most important screenshot.** Capture the full Chat view:  
> - **Left:** User message "create vpc" + assistant reply + system status messages (YAML confirmed → Plan generated → Applying → Apply complete)  
> - **Right:** Terraform plan output, PR #380 APPROVED, green Apply button, Apply Output showing COMPLETE  
>  
> *Reference: this matches the Infrastructure Chat workflow screenshot from product demo.*

#### Step 3 — Review YAML diff

Before any plan runs, you must review the **Before / After YAML** comparison.

- **Green / added lines** — new configuration
- **Red / removed lines** — deleted settings
- **Destructive badge** — appears if the request includes delete/destroy/remove/terminate

Click **Confirm Diff & Generate Plan** or **Reject** to cancel.

> **📸 Use screenshot: SS-05 — YAML Diff Review**  
> Show side-by-side Before/After YAML panes with syntax highlighting and Confirm/Reject buttons.

#### Step 4 — Review Terraform plan

The portal streams a Terraform plan in real time (WebSocket with REST fallback):

```
Terraform v1.7.0
# vpc.main will be updated in-place
  ~ replicas      = 1 -> 2
  ~ instanceType  = "t3.micro" -> "t3.medium"
  + monitoring    = true
Plan: 0 to add, 1 to change, 0 to destroy.
```

Destructive plans **block Apply** automatically — no accidental deletions.

> **📸 Use screenshot: SS-06 — Terraform Plan Output**  
> Show the Plan Output panel with colored diff lines and "✓ Ready" status badge.

#### Step 5 — Approve PR and Apply

Every infrastructure change is linked to a **Pull Request** for review:

1. Review the PR title (e.g. `[SmartOps Portal] Update vpc in prod`)
2. Click **Approve PR** until status shows **APPROVED** (e.g. 2/2 approvals)
3. Click **Apply Changes**

Apply is **disabled** until: YAML confirmed + plan reviewed + PR approved + non-destructive plan.

> **📸 Use screenshot: SS-07 — Pull Request Approval**  
> Show PR widget with green APPROVED badge and full approval bar.

> **📸 Use screenshot: SS-08 — Apply Complete**  
> Show Apply Output with health check passed and "Apply complete! Resources: 1 changed."

Every step is logged to **Log History** (Infrastructure Chat, YAML Diff, Plan Started/Complete, Apply Started/Complete, PR Approved).

---

## 7. Resource Dashboard — View & Manage AWS Resources

Open **Dashboard** from the sidebar to see your live AWS resources inside an embedded view.

> **📸 Use screenshot: SS-09 — Resource Dashboard**  
> Show index.html embedded view: EC2 instances table, S3 buckets, DynamoDB tables with connection status and region in header.

The dashboard displays:

- **EC2 Instances** — ID, type, state, launch time
- **DynamoDB Tables** — name, status, item count, size
- **Application Load Balancers** — name, DNS, state
- **S3 Buckets** — name, region, creation date
- **Auto Scaling Groups** — name, desired/min/max capacity
- **ACM Certificates** — domain, status, type

Each section has refresh and create buttons. Resources are fetched directly from AWS via boto3.

---

## 8. Service Catalog — All Available AWS & Deploy Services

Open **Services** to browse the full catalog of what you can create or deploy.

> **📸 Use screenshot: SS-10 — Service Catalog**  
> Show dashboard.html grid with service cards: EC2, ALB, NLB, DynamoDB, S3, ASG, ACM, Static Website, Code Upload, Custom Docker, ECS, Lambda, RDS.

Each card includes:

- Category badge (COMPUTE, NETWORKING, STORAGE, DATABASE, DEPLOY)
- Mini **3D architecture diagram** preview
- Deploy time and cost estimate
- Feature tags (Quick Launch, Auto Scaling, etc.)
- **Create** button opening a guided modal

> **📸 Use screenshot: SS-22 — Service Architecture Diagram**  
> Open any service modal (EC2, ECS, or DynamoDB) and capture the 3D architecture + field guide diagram at the top.

### Available services

| Category | Services |
|----------|----------|
| Compute | EC2 Instance, ECS Fargate, Lambda Function, Auto Scaling Group |
| Networking | Application Load Balancer, Network Load Balancer, SSL Certificate (ACM) |
| Storage | S3 Bucket, Static Website Hosting |
| Database | DynamoDB Table, RDS Database |
| Deploy | Static Website, Upload Code & Deploy, Custom Docker Image |

---

## 9. AWS Resource Creation — Forms with Smart Validation

Every create form validates input **before** sending to AWS — on both frontend and backend.

> **📸 Use screenshot: SS-11 — EC2 Launch Modal**  
> Show EC2 modal with: OS tabs (Amazon Linux, Ubuntu, Windows), AMI dropdown populated from AWS, instance type grid with categories (General, Compute, Memory), optional key pair, cost summary.

### EC2 Instance

- Select OS → pick AMI from live AWS catalog (with fallback)
- Choose from 12+ instance types with category filters
- Optional instance name and SSH key pair
- Validates AMI ID format (`ami-xxxxxxxx`)

> **📸 Use screenshot: SS-12 — DynamoDB Create Modal**  
> Show billing mode cards (On-Demand vs Provisioned), partition/sort key fields, live schema preview table.

### DynamoDB Table

- Table name regex validation (3–255 chars)
- Partition key + optional sort key with type selectors (String, Number, Binary)
- Billing mode cards with visual selection
- Live schema preview updates as you type

> **📸 Use screenshot: SS-13 — ASG Create Modal**  
> Show launch template dropdown (from AWS), subnet checkboxes, Min/Desired/Max capacity visual bar.

### Auto Scaling Group

- Launch template fetched from AWS
- Subnet multi-select with format validation
- Capacity bar: Min ≤ Desired ≤ Max enforced on submit
- Warning if fewer than 2 subnets selected

### Other resources

- **S3 / Static Website** — bucket naming rules (lowercase, 3–63 chars, no consecutive dots)
- **ALB/NLB** — subnet ID format, minimum 1 subnet (2+ recommended)
- **ACM Certificate** — domain FQDN validation, wildcard support

Errors appear as toast messages with plain-language explanations — no cryptic AWS error codes in the UI.

---

## 10. Application Deployment — Three Paths to Production

SmartOps Portal supports three deployment models. Pick the one that matches what you have.

> **📸 Use screenshot: SS-14 — Static Website Deploy**  
> Show modal: app name field, domain field, CloudFront checkbox, folder upload with file count.

### Path A — Static Website (S3 + CloudFront)

**Best for:** HTML/CSS/JS sites, landing pages, documentation sites.

**Steps:**
1. Prepare a folder with `index.html` plus assets
2. Open Services → **Deploy Static Website Hosting**
3. Enter app name (lowercase, hyphens) and domain (e.g. `app.example.com`)
4. Select website folder → Submit
5. Portal uploads to S3, configures hosting, optionally enables CloudFront CDN

**Validation:** Requires `index.html`, max 50MB per file, valid domain format.

> **📸 Use screenshot: SS-15 — Code Upload Deploy**  
> Show modal: app name, language dropdown (auto-detect/Python/Node/Go/Java), container port, platform, ZIP upload with file size.

### Path B — Upload Code & Deploy (ZIP → Docker → ECS)

**Best for:** Python, Node.js, Go, Java projects without a pre-built Docker image.

**Steps:**
1. ZIP your project folder
2. Open Services → **Upload Code & Deploy**
3. Enter app name, container port (default 8080), upload ZIP
4. Portal auto-detects language, builds Docker image, pushes to ECR, deploys to ECS

**Validation:** ZIP only, max 200MB, port 1–65535, app name format.

> **📸 Use screenshot: SS-16 — Custom Docker Image Pipeline**  
> Show the 4-step 3D pipeline: (1) Build Image → (2) Save as .tar → (3) Upload → (4) Deploy Live, with copy-paste docker commands and .tar file upload.

### Path C — Custom Docker Image (BYOI → ECR → ECS)

**Best for:** Teams with an existing Docker workflow.

**Steps on your machine:**
```bash
docker build -t my-app:latest .
docker save my-app:latest -o my-app.tar
```

**Steps in portal:**
1. Open Services → **Custom Docker Image**
2. Follow the 4-step visual pipeline in the modal
3. Upload `.tar` file, select platform (linux/amd64 or linux/arm64)
4. Submit — portal loads to ECR and deploys behind ALB

**Validation:** .tar only, max 5GB, platform required, chunked upload for files >1GB.

---

## 11. Manage Deployments — Rerun, Edit, Destroy

All deployments appear in a **table view** under the Deployments menu.

> **📸 Use screenshot: SS-17 — Manage Deployments Table**  
> Show table columns: Resource Name, Service Type, Status (APPLIED green badge), URL link, Updated time, action buttons (↻ rerun, ✏️ edit, ✕ destroy).

| Action | What it does |
|--------|--------------|
| **↻ Rerun** | Re-deploy the same configuration |
| **✏️ Edit & Rerun** | Change name, container port, or platform, then redeploy |
| **✕ Destroy** | Remove deployment record and delete uploaded files |
| **▸ Expand row** | Show deployment ID, platform, port, ECR URI details |

Filter by status (Applied, Error, Pending) or search by name/ID. Click **+ New Deployment** to jump to Services.

---

## 12. Audit & Compliance — Log History

Every significant action is recorded in **Log History**.

> **📸 Use screenshot: SS-18 — Audit Log History**  
> Show log table with readable action labels (Infrastructure Chat, Terraform Plan Complete, Apply Complete), Details column showing user message ("Chat: create vpc"), and "Infrastructure workflow" filter selected.

### What gets logged

| Action label | When |
|--------------|------|
| Infrastructure Chat | User sends a chat message |
| YAML Diff Generated / Confirmed / Rejected | Diff workflow steps |
| Terraform Plan Started / Complete | Plan generation |
| Apply Started / Complete | Infrastructure apply |
| PR Approved | Pull request approval |
| Deployment Created / Rerun / Edit / Destroy | App deployment actions |
| Login / Signup / User Approved | Auth events |

### Features

- **Search** — by user, action, service, or details text
- **Filter** — All actions / Infrastructure workflow / Login & users / Deployments
- **Level filter** — Info, Warning, Error
- **Export CSV** — download full audit trail
- **Auto-refresh** — updates when Log History is open during chat workflow

Admins see all logs. Operators see only their own entries.

---

## 13. Built-in User Guide — No External Docs Needed

SmartOps Portal includes a searchable, expandable **User Guide** accessible from the sidebar or the ❓ Help button.

> **📸 Use screenshot: SS-19 — User Guide AWS Deploy Section**  
> Show Help view with "How to Deploy to AWS (Step-by-Step)" section expanded, showing Path A/B/C steps and prerequisites.

### Guide sections

1. What is SmartOps Portal?
2. Getting Access (First-Time Users)
3. **How to Deploy to AWS (Step-by-Step)** ← key section for blog readers
4. Finding Your Way Around
5. Using the Chat Assistant
6. Using the Dashboard
7. Deploying Your Application (Services)
8. Managing Deployments
9. Activity Logs
10. For Administrators
11. Simple Glossary (EC2, S3, Docker, YAML, PR, etc.)
12. FAQ & Help

The guide is written in plain language — no AWS certification required.

---

## 14. Admin & Security — User Approvals & Access Control

Administrators have an additional **Users** menu item for managing access.

> **📸 Use screenshot: SS-20 — Admin User Approvals**  
> Show pending users table with username, email, request date, and Approve / Reject buttons. Include the pending badge count on the sidebar Users icon.

### Security model

| Feature | Detail |
|---------|--------|
| Signup approval | New users start as `pending` — cannot login until approved |
| JWT sessions | 24-hour tokens, stored in browser localStorage |
| Role-based access | `admin` vs `operator` roles |
| Account states | pending, approved, rejected, disabled |
| Audit trail | Every login, signup, approval logged |
| No default credentials | Admin password set on first DB init (console output or `ADMIN_PASSWORD` env var) |

### Production recommendations

- Set `JWT_SECRET` environment variable
- Set `ADMIN_PASSWORD` on first deploy
- Run behind HTTPS reverse proxy
- Restrict network access to the portal API
- Configure AWS IAM with least-privilege policies

---

## 15. How to Deploy to AWS — Complete Step-by-Step (Blog Summary)

This section is the **action checklist** readers can follow after reading the blog.

### Prerequisites

- [ ] AWS account with EC2, S3, ECS, ECR, DynamoDB permissions
- [ ] `aws configure` run on the portal server
- [ ] SmartOps Portal running (`start.bat` or `python backend-api.py`)
- [ ] User account approved by admin

### Option 1 — Infrastructure via Chat

1. Sign in → open **Chat**
2. Select Service (e.g. VPC), Account (e.g. Production), Region
3. Type request: `create vpc`
4. Review YAML diff → **Confirm**
5. Review Terraform plan
6. **Approve PR** until APPROVED
7. Click **Apply Changes**
8. Verify in Log History and Dashboard

> **Screenshots for this flow:** SS-04, SS-05, SS-06, SS-07, SS-08

### Option 2 — Direct resource via Dashboard

1. Open **Dashboard**
2. Find resource type → click Create
3. Fill validated form → Submit
4. Confirm success toast and refreshed list

> **Screenshots for this flow:** SS-09, SS-11, SS-12, SS-13

### Option 3 — Application via Services

1. Open **Services**
2. Choose deployment type (Static / Code / Docker)
3. Fill form, upload files → Submit
4. Check **Deployments** for status and URL

> **Screenshots for this flow:** SS-10, SS-14, SS-15, SS-16, SS-17

---

## 16. Architecture & Technology Stack

> **📸 Use animated GIF: SS-GIF — `screenshots/smartops-architecture-flow.gif`**  
> Shows 4 animated scenes: (1) 3-layer system architecture, (2) 7-step chat workflow, (3) 3 deploy paths, (4) end-to-end data flow. Regenerate anytime with `python generate_architecture_gif.py`.

For technical readers, SmartOps Portal is built as:

| Layer | Technology |
|-------|------------|
| Frontend | HTML5, CSS3 (3D transforms), Vanilla JavaScript |
| Portal shell | portal.html, portal-app.js, portal-ssp.js, portal-ws.js |
| Dashboard | Bootstrap 5, Chart.js, app.js, app-extended.js, app-deploy.js |
| Backend | Python Flask + Flask-SocketIO |
| Auth | JWT (PyJWT), SQLite (ssp_data.db) |
| AWS | boto3 (EC2, S3, DynamoDB, ELBv2, ASG, ACM) |
| Real-time | WebSocket (polling transport) + SSE REST fallback |
| Validation | validation.js (frontend) + validators.py (backend) |
| Deploy storage | Local uploads/ folder + deployments.json |

### Request flow (Chat → Apply)

```
User message
  → POST /api/chat/stream (auth required)
  → POST /api/plan/yaml-diff
  → User confirms diff
  → WS generate_plan / POST /api/plan/stream
  → User approves PR
  → WS apply_plan / POST /api/plan/apply-stream
  → Audit logs written at every step
```

---

## 17. Conclusion

SmartOps Portal addresses a problem most cloud teams know too well: **AWS is capable enough for everyone, but accessible enough for almost no one without help.** By combining a governed chat workflow, a direct resource dashboard, and three application deployment paths in one audited interface, it turns infrastructure from a bottleneck into a self-service capability — without removing the safety rails that production demands.

### What makes it worth adopting

- **Speed without chaos** — Users move fast through Chat, Dashboard, or Services, but YAML review, plan preview, PR approval, and validation catch mistakes before they reach AWS.
- **One front door** — Login, deploy, manage, and audit happen in a single portal instead of scattered consoles and ticket threads.
- **Inclusive by design** — Built-in guides, quick actions, and plain-language errors mean product owners and junior engineers can participate — not just senior DevOps staff.
- **Honest scope** — It is an internal self-service platform and IDP starter, not a full replacement for enterprise service catalogs or production Terraform pipelines — and that clarity helps teams deploy it in the right place.

### Recommended next steps

1. **Run it locally** — `start.bat` or `python backend-api.py`, then open `http://localhost:5000`
2. **Configure AWS** — `aws configure` on the server so Dashboard and catalog APIs connect
3. **Approve your first users** — Walk through signup → admin approval → first chat request
4. **Capture screenshots** — Use the SS-01–SS-22 checklist in Appendix A for your blog or launch deck
5. **Share the GIF** — Embed `screenshots/smartops-architecture-flow.gif` in architecture sections
6. **Harden for production** — Set `JWT_SECRET`, restrict network access, add auth to AWS routes, migrate SQLite to RDS

### Final word

The goal of SmartOps Portal is not to eliminate platform engineering — it is to **free platform engineers from repetitive tickets** so they can focus on standards, security, and automation while everyone else gets a safe, documented path to the cloud.

If your team spends more time fielding *"can someone create a bucket?"* requests than improving your platform, this portal is built for you. Start with Chat and the User Guide, expand to Dashboard and Services, and grow toward full Terraform integration as your maturity increases.

**SmartOps Portal — Self-Service AWS Infrastructure & Application Deployment**

---

## 18. Getting Started Today

```bash
# Clone / open the project
cd selfservice

# Install & start (Windows)
start.bat

# Or manually
pip install -r requirements.txt
aws configure
python backend-api.py

# Open browser
http://localhost:5000
```

Sign up → ask admin to approve → open Chat → type `create vpc` → follow the 5-step workflow.

---

## Appendix A — Screenshot Capture Checklist

Use this when preparing images for publication. Check off each as captured.

- [ ] **SS-01** Login page (dark theme recommended)
- [ ] **SS-02** Request Access signup form
- [ ] **SS-03** Full portal shell with sidebar
- [ ] **SS-04** Infrastructure Chat — full workflow complete *(hero image)*
- [ ] **SS-05** YAML diff Before/After
- [ ] **SS-06** Terraform plan output with changes
- [ ] **SS-07** PR widget APPROVED
- [ ] **SS-08** Apply complete output
- [ ] **SS-09** Resource Dashboard (EC2/S3/DynamoDB lists)
- [ ] **SS-10** Service Catalog grid (all cards visible)
- [ ] **SS-11** EC2 launch modal with AMI & instance types
- [ ] **SS-12** DynamoDB modal with schema preview
- [ ] **SS-13** ASG modal with capacity bar
- [ ] **SS-14** Static Website deploy modal
- [ ] **SS-15** Code Upload deploy modal
- [ ] **SS-16** Custom Docker 4-step pipeline modal
- [ ] **SS-17** Manage Deployments table
- [ ] **SS-18** Log History with Infrastructure filter
- [ ] **SS-19** User Guide — AWS Deploy section
- [ ] **SS-20** Admin User Approvals view
- [ ] **SS-21** 5-step workflow stepper (all steps green/done)
- [ ] **SS-22** Service architecture diagram in modal

### Recommended screenshot settings

| Setting | Value |
|---------|-------|
| Resolution | 1920×1080 or 1440×900 |
| Format | PNG (lossless) |
| Theme | Dark (default) — capture SS-03 also in Light for variety |
| Browser | Chrome or Edge, hide bookmarks bar |
| Data | Use realistic demo data (create vpc, mcrdashboard deployment) |

---

## Appendix B — Suggested Blog Post Title & SEO

**Primary title:**  
*SmartOps Portal: Deploy AWS Infrastructure & Applications Without the Ticket Queue*

**Alternative titles:**
- *How We Built a Self-Service AWS Portal Anyone Can Use*
- *From "Create VPC" to Production: Inside SmartOps Portal's 5-Step Workflow*
- *Stop Waiting on DevOps: SmartOps Portal for EC2, S3, ECS & More*

**Meta description (160 chars):**  
*SmartOps Portal lets teams deploy AWS infrastructure via chat, manage resources on a dashboard, and publish apps — with full audit logs and zero CLI.*

**Tags:** AWS, self-service portal, DevOps, infrastructure as code, ECS, EC2, S3, Terraform, internal developer platform

---

*Document version: 1.0 · SmartOps Portal · For blog publication*
