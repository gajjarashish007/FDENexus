# Part 2: Functional Module Specifications

Each module is independent in ownership and data, but integrated through shared platform services: the policy decision point, the workflow engine, the operation registry and the audit ledger. A module is a **logical module inside the modular core** unless Part 6 says it is a separate deployable service.

Every module follows the same rules: its APIs are authorized by the policy decision point, every state change is audited, every long-running action is a workflow, and every automated action is an operation in the registry (Part 7).

## M01: Platform Experience and Self-Service Portal

**Purpose:** one front door for all users, with role-aware navigation and governed self-service. **Owner:** Platform Product. **Phase:** P1 (assistant in P6).

| Capability | Specification |
|---|---|
| Unified dashboard | Role-based tiles: my requests, pending approvals, my resources, health, cost, security findings, upcoming changes. Each tile reads from the same governed APIs as external clients. |
| Role-based navigation | Menu items and actions are driven by permissions from the policy decision point. Hidden is not secure: the API enforces the same rules. |
| Service catalog | Versioned catalog items with owner, description, inputs schema, policy and cost hints, approval tier, SLA, and lifecycle (draft, published, deprecated, retired). |
| Request management | Guided forms generated from the item's input schema. Validation, estimated cost, policy pre-check, request status timeline, cancellation and re-submit. |
| Approval center | One inbox for all approvals (resource, access, change, data access). Shows risk tier, plan summary, cost, policy results, requester history. Delegation and escalation supported. SoD blocks self-approval. |
| Deployment dashboard | Live and historical deployments with stage status, logs, plan diff, verification results and rollback action. |
| Resource inventory | Searchable inventory by owner, tag, environment, account and type, with relationships and compliance state. Source: M02 and the collectors. |
| Operational health | Service health, SLO status, open incidents, maintenance windows. Source: M11. |
| Notifications | In-app, email and chat. User-configurable by event type and severity. Approval reminders and escalations. |
| Global search | Permission-trimmed search across catalog, requests, resources, runbooks, documents and people. Results are filtered by the caller's access, never after the fact in the browser. |
| AI conversational assistant | Embedded chat that answers questions, drafts requests and explains plans, using the caller's identity and permissions. It can submit a request on the user's behalf only through the normal request API, with the normal approvals (M09). |

**Key controls:** SC-01, SC-02, SC-11, SC-21. **Integrations:** IdP, ITSM, chat, email. **Accessibility:** target WCAG 2.2 AA (NFR-ACC-01).

## M02: Cloud Account and Infrastructure Lifecycle

**Purpose:** create, register, baseline and retire cloud accounts and the infrastructure inside them. **Owner:** Platform Engineering. **Phase:** P1 (inventory, onboarding), P2 (provisioning).

| Capability | Specification |
|---|---|
| Account onboarding | Register an existing account: verify ownership, assume a read-only discovery role, run baseline assessment, apply the required tags and guardrails, then enable features step by step. |
| Account provisioning | Create new accounts through the organization structure with the standard baseline: logging, security tooling, network attachment, IAM boundary, budgets. Evaluate AWS Organizations with Control Tower or a Terraform-based account factory (OD-04). |
| Account registration | Metadata record: business owner, technical owner, cost center, data classification ceiling, environment type, regions allowed, compliance scope. |
| Environment creation | An environment is a named set of resources with a purpose (sandbox, development, test, staging, production) and an applied policy set. Created from catalog templates. |
| Regions and AZ management | Allowed-region policy per environment and data classification. AZ spread rules for production. Capacity and quota awareness. |
| VPC and networking | Standard VPC patterns, subnets, routing, NAT, endpoints, connectivity to shared services, security groups and network ACL baselines, IP address management. |
| Compute provisioning | Approved instance families and images, autoscaling groups, launch templates, patching baseline. |
| Storage provisioning | Block, file and object storage patterns with encryption, backup tags and lifecycle rules by default. |
| Kubernetes infrastructure | Hand-off to M04 for cluster lifecycle. M02 supplies the network, IAM and encryption foundations. |
| Load balancing | Application and network load balancers from templates, WAF association, access logging. |
| DNS and certificates | Delegated zones per environment, record management with ownership checks, certificate issuance and renewal (with M08). |
| Decommissioning | Dependency analysis, data protection check (backup, retention, legal hold), owner and approver sign-off, staged shutdown with a recovery window, then destruction and evidence. |

