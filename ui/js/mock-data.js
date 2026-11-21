/* FDE Nexus: mock data for the static demo UI.
   Reflects the THREE real tools in this repo (workshop, validator, pod/EKSense),
   the open-source stack used to build them, and demo records for every page.
   All data is for display only. No real systems are represented. */
window.NEXUS = window.NEXUS || {};

/* ------------------------------------------------------------------ */
/* The real tools built in this repository (workshop / validator / pod) */
/* ------------------------------------------------------------------ */
NEXUS.tools = [
  {
    id: "TL-VALIDATOR",
    name: "AI Infrastructure Validator",
    tagline: "AWS account validation: inventory, IAM, Service Quotas, superadmin, self-service.",
    folder: "validator/",
    port: "5000",
    status: "healthy",
    icon: "bi-shield-check",
    role: "The unified Cloud Operations Portal and front door",
    entry: "http://<host>:5000/",
    stack: ["Python", "FastAPI", "SQLite", "boto3", "Bootstrap"],
    features: [
      "Live and cached AWS inventory (Secrets Manager, DynamoDB, IAM, Lambda, RDS, SQS)",
      "IAM inventory and least-privilege review",
      "Service Quotas: cached + live fetch, compare, increase requests, CSV/JSON export",
      "Superadmin: read-only secrets probe, DynamoDB PITR and delete-protection checks",
      "Cross-account and cross-region compare for migration and DR",
      "Terraform self-service stacks",
      "Embedded EKS Pod Dashboard at /eks/ and RBAC + audit log"
    ],
    personas: ["Platform / SRE", "Security / compliance", "Capacity manager", "Admin"],
    maps_to: ["M01", "M02", "M07", "M08", "M12"]
  },
  {
    id: "TL-POD",
    name: "Pod Dashboard (EKSense)",
    tagline: "Day-2 EKS cluster operations: pods, deployments, nodes, rollout restarts, Route53.",
    folder: "pod/",
    port: "8080 (via 5000 /eks/)",
    status: "healthy",
    icon: "bi-boxes",
    role: "EKS operations and troubleshooting, embedded in the portal",
    entry: "http://<host>:5000/eks/dashboard.html",
    stack: ["Python", "kubectl", "AWS CLI", "boto3", "SQLite"],
    features: [
      "Multi-cluster context switch (AWS EKS API, kubeconfig, admin registry)",
      "Cross-account clusters via IAM role ARN assume-role",
      "Pods, deployments, nodes, services, ingress, HPA views",
      "Single and bulk rollout restarts across multiple clusters",
      "Service version lookup and Route53 traffic migration",
      "Users / RBAC admin and an activity / audit log"
    ],
    personas: ["K8s operator", "Platform / SRE", "Admin"],
    maps_to: ["M04", "M07", "M11"]
  },
  {
    id: "TL-WORKSHOP",
    name: "Atmos Workshop",
    tagline: "Plan and deploy infrastructure through Atmos + Terraform workflows, with graphs.",
    folder: "workshop/",
    port: "8080",
    status: "degraded",
    icon: "bi-diagram-3",
    role: "Infrastructure as Code self-service (plan / deploy)",
    entry: "http://<host>:8080/",
    stack: ["Python", "FastAPI", "Uvicorn", "Atmos", "Terraform", "AWS CLI", "PyYAML"],
    features: [
      "Service Workflows UI: Plan and Deploy via Atmos",
      "Architecture graphs dashboard",
      "YAML-defined workflow templates",
      "Validate setup (checks atmos, terraform, aws on PATH)",
      "Optional auth"
    ],
    personas: ["Platform / SRE", "Infrastructure engineer"],
    maps_to: ["M03", "M13"]
  }
];

