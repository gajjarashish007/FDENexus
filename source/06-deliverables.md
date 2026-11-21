# Part 10: Final Architecture Deliverables

## 10.1 API Specifications

### Conventions

| Topic | Specification |
|---|---|
| Style | REST over HTTPS with JSON. Resource-oriented. Custom actions use a `:action` suffix. Base path `/api/v1`. An OpenAPI description is the contract, kept in source control. |
| Authentication | OIDC bearer tokens for users. Short-lived workload tokens for services and automations. Webhooks use signatures (below). |
| Authorization | Every call is evaluated by the policy decision point. Deny by default. Decisions are logged with correlation id. |
| Identifiers | UUIDs. Human-readable references in addition for requests and changes. |
| Idempotency | `Idempotency-Key` header required on create and action calls that start work. Same key and same body returns the original result. |
| Concurrency | `ETag` and `If-Match` for updates (optimistic locking). |
| Asynchronous work | Long operations return `202 Accepted` with a link to a run or request resource. Clients poll or subscribe to events. |
| Pagination and filtering | Cursor pagination, maximum page size, filters by documented fields. No unbounded list. |
| Errors | Problem Details style (type, title, status, detail, correlation id, field errors). Stable error codes. |
| Rate limits | Per user, per tenant and per integration. `429` with `Retry-After`. Heavier limits on expensive endpoints. |
| Correlation | `X-Correlation-Id` accepted and returned. Propagated to workflows, workers and audit. |
| Versioning | Major version in path. Additive changes are non-breaking. Deprecations announced with `Deprecation` and `Sunset` headers and a documented period. |
| Contract testing | Consumers and providers verified in CI (TC-INT-01). |

### Endpoint catalog

| Area | Method and path | Purpose | Permission (policy) | Async |
|---|---|---|---|---|
| Identity | `GET /me` | Current user, roles, teams | authenticated | no |
| Identity | `GET /teams`, `POST /teams/{id}/members` | List teams, manage membership | team admin | no |
| Catalog | `GET /catalog/items`, `GET /catalog/items/{id}` | Browse and read items | catalog.read | no |
| Catalog | `POST /catalog/items` | Create item (author) | catalog.author | no |
| Catalog | `POST /catalog/items/{id}/versions` | Add version | catalog.author | no |
| Catalog | `POST /catalog/items/{id}/versions/{v}:publish` | Publish after review | catalog.publish | no |
| Requests | `POST /requests` | Submit a request | request.create | yes |
| Requests | `GET /requests`, `GET /requests/{id}` | List and read | request.read (scoped) | no |
| Requests | `POST /requests/{id}:cancel` | Cancel | requester or admin | no |
| Requests | `GET /requests/{id}/plan` | Plan summary, policy results, cost | request.read | no |
| Approvals | `GET /approvals?assignee=me` | My approvals | authenticated | no |
| Approvals | `POST /approvals/{id}:decide` | Approve or reject | approver, SoD enforced | no |
| Deployments | `GET /deployments`, `GET /deployments/{id}` | Status and history | deployment.read | no |
| Deployments | `POST /deployments/{id}:rollback` | Roll back | deployment.rollback (R2/R3) | yes |
| Inventory | `GET /resources`, `GET /resources/{id}` | Inventory with relationships | inventory.read (scoped) | no |
| Accounts | `GET /accounts` | List accounts | account.read | no |
| Accounts | `POST /accounts:register` | Onboard existing account | account.admin | yes |
| Accounts | `POST /accounts/{id}:decommission` | Start decommission | account.admin (R3) | yes |
| Operations | `GET /operations`, `GET /operations/{id}` | Registry | operation.read | no |
| Operations | `POST /operations/{id}/runs` | Start a run | per operation permission and risk tier | yes |
| Operations | `GET /runs/{id}`, `POST /runs/{id}:cancel` | Track or cancel | run.read, run.cancel | no |
| Policy | `GET /policies`, `POST /policies/{id}/versions` | Read and propose | policy.read, policy.author | no |
| Policy | `POST /policy:evaluate` | Decision API (internal) | service identity | no |
| Policy | `POST /exceptions` | Request exception | exception.request | no |
| Findings | `GET /findings`, `PATCH /findings/{id}` | List and update status | finding.read, finding.triage | no |
| Findings | `POST /findings/{id}:remediate` | Start remediation | by operation tier | yes |
| Access | `POST /access-requests` | Request access (JIT) | authenticated | yes |
| Access | `GET /access-grants`, `POST /access-grants/{id}:revoke` | View and revoke | access.read, access.revoke | no |
| Access | `GET /access-reviews`, `POST /access-reviews/{id}:certify` | Reviews | reviewer | no |
| Databases | `GET /databases`, `GET /databases/{id}/backups` | Inventory and backups | database.read | no |
| Databases | `POST /databases/{id}:restore` | Restore to new instance | database.operate (R2) | yes |
| Data governance | `GET /data-assets`, `PATCH /data-assets/{id}/classification` | Catalog and classify | data.read, data.steward | no |
| Data governance | `POST /data-access-requests` | Request data access | authenticated | yes |
| AI | `POST /assistant/conversations`, `POST /assistant/conversations/{id}/messages` | Chat | assistant.use | no (stream) |
| AI | `GET /agents`, `GET /agent-runs/{id}/trace` | Catalog and trace | agent.read, trace.read | no |
| AI | `POST /agents/{id}:set-autonomy` | Change autonomy | agent.admin (R3) | no |
| AI | `POST /agents:kill-switch` | Pause agents | sre or security | no |
| Cost | `GET /costs`, `POST /budgets` | Cost and budgets | cost.read, budget.manage | no |
| Cost | `GET /recommendations`, `POST /recommendations/{id}:accept` | Optimization | cost.read, operation tier | yes |
| Observability | `GET /incidents`, `POST /incidents`, `GET /slos` | Incidents and SLOs | incident.read, incident.create | no |
| Audit | `GET /audit/events`, `POST /audit/exports`, `GET /audit/verify` | Search, export, verify chain | audit.read (separate role) | exports async |
| Integration | `POST /webhooks/{source}` | Receive external events | signature | no |
| Integration | `GET /integrations`, `POST /integrations/{id}:test` | Health and test | integration.admin | no |

### Event contract

Events use a common envelope (CloudEvents-style): `id`, `source`, `type`, `specversion`, `time`, `tenant_id`, `correlation_id`, `subject`, `schema_version`, `data`. Events are immutable, versioned and documented in a schema registry. Consumers must tolerate additional fields.