**Key controls:** SC-04, SC-09, SC-10, SC-20. **Integrations:** cloud provider APIs, IdP, CMDB.

## M03: Infrastructure as Code and Automation

**Purpose:** safe, repeatable infrastructure change through Terraform. **Owner:** Platform Engineering. **Phase:** P2.

| Capability | Specification |
|---|---|
| Terraform module registry | Curated, versioned modules with owner, tests, documentation, input and output contracts, security review status and support level. |
| Version-controlled templates | Catalog items reference module versions in source control. Changes go through pull requests with review and automated checks. |
| Automated plan generation | Runs in an isolated execution worker with short-lived scoped credentials. Output stored in object storage, encrypted, with a content hash. |
| Plan review | Human-readable plan summary: create, change and destroy counts, sensitive changes highlighted, blast radius, cost delta, policy results. The reviewed plan is the plan that is applied (hash-bound). |
| Policy validation | Plan evaluated by the policy decision point (for example against OPA policies). Hard failures block. Advisory findings warn. |
| Security scanning | IaC static analysis and misconfiguration checks on code and plan. |
| Cost estimation | Estimated monthly cost delta before approval, with budget impact. |
| Deployment orchestration | Workflow: plan, validate, approve, schedule, apply, verify, record. One concurrent apply per state. |
| State management | Remote encrypted state per environment and component, access restricted to execution workers. |
| State locking | Locking on every plan and apply. Stuck-lock recovery is an audited, approved operation. |
| Drift detection | Scheduled plan-only runs. Drift is classified (benign, risky, unauthorized) and routed to a remediation workflow. |
| Rollback and recovery | Roll-forward by default. Rollback means applying the previous known-good module version or snapshot. Destructive reverts need higher approval. State backup and restore procedure. |
| Module versioning and deprecation | Semantic versions, deprecation notices, usage inventory showing which deployments use a version, and an upgrade workflow. |

**Key controls:** SC-04, SC-09, SC-13, SC-20. **Note:** Terraform licensing changes in recent years make OpenTofu a candidate alternative (OD-05).

## M04: Kubernetes and Container Platform Management

**Purpose:** provide a governed container platform on EKS. **Owner:** Platform Engineering. **Phase:** P2 (core), P3 (security), P5 (backup, upgrades at scale).

| Capability | Specification |
|---|---|
| Cluster lifecycle | Create, configure, upgrade and retire clusters from versioned templates. One minor version at a time. Pre-upgrade checks and post-upgrade verification. |
| Node pool management | Pool definitions by workload type and isolation need. Managed node groups or an autoscaler such as Karpenter, based on decision OD-06. |
| Autoscaling | Pod and node autoscaling policies with guardrails and cost caps. |
| Workload deployment | GitOps-based delivery (for example Argo CD) with environment promotion and drift correction. |
| Namespace management | Self-service namespaces with owner, quota, default network policy, labels and cost allocation. |
| RBAC | Mapping from platform roles to Kubernetes roles. No direct cluster-admin for people in production (JIT only). |
| Network policies | Default deny with approved patterns. |
| Ingress management | Standard ingress controllers, certificate and DNS automation, WAF integration. |
| Storage and PVC lifecycle | Storage classes, encryption, snapshot policy, orphan volume detection, reclaim policy governance. |
| Container image scanning | Scan on build, on admission and on schedule. Block on critical findings per policy. |
| Resource quotas | Namespace-level requests and limits, with right-sizing recommendations (M12). |
| Pod health | Restart loops, readiness, OOM kills, evictions and scheduling failures surfaced in the portal. |
| Scheduling analysis | Explains why a pod is pending: capacity, taints, affinity, quotas, topology constraints. |
| Kubernetes upgrades | Version compatibility checks (APIs, add-ons), staged rollout (non-production first), PDB-aware node rotation, rollback plan. |
| Cluster backup and recovery | Cluster state and persistent data backup, restore tests, and rebuild-from-code procedure. |

**Key controls:** SC-09, SC-10, SC-12, SC-13. **Integrations:** EKS, registry, GitOps controller, M08, M11.

## M05: Database Lifecycle and Management