/* ------------------------------------------------------------------ */
/* Open-source / tooling stack actually used (per your list)           */
/* ------------------------------------------------------------------ */
NEXUS.stack = [
  { name: "Terraform", kind: "IaC", icon: "bi-filetype-tf", note: "Infrastructure as code (plan / apply).", license: "Open source" },
  { name: "Atmos (Cloud Posse)", kind: "IaC orchestration", icon: "bi-diagram-3", note: "Terraform workflow orchestration.", license: "Open source" },
  { name: "Kubernetes / EKS", kind: "Container platform", icon: "bi-boxes", note: "Workload runtime and cluster operations.", license: "Open source / AWS" },
  { name: "kubectl", kind: "CLI", icon: "bi-terminal", note: "Cluster inspection and actions.", license: "Open source" },
  { name: "YAML", kind: "Config", icon: "bi-filetype-yml", note: "Workflow and manifest definitions (reproducer).", license: "Open standard" },
  { name: "GitHub", kind: "Source control", icon: "bi-github", note: "Repositories and reviews.", license: "SaaS / open ecosystem" },
  { name: "GitHub Actions", kind: "CI/CD", icon: "bi-github", note: "Pipelines for build, test and deploy.", license: "Open ecosystem" },
  { name: "Argo CD", kind: "GitOps delivery", icon: "bi-arrow-repeat", note: "Declarative delivery and drift correction (or a compatible GitOps tool).", license: "Open source (CNCF)" },
  { name: "Slack", kind: "Chat / notifications", icon: "bi-slack", note: "Notifications and approvals.", license: "SaaS" },
  { name: "AWS", kind: "Cloud", icon: "bi-cloud", note: "Accounts, EKS, IAM, Service Quotas, Route53, Secrets Manager.", license: "Cloud" },
  { name: "Python / FastAPI", kind: "Backend", icon: "bi-filetype-py", note: "Tool APIs and servers.", license: "Open source" },
  { name: "Bootstrap 5", kind: "Frontend", icon: "bi-bootstrap", note: "This static UI.", license: "Open source" }
];

/* 16 platform modules (M01..M16) from the specification. */
NEXUS.modules = [
  { id: "M01", name: "Platform Experience & Self-Service Portal", group: "Experience", owner: "Platform Product", phase: "P1", status: "healthy", icon: "bi-grid-1x2", desc: "One front door: dashboard, catalog, requests, approvals, search, assistant.", caps: ["Unified dashboard","Service catalog","Request management","Approval center","Global search","AI assistant"], tool: "TL-VALIDATOR" },
  { id: "M02", name: "Cloud Account & Infrastructure Lifecycle", group: "Infrastructure", owner: "Platform Engineering", phase: "P1–P2", status: "healthy", icon: "bi-cloud", desc: "Create, register, baseline and retire accounts and infrastructure.", caps: ["Account onboarding","Environment creation","VPC & networking","Compute & storage","DNS & certificates","Decommissioning"], tool: "TL-VALIDATOR" },
  { id: "M03", name: "Infrastructure as Code & Automation", group: "Delivery", owner: "Platform Engineering", phase: "P2", status: "degraded", icon: "bi-file-earmark-code", desc: "Safe Terraform change via Atmos: plan, policy, scan, cost, apply, state, drift.", caps: ["Module registry","Plan generation","Policy validation","Cost estimation","State locking","Drift detection"], tool: "TL-WORKSHOP" },
  { id: "M04", name: "Kubernetes & Container Platform", group: "Infrastructure", owner: "Platform Engineering", phase: "P2", status: "healthy", icon: "bi-boxes", desc: "Governed container platform on EKS.", caps: ["Cluster lifecycle","Node pools","Namespaces & RBAC","Rollout restarts","Troubleshooting","Upgrades"], tool: "TL-POD" },
  { id: "M05", name: "Database Lifecycle & Management", group: "Data platform", owner: "DRE", phase: "P4", status: "pending", icon: "bi-database", desc: "Run the database fleet as a governed, recoverable service.", caps: ["Database catalog","Provisioning","Backup & PITR","Replication & HA","Performance","Migration"], tool: null },
  { id: "M06", name: "Enterprise Data Governance", group: "Governance", owner: "Data Governance Council", phase: "P4", status: "pending", icon: "bi-shield-lock", desc: "Classify, own, retain and protect data.", caps: ["Classification","Metadata catalog","Data lineage","Retention & residency","Masking","Secure deletion"], tool: null },
  { id: "M07", name: "Identity & Access Management", group: "Governance", owner: "Security", phase: "P1, P3", status: "healthy", icon: "bi-person-badge", desc: "The right people and workloads, only when needed, with proof.", caps: ["SSO & MFA","RBAC & ABAC","Just-in-time access","Access reviews","Workload identity","Session auditing"], tool: "TL-VALIDATOR" },
  { id: "M08", name: "Security & Compliance Management", group: "Governance", owner: "Security", phase: "P3", status: "degraded", icon: "bi-shield-check", desc: "Define policy, see risk and drive remediation.", caps: ["Policy-as-Code","Posture management","Vulnerability scanning","Secrets management","Findings & risk","Evidence"], tool: "TL-VALIDATOR" },
  { id: "M09", name: "AI Engineering & Multi-Agent Platform", group: "Intelligence", owner: "Platform Eng. & Security", phase: "P6", status: "blocked", icon: "bi-robot", desc: "Safe AI assistance under the same governance as everything else.", caps: ["Agent orchestration","Model gateway","RAG & knowledge base","Tool authorization","Guardrails","Execution tracing"], tool: null },
  { id: "M10", name: "Operations Automation Engine", group: "Run", owner: "Platform Eng. & SRE", phase: "P2, P5", status: "healthy", icon: "bi-gear-wide-connected", desc: "All automation runs through one controlled engine.", caps: ["Scheduled operations","Event-driven","Patch management","Secret rotation","Resource cleanup","Recovery workflows"], tool: null },
  { id: "M11", name: "Observability & SRE", group: "Run", owner: "SRE", phase: "P5", status: "healthy", icon: "bi-activity", desc: "See the platform and the services it manages, and respond well.", caps: ["Metrics & logs","Distributed tracing","Alerting","Incident management","SLOs & error budgets","Post-incident reports"], tool: "TL-POD" },
  { id: "M12", name: "FinOps & Resource Optimization", group: "Run", owner: "FinOps", phase: "P2–P7", status: "healthy", icon: "bi-cash-coin", desc: "Make cost visible before and after deployment, and reduce waste.", caps: ["Cost estimation","Budgets","Anomaly detection","Idle detection","Rightsizing","Unit economics"], tool: "TL-VALIDATOR" },
  { id: "M13", name: "Deployment & Change Management", group: "Delivery", owner: "Platform Engineering", phase: "P2", status: "healthy", icon: "bi-arrow-repeat", desc: "Consistent, risk-based change from commit to production.", caps: ["Change requests","Risk classification","Deployment windows","Verification","Rollback","Release management"], tool: "TL-WORKSHOP" },
  { id: "M14", name: "Disaster Recovery & Continuity", group: "Run", owner: "SRE", phase: "P5", status: "degraded", icon: "bi-hdd-network", desc: "Make recovery routine, tested and evidenced.", caps: ["Backup policies","RTO & RPO","Cross-region recovery","Failover & failback","Recovery runbooks","DR exercises"], tool: null },
  { id: "M15", name: "Software Supply Chain & Config", group: "Governance", owner: "Security & Platform Eng.", phase: "P3", status: "pending", icon: "bi-diagram-3", desc: "Trust what runs.", caps: ["Artifact registries","SBOM","Software signing","Provenance","Config baselines","Patch compliance"], tool: null },
  { id: "M16", name: "Enterprise Integration Hub", group: "Experience", owner: "Platform Engineering", phase: "P1+", status: "healthy", icon: "bi-plug", desc: "Connect to the tools the enterprise already uses.", caps: ["GitHub & Actions","Argo CD","Slack","ITSM & CMDB","Monitoring","Cost tools"], tool: null }
];