| Event type | Emitted when |
|---|---|
| `request.created`, `request.approved`, `request.rejected` | Request lifecycle |
| `plan.ready`, `plan.policy_failed` | Plan results |
| `deployment.started`, `deployment.succeeded`, `deployment.failed`, `deployment.rolled_back` | Execution |
| `resource.created`, `resource.changed`, `resource.deleted` | Inventory changes |
| `finding.opened`, `finding.closed`, `exception.granted` | Security |
| `access.granted`, `access.revoked`, `access.review_due` | Access |
| `operation.run.started`, `operation.run.succeeded`, `operation.run.failed` | Automation |
| `backup.completed`, `backup.validation_failed` | Recovery |
| `incident.opened`, `incident.resolved`, `slo.burn_alert` | Reliability |
| `agent.run.completed`, `agent.guardrail_blocked`, `agent.killswitch_enabled` | AI |
| `policy.version.activated`, `catalog.version.published` | Governance |

### Webhooks and integration contracts

| Aspect | Specification |
|---|---|
| Inbound webhooks | HMAC signature over body and timestamp. Reject old timestamps (replay window). Allow-list sources. Treat as a hint: fetch authoritative state from the source before acting. |
| Outbound webhooks | Signed. Retried with exponential backoff and jitter for a bounded period. Then dead-letter queue and alert. Consumers de-duplicate on event id. |
| Rate limits | Respect source limits. Token bucket per integration. Back off on `429`. |
| Authentication | Secrets from the secrets manager, rotated. Prefer OIDC or short-lived tokens. |
| Failure handling | Circuit breaker per adapter. Degraded mode (for example ticket creation queued when ITSM is down). Health shown in the integrations page. Poison messages to DLQ with replay tool. |

| Integration | Direction | Mechanism | Notes |
|---|---|---|---|
| Identity provider | Both | OIDC or SAML for login, SCIM for users and groups | Deprovisioning must remove access within a defined time |
| ITSM and change | Both | REST API, webhooks | Create and update tickets and changes. Link ids. Sync status |
| CMDB | Platform to CMDB (source of truth decision OD-21) | REST or bulk sync | Reconcile daily |
| CI/CD | Both | Webhook, API | Pipeline triggers deployment requests. Status returned |
| Source control | Both | App or token, webhooks | Pull requests for catalog, policy and templates |
| Monitoring and paging | Both | Webhook, API | Alerts in, incidents out |
| Chat and email | Out, plus approvals | Bot or API | Actionable approvals with signed links |
| Security tools | In | API, finding import | Normalized into findings |
| Cost tools | In | Export ingestion | Daily |
| Documentation | In | Sync | Knowledge ingestion with owners |

## 10.2 Operational Runbooks

Runbooks are maintained as code, linked to alerts, and where safe, executable through the operation registry. Each has an owner, a last-tested date and an exercise cadence.

| ID | Runbook | Trigger | Key steps | Escalation and verification |
|---|---|---|---|---|
| RB-01 | Portal or API outage | Availability alert | 1. Check edge and gateway health. 2. Check core service and database. 3. Roll back last release if correlated. 4. Scale or fail over per dependency. 5. Post status update | Incident commander for more than 15 minutes. Verify with synthetic transactions |
| RB-02 | Platform database failover | Writer failure or high replication lag | 1. Confirm automatic failover happened. 2. Check connection errors and retries. 3. Verify replication and backups. 4. Review for data loss | DBA on-call. Verify writes, workflow health |
| RB-03 | Workflow backlog or stuck workflows | Queue depth or age alerts | 1. Check worker health and recent deploys. 2. Identify blocked workflows by type. 3. Pause the offender operation. 4. Scale or restart workers. 5. Resume with rate limit | Platform on-call, then engineering |
| RB-04 | Suspected execution worker compromise | Egress or runtime anomaly | 1. Trigger global execution pause. 2. Revoke job role sessions. 3. Isolate the node pool. 4. Collect evidence. 5. Rotate affected credentials and rebuild images | Security incident process |
| RB-05 | Credential or secret leak | Scanner or report | 1. Identify secret and scope. 2. Rotate immediately (OP-SEC-005). 3. Review audit for use. 4. Remove from source. 5. Post-incident review | Security on-call |
| RB-06 | AI agent misbehavior | Guardrail alerts, user report | 1. Enable kill switch for the agent or tool. 2. Preserve traces. 3. Review actions and approvals. 4. Fix prompt, tool or policy. 5. Re-evaluate before re-enable | AI platform owner and Security |
| RB-07 | Regional failover (platform) | Regional disruption | Follow OP-DR-002 steps. Freeze changes, verify lag, promote database, scale compute, repoint DNS, verify, communicate | Incident commander plus business authority |
| RB-08 | Audit chain break | Verification alert | 1. Freeze high-risk operations (fail closed). 2. Identify the break range from archive. 3. Determine cause (fault or tampering). 4. Restore from write-once copy. 5. Security investigation | Security and compliance |
| RB-09 | Failed deployment and rollback | Verification failure | 1. Confirm automatic rollback status. 2. Execute rollback operation if not automatic. 3. Validate service health. 4. Open incident if impact | Service owner and SRE |
| RB-10 | Stuck state lock or suspected state corruption | Lock timeout, apply errors | 1. Confirm no running job. 2. Restore state backup or version. 3. Use OP-STATE-001 with two-person approval. 4. Re-plan to confirm | Platform lead |
| RB-11 | Identity provider outage | Login failures | 1. Confirm IdP status. 2. Use break-glass accounts for critical operations only. 3. Alert on every use. 4. Review after recovery | Security and IAM team |
| RB-12 | Cost anomaly | Anomaly alert | 1. Identify service and team. 2. Contact owner. 3. Apply budget action if policy allows. 4. Record cause | FinOps |
| RB-13 | Policy bundle regression | Spike in denials or failed deployments | 1. Compare decisions by policy version. 2. Roll back to previous bundle. 3. Fix and test in shadow mode. 4. Re-release | Security and platform on-call |

## 10.3 Test Strategy

| Layer | Purpose | Approach |
|---|---|---|
| Unit | Logic correctness | Automated, in CI, with coverage targets |
| Contract | API and event compatibility | Provider and consumer contract tests in CI |
| Integration | Component interaction | Ephemeral environments with real dependencies where practical |
| Policy | Policy correctness | Policy unit tests, scenario tests, shadow mode in production before enforcement |
| End to end | Business flows | Automated scenarios in staging, plus synthetic probes in production |
| Security | Resilience against attack | Static and dynamic analysis, dependency scans, annual or pre-release penetration tests, worker escape tests, tenant isolation tests |
| AI | Safety and quality | Evaluation suites per agent, red-team prompts, regression on every prompt, model or tool change |
| Performance and scale | Targets in Part 8 | Load, soak and scale tests with production-like data volumes |
| Resilience | Failure handling | Chaos experiments and dependency failure injection |
| Recovery | RTO and RPO | Backup restore tests, failover and rebuild exercises |
| Accessibility | WCAG conformance | Automated scans plus manual audits |
| Upgrade | Safe releases | Upgrade and rollback rehearsals in staging |

**Release gates:** all automated tests green, no open critical or high security finding without approved exception, policy tests green, performance within thresholds, DR status current, runbooks updated, change approved.