**Purpose:** run the database fleet as a governed, observable and recoverable service. **Owner:** DRE. **Phase:** P4 (performance and forecasting in P5).

**Database categories:** relational (for example PostgreSQL, MySQL), NoSQL (document, key-value), cache (Valkey or Redis), search (OpenSearch), warehouse, and streaming (managed Kafka or equivalent).

| Capability | Specification |
|---|---|
| Database catalog | Approved engines, versions, sizes, topologies and support levels by category, each with default backup, encryption, HA and monitoring. |
| Provisioning | Catalog-driven. Mandatory fields: owner, data classification, environment, backup policy, retention class, RTO and RPO tier. |
| Instance and cluster configuration | Parameter groups, storage, networking, maintenance windows, monitoring. Configuration baseline and drift detection. |
| Version management | Supported version matrix, end-of-support tracking and upgrade planning. |
| Schema management | Schema changes through reviewed migration scripts, with dry-run, lock-impact estimate and rollback or compensating script. Platform never edits production schema without an approved change. |
| Users and roles | Application and human database roles. Humans via JIT and IAM authentication where available. No shared admin accounts. |
| Credential rotation | Automatic rotation through the secrets manager, with consumer notification and verification. |
| Encryption | Encryption at rest with customer-managed keys, in-transit TLS enforced. |
| Backup and restore | Policy-based backups, immutable copies, scheduled restore validation. |
| Point-in-time recovery | PITR where supported, with a restore-to-new-instance workflow and cutover guidance. |
| Replication and HA | Multi-AZ by default for production. Read replicas, cross-region replicas by tier. |
| Failover | Automated for managed HA, orchestrated and approved for cross-region. Failback procedure. |
| Performance monitoring | Key metrics, slow queries, locks, connections, replication lag. |
| Query analysis and index recommendations | Recommendation only. Applying an index is a change operation. |
| Capacity forecasting | Storage, connections and compute trend forecasting, feeding M12 and M11. |
| Patching and upgrades | Minor patching in windows, major upgrades through blue/green or replica-based cutover with rollback. |
| Migration | Source assessment, schema and data migration, validation, cutover and rollback plan. |
| Data archival | Policy-based archival to lower-cost storage with retrieval process. |
| Secure decommissioning | Final backup per retention policy, dependency check, owner approval, deletion and evidence (including key handling per M06). |

**Key controls:** SC-05, SC-07, SC-16, SC-18. **Integrations:** cloud database services, secrets manager, M06, M11, M14.

## M06: Enterprise Data Governance

**Purpose:** know what data exists, who owns it, how sensitive it is, and enforce rules over it. **Owner:** Data Governance Council. **Phase:** P4 (AI data governance in P6).

| Capability | Specification |
|---|---|
| Data classification | Four levels: Public, Internal, Confidential, Restricted. Each level maps to required controls (encryption, access approval, masking, residency, retention). |
| Data ownership | Every data asset has an accountable owner. Assets without owners are flagged and escalated. |
| Data stewardship | Stewards manage definitions, quality rules and access requests for their domain. |
| Metadata catalog | Technical and business metadata for databases, tables, buckets, streams and platform datasets. |
| Data lineage | Table and column lineage where tooling allows. Pipeline-level lineage as a minimum. Platform lineage: which request created which resource. |
| Data discovery | Automated scanning of approved stores for assets and sensitive patterns. |
| Data quality | Rule definitions, scheduled checks, scorecards and issue routing. |
| Data retention | Retention classes with legal hold override. Automated enforcement with approval for deletion of Restricted data. |
| Data residency | Region policies by classification and legal requirement. Deployment and replication blocked if they violate residency. |
| Data masking | Masking and tokenization patterns for non-production copies and AI use. |
| Encryption | Key hierarchy by classification, key ownership and rotation (SC-05). |
| Data access approval | Request, justification, owner approval, time-bound grant, review. |
| Sensitive-data detection | Pattern and classifier-based detection in data stores, logs and (for platform data) prompts. |
| Data archival | Defined archival tiers and retrieval service levels. |
| Secure data deletion | Deletion by policy: logical delete, crypto-shredding by key destruction where applicable, verification and evidence. |
| Compliance evidence | Evidence packages: classification coverage, access reviews, retention actions, deletion certificates. |