/* EKS troubleshooting scenarios (shown on the Troubleshooting page) */
NEXUS.troubleshooting = [
  { id: "TS-01", symptom: "Pods in CrashLoopBackOff", signal: "web-7d9f6c5b8-4xk2p · 6 restarts", cluster: "payments-prod", likely: "App exits on startup (missing config) or OOMKilled.", checks: ["kubectl logs <pod> --previous","kubectl describe pod <pod>","Check last terminated state & exit code"], action: "Open previous logs, then propose a fix (human-approved).", severity: "high" },
  { id: "TS-02", symptom: "Service has 0 ready endpoints", signal: "svc/web · selector matches, 0 ready", cluster: "payments-prod", likely: "Pods not Ready, or selector mismatch.", checks: ["kubectl get endpointslices -l kubernetes.io/service-name=web","Compare Service selector vs pod labels","Check readiness probe"], action: "Fix readiness or selector. Verify endpoints appear.", severity: "high" },
  { id: "TS-03", symptom: "Node NotReady", signal: "ip-10-0-3-21 · NotReady 8m", cluster: "search-staging", likely: "Kubelet, disk pressure or network issue on the node.", checks: ["kubectl get nodes -o wide","kubectl describe node <node>","Check node conditions & events"], action: "Cordon & drain, let autoscaler replace. Verify workloads reschedule.", severity: "medium" },
  { id: "TS-04", symptom: "Pod Pending (unschedulable)", signal: "orders-api · Pending 4m", cluster: "orders-prod", likely: "Insufficient capacity, taints, affinity, or quota.", checks: ["kubectl describe pod <pod> (Events)","Check node capacity & quotas","Check taints/affinity/topology"], action: "Scale node pool or adjust requests. Confirm scheduling.", severity: "medium" },
  { id: "TS-05", symptom: "Rollout stuck / not progressing", signal: "deploy/web · 2/4 updated", cluster: "payments-prod", likely: "New pods failing readiness; rollout paused by progress deadline.", checks: ["kubectl rollout status deploy/web","kubectl get rs -o wide","Inspect new ReplicaSet pods"], action: "Roll back to previous revision or fix the image. Verify health.", severity: "high" },
  { id: "TS-06", symptom: "Image pull failure", signal: "web · ErrImagePull", cluster: "search-staging", likely: "Wrong tag, missing registry auth, or private image.", checks: ["kubectl describe pod <pod>","Verify image tag & registry","Check pull secret / IRSA"], action: "Fix tag or registry access. Re-deploy.", severity: "medium" }
];

