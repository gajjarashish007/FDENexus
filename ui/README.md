# FDE Nexus: Static Frontend UI

A **frontend-only, static demo** of the FDE Nexus platform console. It brings together the three
real applications in this repository (`validator/`, `pod/`, `workshop/`) behind one governed portal,
and adds self-service flows. Built with HTML, CSS, JavaScript and Bootstrap 5.

> **Demo only.** There is no backend. No APIs, databases, real authentication, AWS calls or business
> logic run here. Every button, form, filter, table action, run, approval, PR and Slack message is a
> **visual simulation** using mock data in `js/mock-data.js`. A banner and toasts make this explicit.

## Open-source stack it represents

Terraform · Atmos · Kubernetes / EKS · kubectl · YAML · GitHub · GitHub Actions · Argo CD (GitOps) ·
Slack · AWS · Python / FastAPI · Bootstrap. See the **Tech Stack** page in the UI.

## Run it locally

No build step. Recommended: a tiny static server (avoids `file://` quirks).

```bash
cd ui
python3 -m http.server 8080
# then open http://localhost:8080  (you land on the login page)
```

Or just open `ui/login.html` in a browser.

Bootstrap and Bootstrap Icons load from a CDN, so an internet connection is needed the first time.

## Sign in (demo)

The app opens on a **login page**. Any username and password work. Pick a **role** to control what
you can see:

| Role | What it unlocks |
|---|---|
| Super Admin / Admin | Everything, including the **Admin Panel** (users, roles, access matrix) |
| Operator / Developer / Security / Viewer | A reduced view; the Admin Panel is hidden |

The session is stored in `localStorage`. Sign out from the avatar menu (top right).

## Pages

| File | Page | What it shows |
|---|---|---|
| `login.html` | Sign in | Demo login with a role selector (public page) |
| `index.html` | Overview | KPIs, your three apps, an end-to-end flow, module health, activity, alerts |
| `applications.html` | Applications | The real tools: Validator, Pod Dashboard (EKSense), Atmos Workshop |
| `services.html` | Modules & Services | The 16 platform modules (M01–M16) as filterable cards |
| `service-details.html` | Module Details | Tabs: capabilities, operations, findings, activity |
| `requests.html` | Requests & Approvals | Request table, risk tiers, approve/reject modals |
| `operations.html` | Operations Registry | Operation catalog (OP-*) with risk tiers R0–R3 and a run modal |
| `requirements.html` | Describe → YAML | Write a requirement, generate YAML, send to Slack, open a PR |
| `builder.html` | Infrastructure Builder | Guided form (incl. full **Helm chart** section) with a live YAML preview |
| `troubleshooting.html` | EKS Troubleshooting | Common EKS failures, read-only checks, simulated diagnostics |
| `validation.html` | Checks & Validation | Policy, security, cost and supply-chain checks with a simulated run |
| `stack.html` | Tech Stack | The open-source tools used, filterable by category |
| `reports.html` | Reports | Compliance, FinOps, reliability and access report cards |
| `activity.html` | Activity & Audit Log | Immutable-style audit event table |
| `admin.html` | Admin Panel (admins only) | Users, roles, and a resource/service access matrix |
| `settings.html` | Settings | Profile, theme, autonomy ladder, integrations |
| `help.html` | Help & Docs | What the demo is, the real apps, terminology |

## Key flows to try

1. **Describe → YAML**: type (or pick an example) → Generate YAML → Send to Slack → Create PR.
2. **Infrastructure Builder**: choose "Helm Release", fill the chart fields → watch the YAML update → Create PR.
3. **EKS Troubleshooting**: open a scenario → Run diagnostics (read-only, simulated).
4. **Admin Panel** (sign in as Admin): change a user's role, suspend a user, adjust the access matrix.

## Project structure

```
ui/
├── login.html + 16 app pages
├── css/styles.css          # design tokens, components, login, builder styles
├── js/
│   ├── mock-data.js        # tools, stack, modules, users, roles, access matrix, demo records
│   ├── components.js       # login gate, sidebar, header, user menu, toasts, theme
│   └── app.js              # page logic: filtering, sorting, modals, YAML generation, admin
└── README.md
```

## Notes

- Clean AWS/cloud-operations enterprise style: one color system, consistent spacing, subtle shadows,
  hover states, light and dark theme (remembered in `localStorage`).
- Responsive: the sidebar collapses on tablet and becomes an off-canvas menu on mobile.
- Accessible: semantic HTML, labelled controls, focus styles, status shown by text plus color.
- Terminology matches the specification: modules M01–M16, risk tiers R0–R3, autonomy A0–A4.

Specification and demo author: Ashish Gajjar.