**Governance of platform data, including AI data (conversations, embeddings, prompts, generated content):** defined in Part 5, AI and Platform Data Governance.

**Key controls:** SC-05, SC-16. **Integrations:** M05, M07, M08, M09, data platforms.

## M07: Identity and Access Management

**Purpose:** the right people and workloads have the right access, only when needed, with proof. **Owner:** Security. **Phase:** P1 (SSO, RBAC), P3 (JIT, PAM, reviews).

| Capability | Specification |
|---|---|
| SSO and MFA | The platform never stores passwords. Authentication through the enterprise IdP using OIDC (preferred) or SAML. MFA enforced by the IdP, with step-up for high-risk actions. |
| SCIM provisioning | Users and groups synchronized from the IdP. Deprovisioning removes platform access automatically. |
| RBAC | Platform roles by persona, scoped to tenant, team or environment. |
| ABAC | Attributes (team, environment, classification, risk tier, time, device posture where available) refine decisions through the policy decision point. |
| IAM role management | Cloud role catalog with permission boundaries and owner. Role creation and change follow the request workflow. |
| Just-in-time access | Time-boxed elevation to production roles after approval and reason. |
| Privileged access management | Privileged sessions via brokered access, session recording where feasible, break-glass with alerts and review. |
| Temporary permissions | Every grant has an expiry. Default maximum durations per role. |
| Access expiration and revocation | Automatic expiry. Automatic revocation on role change, leaving the company or a policy violation. |
| Access reviews | Periodic certification campaigns by owner and risk. Unreviewed access is revoked after the grace period. |
| Approval workflows | Manager plus resource owner, with security for high-risk. No self-approval. |
| Service identities and workload identity | Platform components, automations and agents use dedicated, short-lived, narrowly scoped identities (for example IRSA or Pod Identity, and cross-account role assumption). No long-lived keys. |
| Session auditing | All platform sessions and elevated sessions are logged with identity, action and target. |

**Separation of duties and least privilege** are enforced in policy (Part 4, IAM Permission Model). **Key controls:** SC-01, SC-02, SC-03, SC-17.

## M08: Security and Compliance Management

**Purpose:** one place to define policy, see risk and drive remediation. **Owner:** Security. **Phase:** P3.

| Capability | Specification |
|---|---|
| Security policy engine | Central policy decision point with versioned policy bundles, shadow mode, test suites and staged rollout. |
| Policy-as-Code | Policies in source control with review and automated tests. Rego (OPA) is the primary candidate (OD-08). |
| Cloud security posture management | Continuous configuration assessment against policy and benchmark rules. |
| Vulnerability scanning | Hosts, images and dependencies, with risk-based prioritization. |
| Infrastructure security scanning | IaC and runtime configuration checks. |
| Container security | Image scanning, admission control, runtime signals. |
| Image signing and SBOM | Signature verification at admission (with M15). |
| Secrets management | Central secrets manager, rotation workflows, secret scanning in repositories and logs. |
| Certificate lifecycle | Inventory, issuance, renewal and expiry alerts. |
| KMS and encryption | Key policy standards, rotation and separation of key administrators from key users. |
| Network security | Segmentation standards, security group review, egress control. |
| Public exposure detection | Detects publicly reachable storage, databases and endpoints. Auto-open of a finding, optional auto-remediation by policy. |
| Compliance monitoring | Control library mapped to frameworks. Evaluate CIS Benchmarks, NIST CSF, ISO 27001 and SOC 2 according to the organization's obligations (OD-09). |
| Security findings | Normalized finding model: asset, severity, evidence, owner, SLA, status. |
| Risk scoring | Combines severity, exploitability, exposure, data classification and business criticality. |
| Remediation workflows | Assign, fix via platform operation, verify, close. Exceptions require expiry and approver. |
| Audit evidence | Evidence collection tied to controls, exportable for auditors. |

**Key controls:** SC-04, SC-07, SC-12, SC-13, SC-19.

## M09: AI Engineering and Multi-Agent Platform

**Purpose:** safe, useful AI assistance across the lifecycle, under the same governance as everything else. **Owner:** Platform Engineering with Security. **Phase:** P6 (multi-agent autonomy in P7).

**Non-negotiable rule:** agents act through the same APIs and the same policy decision point as people. They cannot bypass authorization, policy checks or production approvals.