/* Risk tiers R0..R3 */
NEXUS.riskTiers = {
  R0: { label: "R0 Read-only", tone: "success" },
  R1: { label: "R1 Low risk", tone: "info" },
  R2: { label: "R2 Medium", tone: "warning" },
  R3: { label: "R3 High risk", tone: "danger" }
};

/* Autonomy ladder A0..A4 */
NEXUS.autonomy = [
  { level: "A0", name: "Advise", behavior: "Reads and explains. No actions." },
  { level: "A1", name: "Draft", behavior: "Prepares plans, code and requests for a human to submit." },
  { level: "A2", name: "Act with approval", behavior: "Executes after explicit human approval." },
  { level: "A3", name: "Act within policy", behavior: "Executes pre-approved, low-risk, reversible actions automatically." },
  { level: "A4", name: "Bounded autonomy", behavior: "Handles a defined class of work end to end, with limits and a kill switch." }
];

/* KPI tiles for the overview. Values are illustrative. */
NEXUS.kpis = [
  { label: "Tools online", value: "3", delta: "all tracked", trend: "up", icon: "bi-hdd-stack", tone: "primary" },
  { label: "Clusters managed", value: "4", delta: "+1", trend: "up", icon: "bi-boxes", tone: "success" },
  { label: "Policy compliance", value: "92%", delta: "+1%", trend: "up", icon: "bi-shield-check", tone: "success" },
  { label: "Open findings", value: "37", delta: "-5", trend: "down", icon: "bi-exclamation-triangle", tone: "warning" },
  { label: "Change failure rate", value: "3.1%", delta: "-0.4%", trend: "down", icon: "bi-arrow-repeat", tone: "info" },
  { label: "Monthly waste reduced", value: "$18.4k", delta: "+$2.1k", trend: "up", icon: "bi-cash-coin", tone: "primary" }
];

/* Requests & approvals */
NEXUS.requests = [
  { id: "REQ-2041", item: "Standard environment baseline", team: "Payments", requester: "a.khan", risk: "R2", status: "pending", cost: "$320/mo", submitted: "2026-02-18 09:12", env: "production" },
  { id: "REQ-2040", item: "Kubernetes namespace", team: "Search", requester: "l.ortega", risk: "R1", status: "approved", cost: "$0", submitted: "2026-02-18 08:40", env: "staging" },
  { id: "REQ-2039", item: "VPC and networking", team: "Platform", requester: "m.silva", risk: "R2", status: "pending", cost: "$140/mo", submitted: "2026-02-18 08:05", env: "non-production" },
  { id: "REQ-2038", item: "PostgreSQL (non-production)", team: "Billing", requester: "s.cohen", risk: "R2", status: "approved", cost: "$210/mo", submitted: "2026-02-17 17:55", env: "non-production" },
  { id: "REQ-2037", item: "Production database", team: "Orders", requester: "d.park", risk: "R3", status: "pending", cost: "$960/mo", submitted: "2026-02-17 16:20", env: "production" },
  { id: "REQ-2036", item: "Idle resource cleanup", team: "Data", requester: "r.novak", risk: "R1", status: "rejected", cost: "-$80/mo", submitted: "2026-02-17 14:02", env: "sandbox" },
  { id: "REQ-2035", item: "JIT admin access (8h)", team: "SRE", requester: "j.white", risk: "R3", status: "approved", cost: "$0", submitted: "2026-02-17 11:48", env: "production" },
  { id: "REQ-2034", item: "Atmos deploy: load balancer", team: "Web", requester: "t.ito", risk: "R2", status: "pending", cost: "$60/mo", submitted: "2026-02-17 10:31", env: "staging" },
  { id: "REQ-2033", item: "Rotate application secret", team: "Auth", requester: "automation", risk: "R2", status: "approved", cost: "$0", submitted: "2026-02-17 09:00", env: "production" },
  { id: "REQ-2032", item: "Decommission environment", team: "Legacy", requester: "o.meyer", risk: "R3", status: "pending", cost: "-$1,200/mo", submitted: "2026-02-16 18:14", env: "non-production" }
];