### Test case catalog

| ID | Test case | Covers |
|---|---|---|
| TC-API-01 | Authorization matrix on every endpoint (allowed, denied, cross-tenant) | RBAC, ABAC, tenant isolation |
| TC-API-02 | Idempotency and concurrency (duplicate keys, If-Match conflicts) | API semantics |
| TC-E2E-01 | Catalog request to verified resource | Core lifecycle |
| TC-E2E-02 | Approval rejection and expiry paths | Approval |
| TC-E2E-03 | Failed deployment triggers rollback | Rollback |
| TC-E2E-04 | Existing account onboarding and baseline | Account lifecycle |
| TC-E2E-05 | Kubernetes namespace and workload deployment | Container platform |
| TC-E2E-06 | Database provision, backup, restore, decommission | Database lifecycle |
| TC-E2E-07 | JIT access grant, use and automatic expiry | Access |
| TC-E2E-08 | Decommission with dependency and retention checks | Decommissioning |
| TC-POL-01 | Policy denial blocks deployment with clear reason | Policy gate |
| TC-POL-02 | Policy bundle versioning, shadow mode, rollback | Policy lifecycle |
| TC-SEC-01 | Penetration test | Overall security |
| TC-SEC-02 | Separation of duties enforcement | SoD |
| TC-SEC-03 | Worker isolation and escape attempts | Execution security |
| TC-SEC-04 | Secret rotation without outage | Secrets |
| TC-SEC-05 | Audit completeness and tamper detection | Audit |
| TC-SEC-06 | Tenant isolation (database, search, cache, RAG) | Multi-tenancy |
| TC-IAM-01 | SCIM deprovisioning removes access within target time | Identity |
| TC-SUP-01 | Unsigned or unprovenanced artifact is rejected | Supply chain |
| TC-DATA-01 | Classification accuracy on labeled dataset | Governance |
| TC-DATA-02 | Retention and secure deletion with evidence | Governance |
| TC-DATA-03 | Lineage completeness for sample flows | Governance |
| TC-DATA-04 | Schema migration forward and backward | Data management |
| TC-DR-01 | Backup restore validation | Backup |
| TC-DR-02 | Regional failover exercise | DR |
| TC-DR-03 | Rebuild platform from empty account | Platform recovery |
| TC-AI-01 | Prompt injection red-team suite | AI safety |
| TC-AI-02 | Tool authorization bypass attempts | AI safety |
| TC-AI-03 | Groundedness and hallucination evaluation | AI quality |
| TC-AI-04 | Data leakage and redaction tests | AI safety |
| TC-AI-05 | Budget enforcement and kill switch | AI controls |
| TC-PERF-01 | Load test for concurrent users and API latency | Performance |
| TC-PERF-02 | Inventory and tenant scale test | Scale |
| TC-CHAOS-01 | Dependency and node failure during workflows | Resilience |
| TC-OBS-01 | Alerting, SLO burn and runbook linkage | Observability |
| TC-INT-01 | Integration contract tests | Integrations |
| TC-INT-02 | Retry, rate-limit, DLQ and degraded mode | Integrations |
| TC-FIN-01 | Cost estimate accuracy versus actual | FinOps |
| TC-A11Y-01 | Accessibility audit (WCAG 2.2 AA) | Accessibility |
| TC-UPG-01 | Platform upgrade and rollback rehearsal | Releases |
| TC-OPS-01 | Operation preconditions, timeouts, idempotency, mandatory record fields | Automation |

## 10.4 Implementation Backlog

Sizing: S (days), M (1 to 3 weeks), L (more than 3 weeks). Priority: P0 must-have for phase, P1 important, P2 later.

| ID | Item | Phase | Priority | Size |
|---|---|---|---|---|
| BL-P1-01 | Landing zone and platform accounts | P1 | P0 | L |
| BL-P1-02 | Core service skeleton, API gateway, CI/CD, bootstrap pipeline | P1 | P0 | L |
| BL-P1-03 | OIDC login, MFA integration, SCIM sync | P1 | P0 | M |
| BL-P1-04 | Tenant, team and RBAC model with deny-by-default | P1 | P0 | L |
| BL-P1-05 | Audit ledger with hash chain and write-once archive | P1 | P0 | L |
| BL-P1-06 | Portal shell, role-based navigation, dashboard | P1 | P0 | M |
| BL-P1-07 | Catalog service and item lifecycle | P1 | P0 | M |
| BL-P1-08 | Request and approval workflow (no execution) | P1 | P0 | L |
| BL-P1-09 | Account discovery and inventory sync | P1 | P0 | L |
| BL-P1-10 | ITSM and notification adapters | P1 | P1 | M |
| BL-P1-11 | Platform observability baseline and SLOs | P1 | P1 | M |
| BL-P1-12 | Platform backup and restore procedure | P1 | P1 | M |
| BL-P2-01 | Execution worker platform (ephemeral, isolated) | P2 | P0 | L |
| BL-P2-02 | Workflow engine integration and approval flows | P2 | P0 | L |
| BL-P2-03 | Policy decision service and first policy bundle | P2 | P0 | L |
| BL-P2-04 | Terraform module registry and standards | P2 | P0 | L |
| BL-P2-05 | Plan, scan, cost estimate and review UI | P2 | P0 | L |
| BL-P2-06 | Apply, verify, rollback and state locking | P2 | P0 | L |
| BL-P2-07 | Catalog items: environment baseline, network, namespace | P2 | P0 | L |
| BL-P2-08 | Quota and limit increase workflow | P2 | P2 | M |
| BL-P2-09 | Operation registry with mandatory field enforcement | P2 | P0 | M |
| BL-P2-10 | Change requests, windows and calendar | P2 | P1 | M |
| BL-P2-11 | Decommissioning workflow | P2 | P1 | M |
| BL-P2-12 | CI/CD and CMDB integrations | P2 | P1 | M |
| BL-P3-01 | Policy lifecycle (test, shadow, enforce, exceptions) | P3 | P0 | L |
| BL-P3-02 | Findings model, posture and scanner imports | P3 | P0 | L |
| BL-P3-03 | JIT, PAM brokering and access reviews | P3 | P0 | L |
| BL-P3-04 | Secrets and certificate lifecycle operations | P3 | P0 | M |
| BL-P3-05 | Registry, signing, SBOM and provenance enforcement | P3 | P0 | L |
| BL-P3-06 | Drift detection and remediation workflow | P3 | P1 | M |
| BL-P3-07 | Compliance control library and evidence export | P3 | P1 | L |
| BL-P4-01 | Database catalog items (relational first) | P4 | P0 | L |
| BL-P4-02 | Backup, PITR and restore validation automation | P4 | P0 | L |
| BL-P4-03 | Credential rotation and database user management | P4 | P0 | M |
| BL-P4-04 | Metadata catalog, ownership and classification | P4 | P0 | L |
| BL-P4-05 | Retention, deletion and legal hold engine | P4 | P0 | L |
| BL-P4-06 | Data access approval workflow | P4 | P1 | M |
| BL-P4-07 | Lineage and data quality checks | P4 | P1 | L |
| BL-P4-08 | Cache, search, warehouse and streaming catalog items | P4 | P2 | L |
| BL-P5-01 | Observability integration, alert-as-code, SLO engine | P5 | P0 | L |
| BL-P5-02 | Incident management workflow and post-incident reports | P5 | P0 | L |
| BL-P5-03 | Operation library: patching, renewal, cleanup, rotation | P5 | P0 | L |
| BL-P5-04 | DR orchestration, runbooks and exercise tooling | P5 | P0 | L |
| BL-P5-05 | Kubernetes upgrades and cluster backup | P5 | P1 | L |
| BL-P5-06 | Database performance, forecasting, upgrade and migration | P5 | P1 | L |
| BL-P5-07 | Platform DR: cross-region replication and rebuild test | P5 | P0 | L |
| BL-P6-01 | Model gateway with redaction, budgets and logging | P6 | P0 | L |
| BL-P6-02 | Tool registry and per-call authorization | P6 | P0 | L |
| BL-P6-03 | Knowledge ingestion and permission-aware retrieval | P6 | P0 | L |
| BL-P6-04 | Evaluation harness and red-team suite | P6 | P0 | L |
| BL-P6-05 | Assistant and first agents (knowledge, Kubernetes, Terraform) | P6 | P0 | L |
| BL-P6-06 | Agent tracing, kill switch and cost reporting | P6 | P0 | M |
| BL-P6-07 | AI data retention and deletion | P6 | P1 | M |
| BL-P7-01 | Multi-agent orchestration with supervisor pattern | P7 | P1 | L |
| BL-P7-02 | FinOps intelligence (forecast, anomaly, rightsizing at scale) | P7 | P1 | L |
| BL-P7-03 | Autonomy promotion process and A3 operations | P7 | P1 | L |
| BL-P7-04 | Predictive capacity and reliability analytics | P7 | P2 | L |
| BL-P7-05 | Second cloud provider proof of concept | P7 | P2 | L |