### Agent catalog

| Agent | Purpose | Read tools | Write or propose tools | Initial autonomy |
|---|---|---|---|---|
| Infrastructure architecture | Recommend designs and trade-offs from requirements and standards | Catalog, standards, inventory, cost | Draft design document | A0 to A1 |
| Infrastructure provisioning | Turn approved intent into catalog requests and plans | Catalog, policy results, quotas | Submit request (user identity), prepare plan | A1 to A2 |
| Terraform generation | Draft and review Terraform within approved modules | Module registry, standards | Propose pull request | A1 |
| Kubernetes troubleshooting | Diagnose workload and cluster issues from evidence | Pods, events, logs, metrics (read-only) | Propose remediation operation | A0, then A2 |
| Database operations | Explain performance issues, propose indexes, plan maintenance | Metrics, query stats, config | Propose change operation | A0 to A1 |
| Security analysis | Triage findings, explain risk, propose fixes | Findings, inventory, policy | Propose remediation | A0 to A2 |
| Data governance | Suggest classifications, owners and retention | Metadata catalog, scan results | Propose catalog update | A1 |
| FinOps | Explain cost changes, suggest rightsizing | Cost, usage, inventory | Propose optimization operation | A0 to A2 |
| Incident management | Correlate alerts, summarize, suggest runbook steps | Alerts, topology, change history | Propose runbook execution | A0 to A2 |
| Observability | Build queries, explain dashboards, suggest alerts and SLOs | Metrics, logs, traces | Propose alert rule | A0 to A1 |
| Documentation and knowledge retrieval | Answer questions from approved knowledge with citations | Knowledge base (access-aware) | None | A0 |

### Platform components

| Component | Specification |
|---|---|
| Agent orchestration | Controls agent runs, task decomposition, hand-offs, step and time limits. Supports one agent, then supervised multi-agent flows. |
| Model gateway | Single entry point to models. Authentication, model allow-list, routing, rate limits, token and cost budgets, request and response logging per policy, content filters, provider failover. |
| Model selection | Per-task model policy by data classification, capability, latency and cost. Restricted data only to approved model endpoints. |
| Prompt versioning | Prompts and system instructions in source control with version, owner, test results and rollout stage. |
| Retrieval-augmented generation | Retrieval from approved sources only, with the caller's permissions applied at retrieval time. Citations required. |
| Knowledge base and vector database | Curated documents (runbooks, standards, architecture, past incidents). Ingestion with owner, classification and review date. |
| Agent memory boundaries | Short-term memory scoped to a session. No cross-user memory. Long-term memory only for approved, non-sensitive preferences, with user visibility and deletion. |
| Tool registry | Every tool has a schema, owner, risk tier, required permissions, rate limit and an allow-list of agents. |
| Tool authorization | Each tool call is authorized by the policy decision point using the user identity, the agent identity and the operation risk tier. Both must be allowed. |
| Human approval | State-changing tool calls above the pre-approved tier create an approval request, shown with the agent's evidence and plan. |
| Agent evaluation | Offline evaluation sets per agent (accuracy, groundedness, safety, policy compliance), run on every prompt, model or tool change. Online sampling and review. |
| Hallucination controls | Grounding in retrieved evidence, required citations, "unknown" as a valid answer, output validation against schemas, cross-checks against inventory. |
| Prompt injection protection | Content from tools, logs and documents is treated as untrusted data. Separation of instructions and data, tool allow-lists, output filtering, no tool call derived solely from untrusted content without policy check. |
| Data leakage prevention | Redaction before model calls, classification-aware routing, output scanning, no training on platform data by providers (contractual and technical control). |
| Execution tracing | Full trace per run: prompts, retrieved sources, tool calls, decisions, approvals, tokens and cost. Access-controlled and retained per policy. |
| Cost monitoring | Budgets per team and agent, alerts, hard stops, cost per outcome reporting. |
| Kill switch | Per agent, per tool and global. Tested regularly. |

**Key controls:** SC-14, SC-15, SC-16. Full architecture in Part 6.

## M10: Operations Automation Engine

**Purpose:** all automation runs through one controlled engine. **Owner:** Platform Engineering and SRE. **Phase:** P2 (engine core), P5 (operation library).