/* Operation registry (OP-*) */
NEXUS.operations = [
  { id: "OP-INV-001", name: "Sync AWS inventory (validator)", module: "M02", trigger: "Schedule, event", risk: "R0", approval: "None", owner: "Platform Eng.", slo: "99% in 15 min" },
  { id: "OP-SEC-001", name: "Posture / quota assessment", module: "M08", trigger: "Schedule", risk: "R0", approval: "None", owner: "Security", slo: "Daily" },
  { id: "OP-K8S-001", name: "Pod diagnostics (EKSense)", module: "M04", trigger: "Incident, user", risk: "R0", approval: "None", owner: "Platform Eng.", slo: "95% in 2 min" },
  { id: "OP-DB-002", name: "Create manual snapshot", module: "M05", trigger: "User, pre-change", risk: "R1", approval: "Pre-approved", owner: "DRE", slo: "95% in 30 min" },
  { id: "OP-CERT-001", name: "Renew certificate", module: "M08", trigger: "Expiry event", risk: "R1", approval: "Pre-approved", owner: "Security", slo: "Before expiry −14d" },
  { id: "OP-SEC-002", name: "Close public exposure (non-prod)", module: "M08", trigger: "Finding", risk: "R1", approval: "Pre-approved", owner: "Security", slo: "95% in 15 min" },
  { id: "OP-INF-001", name: "Atmos plan: standard environment", module: "M03", trigger: "Request", risk: "R2", approval: "Team approver", owner: "Platform Eng.", slo: "90% in 60 min" },
  { id: "OP-K8S-002", name: "Rollout restart (non-prod)", module: "M04", trigger: "User", risk: "R1", approval: "Pre-approved", owner: "Platform Eng.", slo: "95% in 10 min" },
  { id: "OP-DB-004", name: "Restore database (PITR) to new instance", module: "M05", trigger: "Request, incident", risk: "R2", approval: "Owner", owner: "DRE", slo: "Within RTO tier" },
  { id: "OP-SEC-003", name: "Rotate application secret", module: "M08", trigger: "Schedule, finding", risk: "R2", approval: "Pre-approved / TA", owner: "Security", slo: "On schedule" },
  { id: "OP-DEP-001", name: "Atmos deploy to production", module: "M13", trigger: "Change", risk: "R3", approval: "Owner + change", owner: "Platform Eng.", slo: "Per window" },
  { id: "OP-K8S-007", name: "Upgrade Kubernetes (production)", module: "M04", trigger: "Change", risk: "R3", approval: "Owner + SRE + window", owner: "Platform Eng.", slo: "Within window" },
  { id: "OP-IAM-003", name: "JIT elevation to production role", module: "M07", trigger: "Request", risk: "R3", approval: "Owner (SEC for admin)", owner: "Security", slo: "Grant in 5 min" },
  { id: "OP-DR-002", name: "Route53 traffic failover", module: "M14", trigger: "Incident", risk: "R3", approval: "Incident commander", owner: "SRE", slo: "Within RTO tier" }
];

/* Validation / checks */
NEXUS.checks = [
  { id: "CHK-POL-01", name: "Policy gate (OPA)", type: "Policy", target: "Atmos plan: standard environment", status: "pass", detail: "No hard failures. 2 advisory notices." },
  { id: "CHK-SEC-01", name: "IaC security scan (tfsec/checkov)", type: "Security", target: "Atmos plan: standard environment", status: "warning", detail: "1 medium: overly broad egress rule." },
  { id: "CHK-COST-01", name: "Cost estimate vs budget", type: "Cost", target: "Atmos plan: standard environment", status: "pass", detail: "Estimated +$320/mo, within team budget." },
  { id: "CHK-IMG-01", name: "Container image scan", type: "Security", target: "web:1.6.2", status: "fail", detail: "1 critical vulnerability. Admission would block." },
  { id: "CHK-POL-02", name: "Residency policy", type: "Policy", target: "Database: orders", status: "pass", detail: "Region allowed for classification." },
  { id: "CHK-TAG-01", name: "Mandatory tagging", type: "Policy", target: "Request REQ-2041", status: "warning", detail: "Missing tag: cost-center." },
  { id: "CHK-QUOTA-01", name: "Service Quota headroom", type: "Capacity", target: "Account: shared-services", status: "warning", detail: "EC2 vCPU limit at 82% in us-east-2." },
  { id: "CHK-SEC-02", name: "Public exposure check", type: "Security", target: "Account: shared-services", status: "pass", detail: "No public storage or databases found." },
  { id: "CHK-EKS-01", name: "EKS version support", type: "Platform", target: "Cluster: payments-prod", status: "pass", detail: "On a supported Kubernetes version." },
  { id: "CHK-SECRET-01", name: "Empty secret probe", type: "Security", target: "Secrets Manager (non-prod)", status: "warning", detail: "2 secrets have empty values." }
];