## 10.5 Release Gates and Definition of Done

| Gate | Criteria |
|---|---|
| Definition of done (any item) | Code reviewed, tests added and passing, policy and security checks passed, documentation and runbook updated, observability added, audit events emitted, accessibility checked for UI, feature flag defined if risky |
| Release candidate | All phase acceptance criteria evidence collected. No open critical defects. Performance and security gates met |
| Go-live | Business approval of SLO, RTO and RPO. Support model staffed. Rollback rehearsed. Communication sent |
| Post-release | Hypercare period, defect review, metrics compared to targets |

## 10.6 Risk Register

Likelihood and impact: L (low), M (medium), H (high). Ratings are initial and must be reviewed by the steering group.

| ID | Risk | L | I | Mitigation | Owner |
|---|---|---|---|---|---|
| R-01 | Scope of 16 modules overwhelms delivery | H | H | Strict phasing, MVP definition, modular core, scope control board | Platform Product |
| R-02 | Low adoption by engineering teams | M | H | FDE embedding, paved-road quality, feedback loops, adoption metrics | Platform Product |
| R-03 | Identity provider integration delays | M | M | Early engagement, interim test IdP, parallel work | Security |
| R-04 | Automation causes damage (wrong target, bad change) | M | H | Risk tiers, blast-radius caps, verification, rollback, kill switch, staged autonomy | SRE |
| R-05 | Execution worker compromise or over-privilege | L | H | Isolation, per-job scoped roles, signed images, egress control, tests | Security |
| R-06 | Terraform state corruption or loss | L | H | Versioned encrypted state, locking, backups, restore drill | Platform Engineering |
| R-07 | DR gaps discovered only during an incident | M | H | Early DR design, regular exercises, evidence | SRE |
| R-08 | Scope creep into bespoke automation | H | M | Operation registry gate, backlog discipline | Platform Product |
| R-09 | Low module quality causes insecure or unstable infrastructure | M | H | Module standards, tests, reviews, deprecation process | Platform Engineering |
| R-10 | Policy false positives block delivery | M | M | Shadow mode, exceptions with expiry, policy tests | Security |
| R-11 | Scanner noise and finding fatigue | H | M | Risk scoring, dedupe, ownership routing, SLAs | Security |
| R-12 | Tenant and org model changes after launch | M | H | Decide early (OD-13), keep tenant_id universal, migration plan | Platform Product |
| R-13 | Breadth of database engines exceeds capacity | H | M | Prioritize engines, support tiers, defer low-use categories | DRE |
| R-14 | Poor metadata and lineage quality | H | M | Start with owners and classification, measure coverage, steward process | Data Governance |
| R-15 | Alert fatigue | M | M | Alert quality review, SLO-based alerting, correlation | SRE |
| R-16 | AI hallucination leads to wrong action | M | H | Grounding, validation, approvals, evaluation, autonomy ladder | AI platform owner |
| R-17 | Data leakage through AI prompts or retrieval | M | H | Redaction, classification routing, permission-aware retrieval, DLP | Security |
| R-18 | AI cost overrun | M | M | Budgets, hard stops, model routing, caching | AI platform owner |
| R-19 | Multi-cloud complexity creeps into the MVP | M | M | Provider seams only, decision gate (OD-18) | Architecture |
| R-20 | Model drift or provider change degrades quality | M | M | Evaluation on every change, model pinning, fallback | AI platform owner |
| R-21 | Workflow engine operational complexity | M | H | Managed option, runbooks, capacity testing, fallback decision OD-02 | Platform Engineering |
| R-22 | Skills and key-person dependency | H | M | Training, pairing, documentation, bench of backups | Engineering manager |
| R-23 | Licensing or ecosystem change in a core tool (for example IaC tool) | L | M | Abstraction, evaluate alternatives (OD-05) | Architecture |
| R-24 | Compliance interpretation differences | M | M | Early auditor review, control mapping, evidence samples | Compliance |
| R-25 | Platform cost exceeds value | M | M | Cost tracking per request, tiered services, review each quarter | FinOps |

## 10.7 Open Decisions, Assumptions and Dependencies

### Open decisions