| Capability | Specification |
|---|---|
| Scheduled operations | Calendar and cron-style schedules with maintenance windows and holiday freezes. |
| Event-driven automation | Triggered by platform or cloud events (for example resource created, finding opened, certificate nearing expiry). |
| Incident-triggered automation | Triggered by alert or incident state, running diagnostics first and remediation only if allowed by tier. |
| Resource lifecycle automation | Expiry of temporary resources, tagging enforcement, ownership reminders, cleanup of orphaned resources. |
| Patch management | Patch baselines, rings (non-production first), windows, verification and rollback. |
| Backup scheduling | Policy-driven schedules, validation restores. |
| Database maintenance | Statistics, vacuum, minor patching, replica checks. |
| Kubernetes maintenance | Node rotation, add-on updates, certificate renewal. |
| Certificate renewal | Automatic renewal with deployment verification. |
| Secret rotation | Rotation with consumer verification and rollback. |
| Resource cleanup | Idle resource shutdown, snapshot pruning, with owner notification and grace period. |
| Capacity optimization | Rightsizing and scaling adjustments within guardrails. |
| Recovery workflows | Restore, failover and rebuild workflows from M14. |
| Configuration remediation | Drift correction toward baselines under policy. |

**Mandatory record for every automation:** owner, trigger, preconditions, authorization scope, approval requirement, execution timeout, retry strategy, idempotency controls, verification and audit evidence. The full contract is in Part 7. An automation without a complete record cannot be enabled.

## M11: Observability and SRE

**Purpose:** see the platform and the services it manages, and respond well. **Owner:** SRE. **Phase:** P5 (platform self-monitoring from P1).

| Capability | Specification |
|---|---|
| Centralized metrics | Time-series metrics through OpenTelemetry and Prometheus-compatible collection. |
| Logs | Structured logging with correlation identifiers, central search and retention tiers. |
| Distributed tracing | OpenTelemetry traces across portal, API, workflows and workers. |
| Alert management | Alert definitions as code, severity, ownership, routing, silencing and maintenance windows. |
| Alert correlation | Group related alerts by topology and change history to reduce noise. |
| Incident management | Declare, assign, communicate, track, resolve. Integrates with the ITSM and paging tools. |
| Root cause analysis | Timeline of changes, deployments, config drift and alerts. Agent-assisted analysis, human-confirmed. |
| SLO management | SLIs, SLOs, burn-rate alerts. |
| Error budgets | Budget tracking and policy (for example slow releases when budget is spent). |
| Service health | Aggregated health from SLOs, dependencies and incidents. |
| Dependency mapping | Service and infrastructure relationships from inventory, traces and declared dependencies. |
| Runbook automation | Runbooks as steps with embedded safe operations (from the registry). |
| Capacity planning | Trend and forecast across compute, storage, database and quotas. |
| Reliability analytics | Trends in incidents, MTTR, change failure rate, toil. |
| Post-incident reporting | Template-driven report with timeline, impact, causes, actions and owners. Follow-up actions tracked to completion. |

## M12: FinOps and Resource Optimization

**Purpose:** make cost visible before and after deployment, and reduce waste. **Owner:** FinOps. **Phase:** P2 (estimates), P5 (reporting), P7 (intelligence).

| Capability | Specification |
|---|---|
| Cost estimation | Pre-approval cost delta from IaC plans. |
| Budgets | Per team, environment and account, with alerts and enforcement options. |
| Cost allocation | Tag and account-based allocation, with untagged cost shown separately. |
| Resource tagging | Mandatory tag policy enforced at request time and by drift checks. |
| Cost forecasting | Trend-based and plan-based forecasts. |
| Anomaly detection | Detect unusual spend and notify the owner. |
| Idle resource identification | Utilization-based detection with owner confirmation. |
| Rightsizing | Compute, database and storage recommendations with risk indicators. |
| Reserved capacity recommendations | Commitment recommendations, reviewed by FinOps. |
| Storage optimization | Lifecycle tiers, snapshot and backup cost review. |
| Cost center reporting | Chargeback or showback reports. |
| Unit economics | Cost per service, per transaction or per environment where data exists. |
| Cost governance | Budget approvals, exception handling, optimization KPIs. |

## M13: Deployment and Change Management

**Purpose:** consistent, risk-based change from commit to production. **Owner:** Platform Engineering. **Phase:** P2.