/* Security findings */
NEXUS.findings = [
  { id: "F-5012", title: "Publicly reachable object storage", severity: "critical", module: "M08", asset: "bucket: reports-nonprod", status: "open", sla: "1d" },
  { id: "F-5011", title: "Container image: critical CVE", severity: "critical", module: "M15", asset: "web:1.6.2", status: "open", sla: "2d" },
  { id: "F-5009", title: "Overly broad security group egress", severity: "medium", module: "M08", asset: "sg-env-payments", status: "in_progress", sla: "14d" },
  { id: "F-5008", title: "Unrotated secret past policy age", severity: "high", module: "M08", asset: "secret: billing-db", status: "open", sla: "7d" },
  { id: "F-5004", title: "Missing mandatory tags", severity: "low", module: "M12", asset: "12 resources", status: "in_progress", sla: "30d" },
  { id: "F-4998", title: "IAM role with unused admin permissions", severity: "high", module: "M07", asset: "role: legacy-ops", status: "open", sla: "7d" }
];

/* Audit / activity events (immutable-style) */
NEXUS.activity = [
  { ts: "2026-02-18 09:14:02", actor: "a.khan", action: "request.created", target: "REQ-2041", decision: "accepted", module: "M01", tone: "info" },
  { ts: "2026-02-18 09:12:55", actor: "policy-service", action: "policy.evaluated", target: "REQ-2041 plan", decision: "allow (advisory)", module: "M08", tone: "success" },
  { ts: "2026-02-18 08:41:10", actor: "r.ahmed", action: "approval.decided", target: "REQ-2040", decision: "approved", module: "M01", tone: "success" },
  { ts: "2026-02-18 08:40:03", actor: "eksense", action: "deployment.restart", target: "deploy/search @ staging", decision: "verified", module: "M04", tone: "success" },
  { ts: "2026-02-18 08:05:21", actor: "m.silva", action: "request.created", target: "REQ-2039", decision: "accepted", module: "M01", tone: "info" },
  { ts: "2026-02-18 07:30:00", actor: "automation", action: "operation.run.succeeded", target: "OP-SEC-003 / billing-db", decision: "verified", module: "M10", tone: "success" },
  { ts: "2026-02-18 03:00:00", actor: "validator", action: "inventory.sync", target: "OP-INV-001", decision: "verified", module: "M02", tone: "success" },
  { ts: "2026-02-17 22:14:49", actor: "eksense", action: "cluster.switch", target: "payments-prod", decision: "ok", module: "M04", tone: "info" },
  { ts: "2026-02-17 18:40:11", actor: "workshop", action: "atmos.plan", target: "standard environment", decision: "ok", module: "M03", tone: "success" },
  { ts: "2026-02-17 16:21:33", actor: "d.park", action: "request.created", target: "REQ-2037", decision: "accepted", module: "M01", tone: "info" },
  { ts: "2026-02-17 11:49:00", actor: "security", action: "access.granted", target: "j.white → prod-admin (8h)", decision: "approved", module: "M07", tone: "warning" },
  { ts: "2026-02-17 09:00:12", actor: "eksense", action: "rollout.restart_batch", target: "4 deployments", decision: "verified", module: "M04", tone: "success" }
];

/* Alerts / notifications */
NEXUS.alerts = [
  { level: "danger", icon: "bi-exclamation-octagon", title: "Critical finding", text: "Publicly reachable object storage detected (F-5012). SLA 1 day.", time: "12m ago" },
  { level: "warning", icon: "bi-boxes", title: "CrashLoopBackOff", text: "web pod restarting in payments-prod. Open EKS troubleshooting.", time: "25m ago" },
  { level: "warning", icon: "bi-hdd-network", title: "Service quota warning", text: "EC2 vCPU limit at 82% in us-east-2.", time: "1h ago" },
  { level: "info", icon: "bi-arrow-repeat", title: "Atmos plan ready", text: "Standard environment plan is ready for review.", time: "3h ago" }
];