| ID | Decision needed | Options | Needed by | Owner |
|---|---|---|---|---|
| OD-01 | Backend language and framework | Python FastAPI (recommended), Java Spring Boot | Before P1 build | Architecture |
| OD-02 | Workflow engine | Temporal (recommended), AWS Step Functions | Before P2 | Architecture |
| OD-03 | PostgreSQL service type | Aurora PostgreSQL-compatible, RDS Multi-AZ | Before P1 | Architecture, DRE |
| OD-04 | Account vending method | Control Tower with account factory, Terraform-based factory | Before P2 | Platform Engineering |
| OD-05 | IaC tool | Terraform, OpenTofu | Before P2 | Architecture, Legal |
| OD-06 | Kubernetes node scaling | Managed node groups with autoscaler, Karpenter | Before P2 | Platform Engineering |
| OD-07 | Platform cluster topology | One cluster with isolated pools, separate clusters per environment | Before P2 | Platform Engineering |
| OD-08 | Policy engines | OPA only, OPA plus Kyverno, Cedar for application authorization | Before P2 | Security |
| OD-09 | Compliance frameworks in scope | CIS, NIST CSF, ISO 27001, SOC 2, others | Before P3 | Compliance |
| OD-10 | Vector store | pgvector, OpenSearch vector, dedicated | Before P6 | Architecture |
| OD-11 | Model providers and data terms | Managed model service on AWS, others | Before P6 | Security, Legal |
| OD-12 | Incident system of record | Existing ITSM, platform-native | Before P5 | SRE |
| OD-13 | Tenant and organization model | Business unit, team and environment hierarchy | Before P1 | Platform Product |
| OD-14 | Automatic JIT for incident-linked requests | Allow with incident commander confirmation, always require owner | Before P3 | Security |
| OD-15 | Data governance council and steward roles | Define membership and decision rights | Before P4 | Data Governance |
| OD-16 | Business approval of tiers, RTO and RPO | Accept, adjust | Before P5 | Business owners |
| OD-17 | Support model and severity definitions | Hours and tiers | Before R1 | Platform Product |
| OD-18 | Multi-cloud commitment | Defer, proof of concept in P7 | Before P7 | Executive sponsor |
| OD-19 | DR region and residency constraints | Region pair per legal requirements | Before P5 design | Security, Legal |
| OD-20 | Team size, funding and planning assumptions | Confirm | Before planning | Executive sponsor |
| OD-21 | CMDB authority and sync direction | Platform authoritative for cloud resources, or CMDB authoritative | Before P2 | Enterprise architecture |
| OD-22 | Integration depth with ITSM and chat | Minimal, full bidirectional | Before P1 | Platform Product |
| OD-23 | Retention periods and privacy obligations (including requests concerning personal data of platform users) | Per legal | Before P1 data design | Legal, Data Governance |
| OD-24 | SLO targets approval | Accept proposed or adjust | Before R1 | Business owners |
| OD-25 | Which production operations developers can self-serve | Policy matrix | Before P2 | Security, Engineering leadership |

### Assumptions

| ID | Assumption | If false |
|---|---|---|
| AS-01 | An enterprise IdP supports OIDC or SAML and SCIM | Add identity bridge, adds time to P1 |
| AS-02 | An AWS Organization with a landing zone exists or will be created before P1 | Add landing zone workstream |
| AS-03 | A CI/CD system and source control exist | Provide minimal pipelines |
| AS-04 | An ITSM tool with an API exists | Reduce to platform-native approval records |
| AS-05 | Teams have Terraform skills or will be trained | Increase FDE and training effort |
| AS-06 | Approved managed model access on AWS is permitted by policy | Use self-hosted models, increases cost and effort |
| AS-07 | Platform data may be stored in the chosen primary and DR regions | Revisit region choices (OD-19) |
| AS-08 | Existing cloud resources can be discovered and tagged | Add remediation program |
| AS-09 | English-only user interface is acceptable for MVP | Add localization work (not specified in this document) |
| AS-10 | A central log and security account structure is acceptable | Adapt to the organization's structure |

### External dependencies

IdP team, network and landing zone team, security architecture review, legal and privacy review, procurement for managed services and tooling, ITSM team, finance (cost data), audit and compliance, existing monitoring owners.

### Explicitly not specified (not assumed to exist)

Localization, mobile applications, customer-facing (external) portals, on-premises or private cloud provisioning, a general application PaaS, a custom CI system, software license management, and bring-your-own-model training pipelines. If needed, each requires a separate decision and scope.

## 10.8 Ownership Matrix (RACI)

R = responsible, A = accountable, C = consulted, I = informed. PP Platform Product, PE Platform Engineering, SRE, SEC Security, DRE database reliability, DG Data Governance, FO FinOps, FDE forward deployed engineering, SO service owners, CMP compliance and audit.

| Activity | PP | PE | SRE | SEC | DRE | DG | FO | FDE | SO | CMP |
|---|---|---|---|---|---|---|---|---|---|---|
| Platform roadmap and prioritization | A, R | C | C | C | C | C | C | C | C | I |
| Portal and catalog operation | A | R | C | C | I | I | I | C | C | I |
| Catalog item creation | C | R | C | C | C | I | C | R | A | I |
| Terraform modules and templates | I | A, R | C | C | C | I | I | R | I | I |
| Policy-as-code content | C | C | I | A, R | C | C | C | I | I | C |
| Policy exceptions | I | C | I | A | C | C | C | I | R | I |
| Identity, roles and access reviews | I | C | I | A, R | C | C | I | I | R | C |
| Execution worker security | I | R | C | A | I | I | I | I | I | C |
| Kubernetes platform | I | A, R | C | C | I | I | C | C | I | I |
| Database standards and operations | I | C | C | C | A, R | C | C | I | R | I |
| Data classification and retention | I | I | I | C | C | A, R | I | I | R | C |
| Platform reliability and SLOs | I | R | A | C | C | I | I | I | I | I |
| Incident response | I | R | A | C | C | I | I | I | R | I |
| DR planning and exercises | I | R | A | C | R | C | I | I | R | C |
| Operation registry and automations | C | A, R | R | C | R | I | C | C | R | C |
| AI platform and agent approvals | C | A, R | C | A | C | C | C | R | I | C |
| Cost governance and optimization | I | C | C | I | C | I | A, R | I | R | I |
| Supply chain and baselines | I | R | C | A | I | I | I | I | R | C |
| Audit evidence and compliance reporting | I | R | C | R | C | R | I | I | I | A |
| Integrations | C | A, R | C | C | I | I | I | R | I | I |
| Platform release and upgrade | C | A, R | R | C | C | I | I | I | I | I |
| Support and user communication | A | R | R | I | I | I | I | R | I | I |

## 10.9 Final Quality Gate: Completeness Review

This review was performed against the brief's checklist. "Addressed" means a specification exists in this document. It does not mean the capability is built.