| Capability | Specification |
|---|---|
| CI/CD integrations | Triggers and status exchange with source control and pipeline systems. The platform governs change. It does not replace the CI system. |
| Change requests | Standard, normal and emergency change types. Pre-approved standard changes for low-risk, repeatable work. |
| Approval workflows | Risk-tier-based approvers, including CAB for high-risk. |
| Risk classification | Computed from target environment, blast radius, data classification, reversibility, change size and recent failures. |
| Deployment windows | Freeze periods, windows per environment, exceptions with approval. |
| Scheduling | Scheduled start with pre-checks at start time. |
| Pipeline execution | Run, observe and record pipeline stages. |
| Deployment verification | Automated health checks, SLO guard, smoke tests. Failure triggers rollback policy. |
| Rollback | Automatic where defined, otherwise one-click with approval. |
| Change history | Immutable record: who, what, when, why, approvals, results. |
| Conflict detection | Detect overlapping changes on the same service, dependency or window. |
| Release management | Release trains, notes, version and artifact traceability. |

## M14: Disaster Recovery and Business Continuity

**Purpose:** make recovery routine, tested and evidenced. **Owner:** SRE. **Phase:** P5 (policy design from P4).

| Capability | Specification |
|---|---|
| Backup policies | Tiered policies by service criticality with immutability options. |
| Backup validation | Scheduled restore tests, integrity checks and reporting. |
| Recovery objectives | RTO and RPO captured per service and compared with measured results. |
| RTO and RPO management | Tier model (Part 8), gap analysis and remediation tracking. |
| Cross-region recovery | Replication and rebuild designs by tier. |
| Replication | Database, object and secret replication health monitoring. |
| Failover | Orchestrated, approved workflows with pre-checks. |
| Failback | Controlled return with data reconciliation. |
| Recovery runbooks | Executable runbooks linked to services. |
| DR exercises | Scheduled, scoped exercises with success criteria and evidence capture. |
| Evidence collection | Timestamps, logs, test results and sign-offs. |
| Platform-level DR | The platform's own recovery design, tested separately (Part 6). |

## M15: Software Supply Chain and Configuration Management

**Purpose:** trust what runs. **Owner:** Security and Platform Engineering. **Phase:** P3 (baselines and drift to P5).

| Capability | Specification |
|---|---|
| Artifact registries | Governed registries for images, packages and modules with retention and access control. |
| Container image management | Approved base images, rebuild on vulnerability, deprecation. |
| SBOM | SBOM generation and storage (SPDX or CycloneDX), queryable by component. |
| Software signing | Sign artifacts at build time. Verify at admission and deployment. |
| Provenance | Build provenance attestations (for example SLSA levels as a target). |
| Dependency scanning | Known-vulnerability and license checks. |
| Configuration baselines | Hardened baselines for operating systems, clusters and services. |
| Configuration drift | Detect and report deviation. Remediate under policy. |
| Patch compliance | Patch status by asset with SLAs per severity. |
| Release artifact management | Link artifact versions to changes, deployments and environments. |

## M16: Enterprise Integration Hub

**Purpose:** connect to the tools the enterprise already uses, reliably and securely. **Owner:** Platform Engineering. **Phase:** P1 onward.

| Integration area | Pattern | Examples of systems (generic) |
|---|---|---|
| Identity providers | OIDC, SAML, SCIM | Enterprise IdP |
| CI/CD | Webhook plus API | Pipeline systems |
| ITSM and change management | REST API, bidirectional sync | Ticketing, change, CMDB |
| Monitoring | Pull and push, alert webhook | Metrics, logging, paging tools |
| Messaging | Chat apps and email | Notifications and approvals |
| Documentation | API, index sync | Wiki and knowledge tools |
| Source control | Webhook, app installation | Git hosting |
| Cloud-native services | SDK and events | Organizations, config, security and cost services |
| Security tools | API, finding import | Scanners and posture tools |
| Cost management | Export ingestion | Billing and cost tools |

Contracts, webhooks, event schemas, retries, rate limits, authentication and failure handling are specified in Part 10 (API Specifications). **Principles:** adapters are isolated so one failing integration cannot stop the platform. Each adapter has a circuit breaker, a dead-letter queue and a health indicator. Credentials come from the secrets manager and are rotated.