/* Reports */
NEXUS.reports = [
  { id: "RPT-CMP-02", name: "Compliance evidence pack", type: "Compliance", period: "Feb 2026", coverage: "94%", status: "ready", owner: "Security" },
  { id: "RPT-FIN-02", name: "Cost allocation & showback", type: "FinOps", period: "Feb 2026", coverage: "100%", status: "ready", owner: "FinOps" },
  { id: "RPT-QTA-01", name: "Service Quota headroom", type: "Capacity", period: "Feb 2026", coverage: "100%", status: "ready", owner: "Capacity" },
  { id: "RPT-REL-02", name: "Reliability & SLO summary", type: "Reliability", period: "Feb 2026", coverage: "100%", status: "ready", owner: "SRE" },
  { id: "RPT-DR-01", name: "Route53 failover exercise", type: "Continuity", period: "Q1 2026", coverage: "n/a", status: "generating", owner: "SRE" },
  { id: "RPT-ACC-01", name: "Access review certification", type: "Access", period: "Q1 2026", coverage: "61%", status: "in_progress", owner: "Security" }
];

/* Integrations (visual only) */
NEXUS.integrations = [
  { name: "GitHub (source control)", icon: "bi-github", status: "connected" },
  { name: "GitHub Actions (CI/CD)", icon: "bi-github", status: "connected" },
  { name: "Argo CD (GitOps)", icon: "bi-arrow-repeat", status: "connected" },
  { name: "Slack (notifications)", icon: "bi-slack", status: "connected" },
  { name: "AWS (EKS, IAM, Quotas, Route53)", icon: "bi-cloud", status: "connected" },
  { name: "Terraform + Atmos", icon: "bi-diagram-3", status: "connected" },
  { name: "Security scanners (tfsec/checkov)", icon: "bi-shield-check", status: "degraded" },
  { name: "Documentation", icon: "bi-journal-text", status: "disconnected" }
];

/* ------------------------------------------------------------------ */
/* Admin: users, roles and resource/service access (frontend only)     */
/* ------------------------------------------------------------------ */
NEXUS.roles = [
  { id: "superadmin", name: "Super Admin", desc: "Full access including admin panel and all resources." },
  { id: "admin", name: "Admin", desc: "Manage users, approve, and operate most resources." },
  { id: "operator", name: "Operator", desc: "Run approved operations and view resources." },
  { id: "developer", name: "Developer", desc: "Self-service in non-production; view own resources." },
  { id: "security", name: "Security", desc: "Policy, findings and access reviews." },
  { id: "viewer", name: "Viewer", desc: "Read-only across the portal." }
];

/* Access matrix: which role may access which resource/service area, and at what level.
   Levels: none, view, operate, manage. */
NEXUS.accessResources = [
  "Inventory", "IAM", "Service Quotas", "Secrets", "EKS clusters",
  "Databases", "Terraform / Atmos", "Findings", "Reports", "Audit log", "Users & roles"
];
NEXUS.accessMatrix = {
  superadmin: { Inventory:"manage", IAM:"manage", "Service Quotas":"manage", Secrets:"manage", "EKS clusters":"manage", Databases:"manage", "Terraform / Atmos":"manage", Findings:"manage", Reports:"manage", "Audit log":"view", "Users & roles":"manage" },
  admin:      { Inventory:"manage", IAM:"operate", "Service Quotas":"operate", Secrets:"view", "EKS clusters":"operate", Databases:"operate", "Terraform / Atmos":"operate", Findings:"operate", Reports:"view", "Audit log":"view", "Users & roles":"manage" },
  operator:   { Inventory:"view", IAM:"view", "Service Quotas":"operate", Secrets:"none", "EKS clusters":"operate", Databases:"operate", "Terraform / Atmos":"operate", Findings:"view", Reports:"view", "Audit log":"none", "Users & roles":"none" },
  developer:  { Inventory:"view", IAM:"none", "Service Quotas":"view", Secrets:"none", "EKS clusters":"view", Databases:"view", "Terraform / Atmos":"operate", Findings:"view", Reports:"view", "Audit log":"none", "Users & roles":"none" },
  security:   { Inventory:"view", IAM:"operate", "Service Quotas":"view", Secrets:"view", "EKS clusters":"view", Databases:"view", "Terraform / Atmos":"view", Findings:"manage", Reports:"view", "Audit log":"view", "Users & roles":"view" },
  viewer:     { Inventory:"view", IAM:"view", "Service Quotas":"view", Secrets:"none", "EKS clusters":"view", Databases:"view", "Terraform / Atmos":"view", Findings:"view", Reports:"view", "Audit log":"none", "Users & roles":"none" }
};