| Check | Result | Where addressed | Gaps found and how handled |
|---|---|---|---|
| Missing platform capabilities | Mostly complete | Parts 1, 2 | Added: tenant model (OD-13), notification preferences, deprecation process for catalog items, quota workflow (BL-P2-08). Not specified: localization (AS-09) |
| Missing infrastructure lifecycle operations | Complete | M02, M03, Part 7 | Added decommission safeguards, IPAM, state recovery. Quota management is a backlog item |
| Missing security controls | Complete for scope | Part 4, SC-01 to SC-22 | Added security controls for the platform's own supply chain (SC-22). Vulnerability disclosure program not specified |
| Missing data governance requirements | Complete | M06, Part 5 | Added legal hold, residency enforcement, AI data governance. Privacy rights process depends on OD-23 |
| Missing database management features | Complete for relational. Partial depth for other categories | M05 | Streaming and warehouse operations are lighter. Tracked as R-13 |
| Missing operational automation | Complete | M10, Part 7 | Added owner-must-be-active rule for registry hygiene. Remaining operation cards to be completed in P2 to P5 |
| Missing approval and rollback mechanisms | Complete | Parts 3, 7 | Added emergency change path and post-action review |
| Missing disaster recovery controls | Complete | M14, Part 6 | Clarified: platform DR (Part 6) versus service DR for workloads (M14) |
| Missing AI governance | Complete | M09, Part 4, Part 5 | Added model change evaluation, kill switch, AI data retention, AI runbook RB-06 |
| Missing integrations | Complete | M16, 10.1 | Tenant-specific integrations and depth are open (OD-22) |
| Missing ownership and support models | Mostly complete | 1.5, 10.8 | Severity and SLA definitions pending (OD-17) |
| Missing audit and compliance requirements | Complete | 4.5, M08, M06 | Added auditor read-only role and export API |
| Missing non-functional requirements | Complete | Part 8 | No baselines exist yet. All targets need measurement and approval |
| Missing testing and release management | Complete | 10.3, 10.5 | Added contract tests, upgrade rehearsals and release gates |
| Missing platform self-management and recovery | Complete | 6.10, 6.11 | Added bootstrap path outside the platform and break-glass procedures |

**Unresolved items:** all open decisions in 10.7 and the assumptions list. **No feature is assumed to exist unless listed in this document.**

## 10.10 Traceability Matrix

Columns: requirement, owning module, architecture component (Part 6.4), phase, security control (4.9), test cases (10.3), acceptance criterion (testable statement).

### Functional requirements

| Requirement | Module | Component | Phase | Security control | Test case | Acceptance criterion |
|---|---|---|---|---|---|---|
| REQ-PRT-01 Role-based navigation and dashboard | M01 | C01, C02, C03 | P1 | SC-02 | TC-API-01, TC-E2E-01 | Users see only permitted modules. The API denies the rest. |
| REQ-PRT-02 Catalog browse and guided requests | M01 | C01, C03 | P1 | SC-02, SC-11 | TC-E2E-01 | A valid request is created from schema-driven form. Invalid input is rejected with field errors. |
| REQ-PRT-03 Request tracking and approval center | M01 | C03, C04 | P1 | SC-17, SC-20 | TC-E2E-02, TC-SEC-02 | Approvers decide from one inbox. Self-approval is blocked. |
| REQ-PRT-04 Global search with permission trimming | M01 | C03, C13 | P2 | SC-21 | TC-SEC-06 | Search never returns objects the caller cannot read. |
| REQ-PRT-05 Notifications | M01 | C16 | P1 | SC-11 | TC-INT-02 | Users receive configured notifications. Failures retry and do not block workflows. |
| REQ-PRT-06 AI assistant with scoped answers | M01, M09 | C07, C08 | P6 | SC-14, SC-15 | TC-AI-01, TC-AI-02 | Assistant answers use only caller-permitted data. State changes use normal approvals. |
| REQ-INF-01 Account onboarding and registration | M02 | C03, C10 | P1 | SC-04, SC-10 | TC-E2E-04 | Existing account is discovered, registered with owner and baseline checked. |
| REQ-INF-02 Environment creation from templates | M02 | C03, C04, C05 | P2 | SC-04, SC-09 | TC-E2E-01 | Environment is created, verified and registered in inventory. |
| REQ-INF-03 Region and AZ policy | M02 | C06 | P2 | SC-04 | TC-POL-01 | Deployments to disallowed regions are denied. |
| REQ-INF-04 Decommissioning with safeguards | M02 | C04, C05 | P2 | SC-20 | TC-E2E-08 | Dependency and retention checks run. Recovery window honored. Certificate recorded. |
| REQ-IAC-01 Module registry, versioning, deprecation | M03 | C03 | P2 | SC-22 | TC-E2E-01 | Only registered module versions are usable. Deprecated versions show usage. |
| REQ-IAC-02 Plan, policy, scan and cost before approval | M03 | C05, C06 | P2 | SC-04, SC-13 | TC-POL-01, TC-FIN-01 | Approval screen shows plan diff, policy and scan results and cost delta. |
| REQ-IAC-03 State management and locking | M03 | C05, C13 | P2 | SC-05, SC-09 | TC-E2E-03 | Concurrent applies are blocked. State is encrypted and backed up. |
| REQ-IAC-04 Drift detection and remediation | M03 | C10 | P3 | SC-04 | TC-OPS-01 | Drift is detected on schedule and routed to a workflow. |
| REQ-IAC-05 Rollback and recovery of deployments | M03, M13 | C04, C05 | P2 | SC-20 | TC-E2E-03 | Failed verification triggers rollback per policy with evidence. |
| REQ-K8S-01 Cluster lifecycle | M04 | C04, C05 | P2, P5 | SC-09, SC-20 | TC-E2E-05, TC-UPG-01 | Cluster is created and upgraded one minor version at a time with verification. |
| REQ-K8S-02 Namespace, RBAC, quotas, network policy | M04 | C03, C05 | P2 | SC-10, SC-02 | TC-E2E-05 | Namespace is created with default-deny network policy and quota. |
| REQ-K8S-03 Workload deployment and health insight | M04, M13 | C03, C05 | P2 | SC-12 | TC-E2E-05 | Workload deploys and health, restarts and scheduling reasons appear in the portal. |
| REQ-K8S-04 Image scanning and admission | M04, M15 | C05 | P3 | SC-12, SC-13 | TC-SUP-01 | Unsigned or critical-vulnerable images are blocked per policy. |
| REQ-K8S-05 Cluster backup and restore | M04 | C05 | P5 | SC-18 | TC-DR-01 | Cluster restore test completes within target. |
| REQ-DB-01 Catalog and provisioning for database categories | M05 | C03, C05 | P4 | SC-05, SC-16 | TC-E2E-06 | Each supported engine provisions with encryption, backup and metadata. |
| REQ-DB-02 Credential rotation and user management | M05 | C05, C12 | P4 | SC-07 | TC-SEC-04 | Rotation completes without consumer outage. No shared admin accounts. |
| REQ-DB-03 Backup, PITR and restore validation | M05, M14 | C05 | P4 | SC-18 | TC-DR-01, TC-E2E-06 | Restore to a new instance succeeds and is validated. |
| REQ-DB-04 HA, replication and failover | M05, M14 | C05 | P4 | SC-18 | TC-DR-02 | Failover meets tier targets in exercise. |
| REQ-DB-05 Patching, upgrades and migration | M05 | C04, C05 | P4, P5 | SC-20 | TC-DATA-04 | Changes run with backup, verification and rollback. |
| REQ-DB-06 Performance, query analysis, index and capacity insights | M05 | C10, C15 | P5 | SC-19 | TC-OBS-01 | Recommendations are produced and never applied without a change. |
| REQ-DB-07 Archival and secure decommissioning | M05, M06 | C04, C05 | P4 | SC-16, SC-18 | TC-DATA-02 | Final backup, approval, deletion and certificate are recorded. |
| REQ-GOV-01 Classification, ownership and stewardship | M06 | C03 | P4 | SC-16 | TC-DATA-01 | Assets have owner and classification. Coverage is reported. |
| REQ-GOV-02 Catalog, lineage and discovery | M06 | C03, C10 | P4 | SC-16 | TC-DATA-03 | Sample flows show correct lineage. |
| REQ-GOV-03 Retention, residency, archival, deletion, legal hold | M06 | C04, C05 | P4 | SC-05, SC-16 | TC-DATA-02 | Rules enforced. Legal hold blocks deletion. Evidence recorded. |
| REQ-GOV-04 Sensitive-data detection and masking | M06 | C10 | P4 | SC-16 | TC-DATA-01 | Detection meets agreed precision and recall on labeled data. |
| REQ-GOV-05 Data access approval | M06, M07 | C03, C04 | P4 | SC-02, SC-03 | TC-E2E-07 | Data access is time-bound, approved by owner and logged. |
| REQ-GOV-06 Governance of AI data | M06, M09 | C07, C08, C13 | P6 | SC-16, SC-14 | TC-AI-04, TC-DATA-02 | AI conversation retention and deletion work. Embeddings follow source classification. |
| REQ-GOV-07 Compliance evidence | M06, M08 | C03, C11 | P3 | SC-08 | TC-SEC-05 | Evidence package covers in-scope controls and is exportable. |
| REQ-IAM-01 SSO, MFA, SCIM | M07 | C02, C03 | P1 | SC-01 | TC-IAM-01 | Only SSO logins with MFA. Deprovisioning removes access within the target time. |
| REQ-IAM-02 RBAC, ABAC and SoD | M07 | C06 | P1, P3 | SC-02, SC-17 | TC-API-01, TC-SEC-02 | Deny by default. SoD violations are blocked. |
| REQ-IAM-03 JIT, privileged access, auto-revoke | M07 | C04 | P3 | SC-03 | TC-E2E-07 | Elevated access expires automatically with session audit. |
| REQ-IAM-04 Access reviews | M07 | C03 | P3 | SC-03 | TC-E2E-07 | Review campaigns complete. Unreviewed access is revoked. |
| REQ-IAM-05 Service and workload identity | M07 | C03, C05 | P1, P3 | SC-02, SC-09 | TC-SEC-03 | No long-lived keys in platform paths. |
| REQ-IAM-06 Session auditing | M07 | C11 | P3 | SC-08 | TC-SEC-05 | Privileged sessions are logged with identity and actions. |
| REQ-SEC-01 Policy engine and policy-as-code lifecycle | M08 | C06 | P2, P3 | SC-04 | TC-POL-02 | Policies are versioned, tested, shadowed, enforced and rollbackable. |
| REQ-SEC-02 Posture management and public exposure detection | M08 | C10 | P3 | SC-10, SC-19 | TC-OBS-01 | Public exposure creates a finding and tracks to closure. |
| REQ-SEC-03 Scanning, findings and risk scoring | M08 | C10 | P3 | SC-13 | TC-SEC-01 | Findings are normalized, scored, owned and tracked to SLA. |
| REQ-SEC-04 Secrets and certificate lifecycle | M08 | C04, C12 | P3 | SC-07 | TC-SEC-04 | Rotation and renewal run on schedule without outage. |
| REQ-SEC-05 Remediation workflows | M08, M10 | C04 | P3 | SC-20 | TC-OPS-01 | Fixes follow approval by tier and are verified. |
| REQ-SEC-06 Compliance monitoring and audit evidence | M08 | C11 | P3 | SC-08, SC-19 | TC-SEC-05 | Control status is current and exportable. |
| REQ-AI-01 Agent orchestration and tool registry | M09 | C07 | P6 | SC-15 | TC-AI-02 | Only registered tools are callable. Each call is authorized for user and agent. |
| REQ-AI-02 Model gateway, selection, cost control | M09 | C08 | P6 | SC-14, SC-16 | TC-AI-05 | Budgets are enforced with hard stop. Restricted data routes only to approved endpoints. |
| REQ-AI-03 RAG over approved knowledge | M09 | C07, C13 | P6 | SC-16, SC-21 | TC-SEC-06, TC-AI-03 | Retrieval respects caller permissions and cites sources. |
| REQ-AI-04 Prompt versioning and evaluation | M09 | C07 | P6 | SC-22 | TC-AI-03 | Changes are blocked unless evaluation passes. |
| REQ-AI-05 Guardrails against injection, hallucination and leakage | M09 | C07, C08 | P6 | SC-14 | TC-AI-01, TC-AI-04 | Red-team suite meets threshold. No state change from untrusted content. |
| REQ-AI-06 Human approval for state-changing actions | M09 | C04, C07 | P6 | SC-15, SC-17 | TC-AI-02 | Agent-initiated R2 and R3 operations always wait for a human. |
| REQ-AI-07 Tracing and kill switch | M09 | C07, C11 | P6 | SC-08 | TC-AI-05 | Every run has a trace. Kill switch halts agents within the target time. |
| REQ-OPS-01 Operation registry with mandatory fields | M10 | C03, C04 | P2 | SC-20 | TC-OPS-01 | Operations with incomplete records cannot be enabled. |
| REQ-OPS-02 Triggers, timeouts, retries, idempotency | M10 | C04, C05 | P2, P5 | SC-09 | TC-OPS-01 | Duplicate runs produce no duplicate effect. Timeouts trigger verification. |
| REQ-OPS-03 Verification and compensation | M10 | C04 | P5 | SC-20 | TC-OPS-01, TC-E2E-03 | Runs succeed only after verification. Failures compensate. |
| REQ-OPS-04 Patch, rotation, renewal and cleanup automations | M10 | C04, C05 | P5 | SC-07, SC-13 | TC-OPS-01 | Automations meet SLOs and are auditable. |
| REQ-OBS-01 Metrics, logs, traces, alerts | M11 | C15 | P1, P5 | SC-19 | TC-OBS-01 | All services emit signals. Paging alerts have owners and runbooks. |
| REQ-OBS-02 Incident management and RCA | M11 | C03, C04 | P5 | SC-19 | TC-OBS-01 | Incidents link alerts, changes and timelines. |
| REQ-OBS-03 SLOs and error budgets | M11 | C15 | P5 | SC-19 | TC-OBS-01 | SLO burn alerts fire correctly in test. |
| REQ-OBS-04 Dependency mapping and runbook automation | M11 | C10, C04 | P5 | SC-19 | TC-OPS-01 | Runbook steps use registered operations only. |
| REQ-OBS-05 Post-incident reporting | M11 | C03 | P5 | SC-19 | TC-OBS-01 | Reports are produced and actions tracked to closure. |
| REQ-FIN-01 Cost estimate, budgets, allocation, tagging | M12 | C03, C10 | P2 | SC-04 | TC-FIN-01 | Estimate accuracy is reported. Missing mandatory tags are blocked. |
| REQ-FIN-02 Forecasting, anomalies, optimization recommendations | M12 | C10 | P5, P7 | SC-20 | TC-FIN-01 | Recommendations are explainable. Accepted ones execute through the registry. |
| REQ-FIN-03 Unit economics and cost governance | M12 | C03 | P7 | SC-02 | TC-FIN-01 | Cost per service or request is reported with documented method. |
| REQ-CHG-01 Change requests with risk classification | M13 | C03, C04 | P2 | SC-20 | TC-E2E-02 | Risk tier is computed and approvals follow policy. |
| REQ-CHG-02 Windows, scheduling, conflict detection | M13 | C03 | P2 | SC-20 | TC-E2E-01 | Conflicting or out-of-window changes are blocked or rescheduled. |
| REQ-CHG-03 CI/CD integration, verification, rollback | M13, M16 | C09, C04 | P2 | SC-12, SC-20 | TC-INT-01, TC-E2E-03 | Pipeline status is tracked. Failed verification rolls back. |
| REQ-CHG-04 Release management and change history | M13 | C03, C11 | P2 | SC-08 | TC-SEC-05 | Change history is immutable and traceable to artifacts. |
| REQ-DR-01 Backup policies and validation | M14 | C04, C05 | P4, P5 | SC-18 | TC-DR-01 | Restore validation runs on schedule with reports. |
| REQ-DR-02 RTO and RPO management | M14 | C03 | P5 | SC-18 | TC-DR-02 | Tiers assigned. Measured results compared to targets. |
| REQ-DR-03 Cross-region replication, failover, failback | M14 | C04, C05 | P5 | SC-18 | TC-DR-02 | Failover meets tier objectives in exercise. |
| REQ-DR-04 DR exercises and evidence | M14 | C04, C11 | P5 | SC-08 | TC-DR-02 | Exercise evidence is stored and reviewed. |
| REQ-DR-05 Platform-level DR | M14 | All | P5 | SC-18 | TC-DR-02, TC-DR-03 | Platform fails over and can be rebuilt within targets. |
| REQ-SCM-01 Registries, signing, provenance | M15 | C05 | P3 | SC-12 | TC-SUP-01 | Unsigned artifacts cannot be deployed. |
| REQ-SCM-02 SBOM and dependency scanning | M15 | C05 | P3 | SC-13, SC-22 | TC-SUP-01 | SBOM exists for every deployed artifact and is queryable. |
| REQ-SCM-03 Baselines, drift and patch compliance | M15 | C10 | P3, P5 | SC-13 | TC-OPS-01 | Baseline deviations and patch status are reported by asset. |
| REQ-INT-01 Contracts, events and webhooks | M16 | C09, C14 | P1 | SC-11 | TC-INT-01 | Contract tests pass for each integration. Webhooks verify signatures. |
| REQ-INT-02 Retry, rate limits, DLQ, degraded mode | M16 | C09 | P1 | SC-11 | TC-INT-02 | An integration outage does not stop core flows. Messages are replayable. |
| REQ-INT-03 ITSM and CMDB sync | M16 | C09 | P2 | SC-11 | TC-INT-01 | Records are linked and reconciled daily. |
| REQ-AUD-01 Immutable audit of all state changes | Core | C11 | P1 | SC-08 | TC-SEC-05 | Chain verifies daily. Tampering is detected. |
| REQ-TEN-01 Tenant isolation | Core | C03, C13 | P1 | SC-21 | TC-SEC-06 | No cross-tenant read or write in any store. |
| REQ-SELF-01 Platform self-management, upgrade and recovery | Core | All | P1, P5 | SC-22, SC-18 | TC-UPG-01, TC-DR-03 | Upgrades and rollbacks rehearsed. Rebuild from source succeeds. |