NEXUS.users = [
  { id: "u-001", name: "Ashish Gajjar", email: "ashish.gajjar@example.com", role: "superadmin", team: "Platform", status: "active", mfa: true, last: "2026-02-18 09:02" },
  { id: "u-002", name: "Ravi Ahmed", email: "r.ahmed@example.com", role: "admin", team: "Platform", status: "active", mfa: true, last: "2026-02-18 08:40" },
  { id: "u-003", name: "Lara Ortega", email: "l.ortega@example.com", role: "developer", team: "Search", status: "active", mfa: true, last: "2026-02-18 08:05" },
  { id: "u-004", name: "Dan Park", email: "d.park@example.com", role: "operator", team: "Orders", status: "active", mfa: false, last: "2026-02-17 16:20" },
  { id: "u-005", name: "Sara Cohen", email: "s.cohen@example.com", role: "security", team: "Security", status: "active", mfa: true, last: "2026-02-17 17:55" },
  { id: "u-006", name: "Omar Meyer", email: "o.meyer@example.com", role: "viewer", team: "Legacy", status: "suspended", mfa: false, last: "2026-02-10 12:00" },
  { id: "u-007", name: "Tomo Ito", email: "t.ito@example.com", role: "developer", team: "Web", status: "active", mfa: true, last: "2026-02-17 10:31" }
];

NEXUS.accessLevelMeta = {
  none:    { label: "No access", tone: "secondary" },
  view:    { label: "View",      tone: "info" },
  operate: { label: "Operate",   tone: "warning" },
  manage:  { label: "Manage",    tone: "success" }
};

/* ------------------------------------------------------------------ */
/* Self-service: Describe → YAML, and the Infrastructure Builder        */
/* ------------------------------------------------------------------ */

/* Example natural-language requirements for the Describe → YAML page */
NEXUS.requirementExamples = [
  "Create an EKS namespace called payments-staging with a resource quota of 8 CPU and 16Gi memory, and a default-deny network policy.",
  "Deploy the web Helm chart version 1.6.2 to the shop namespace with 3 replicas, image web:1.6.2, and an ingress host shop.example.com.",
  "Provision a standard non-production environment for the Search team in us-east-2 with logging and budgets enabled.",
  "Create a PostgreSQL database for Orders, Multi-AZ, with 7-day backups and point-in-time recovery."
];

/* Builder catalog: kinds of infrastructure and their parameters (for the GUI builder) */
NEXUS.builderKinds = [
  { id: "namespace", name: "Kubernetes Namespace", icon: "bi-collection" },
  { id: "helm", name: "Helm Release (app deploy)", icon: "bi-box-seam" },
  { id: "environment", name: "Standard Environment (Atmos)", icon: "bi-diagram-3" },
  { id: "database", name: "Database", icon: "bi-database" }
];

NEXUS.statusMeta = {
  healthy:     { label: "Healthy",     tone: "success", icon: "bi-check-circle-fill" },
  degraded:    { label: "Degraded",    tone: "warning", icon: "bi-exclamation-triangle-fill" },
  blocked:     { label: "Blocked",     tone: "danger",  icon: "bi-x-octagon-fill" },
  pending:     { label: "Planned",     tone: "secondary", icon: "bi-hourglass-split" },
  approved:    { label: "Approved",    tone: "success", icon: "bi-check-circle" },
  rejected:    { label: "Rejected",    tone: "danger",  icon: "bi-x-circle" },
  pass:        { label: "Pass",        tone: "success", icon: "bi-check-circle" },
  warning:     { label: "Warning",     tone: "warning", icon: "bi-exclamation-triangle" },
  fail:        { label: "Fail",        tone: "danger",  icon: "bi-x-circle" },
  open:        { label: "Open",        tone: "danger",  icon: "bi-circle" },
  in_progress: { label: "In progress", tone: "warning", icon: "bi-hourglass-split" },
  ready:       { label: "Ready",       tone: "success", icon: "bi-check-circle" },
  generating:  { label: "Generating",  tone: "info",    icon: "bi-arrow-repeat" },
  connected:   { label: "Connected",   tone: "success", icon: "bi-check-circle-fill" },
  disconnected:{ label: "Disconnected",tone: "secondary", icon: "bi-dash-circle" },
  critical:    { label: "Critical",    tone: "danger",  icon: "bi-exclamation-octagon-fill" },
  high:        { label: "High",        tone: "danger",  icon: "bi-exclamation-triangle-fill" },
  medium:      { label: "Medium",      tone: "warning", icon: "bi-exclamation-triangle" },
  low:         { label: "Low",         tone: "info",    icon: "bi-info-circle" }
};