### Non-functional requirements

| Requirement | Module | Component | Phase | Security control | Test case | Acceptance criterion |
|---|---|---|---|---|---|---|
| NFR-AVL-01 to 03 Availability | All | C02 to C06 | P1 onward | SC-19 | TC-CHAOS-01, TC-OBS-01 | SLOs met over agreed window. |
| NFR-SCA-01 to 03 Scalability | All | C03, C04, C05 | P2 onward | SC-11 | TC-PERF-01, TC-PERF-02 | Scale targets met without breaching latency. |
| NFR-LAT-01 to 05 Latency | All | C02, C03, C06 | P1 onward | SC-11 | TC-PERF-01 | Percentile targets met. |
| NFR-REL-01 to 04 Reliability | M10 | C04, C05 | P2 onward | SC-09 | TC-CHAOS-01, TC-OPS-01 | No lost approvals. Workflows survive failures. Operations are idempotent. |
| NFR-SEC-01 to 05 Security | All | All | P1 onward | SC-01 to SC-22 | TC-SEC-01 to TC-SEC-06 | No unresolved critical findings. Controls verified. |
| NFR-DAT-01 to 03 Data consistency | Core | C03, C13 | P1 onward | SC-21 | TC-DATA-04, TC-PERF-02 | Consistency and freshness targets met. |
| NFR-BKP-01 to 02 Backup | M14 | C13 | P1, P4 | SC-18 | TC-DR-01 | Restore tests succeed monthly. |
| NFR-REC-01, NFR-DR-01 to 02 Recovery and DR | M14 | All | P5 | SC-18 | TC-DR-02, TC-DR-03 | Objectives met in exercises. |
| NFR-ACC-01 Accessibility | M01 | C01 | P1 onward | n/a | TC-A11Y-01 | WCAG 2.2 AA target met for core flows. |
| NFR-OBS-01 to 02 Observability | M11 | C15 | P1 onward | SC-19 | TC-OBS-01 | Full signal coverage. Alerts owned. |
| NFR-AUD-01 to 02 Audit completeness | Core | C11 | P1 | SC-08 | TC-SEC-05 | All state changes recorded. Chain verified. |
| NFR-AI-01 to 05 AI safety | M09 | C07, C08 | P6 | SC-14, SC-15, SC-16 | TC-AI-01 to TC-AI-05 | Thresholds met. Zero unauthorized tool execution. |
| NFR-OPS-01 to 03 Operational efficiency | M10, M12 | C04 | P5 onward | SC-20 | TC-OPS-01, TC-FIN-01 | Automation rate and platform cost reported against targets. |

---

> **Closing statement.** FDE Nexus is specified as one governed platform: self-service in front, policy and approvals in the middle, isolated automation underneath, and AI that works only through the same controls. What remains is business approval of the open decisions, baseline measurement of every target, and phased delivery with evidence at each gate.
