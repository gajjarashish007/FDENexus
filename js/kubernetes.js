/* M04 Kubernetes workspace: cluster picker, overview, pods, workloads, nodes, networking,
   config, storage, events, cleanup, plus logs / describe / YAML / diagnose / exec modals. */
(function () {
  "use strict";
  const NX = window.NEXUS, UI = NX.ui, esc = NX.esc, $ = UI.$, $$ = UI.$$;
  const S = { clusters: [], cid: localStorage.getItem("nx-k8s-cluster") || "", tab: "overview", rows: [], meta: {}, timer: null };
  const me = () => NX.session.get() || {};
  const cl = () => S.clusters.find(c => c.id === S.cid);
  const api = (p) => `/api/m04/c/${encodeURIComponent(S.cid)}${p}`;
  const role = () => me().role;
  const canChange = () => { const c = cl(); return ["admin", "operator", "developer"].includes(role()) && !(role() === "developer" && c && c.tier === "production"); };
  const canExec = () => { const c = cl(); return S.meta.exec_enabled && (role() === "admin" || (role() === "operator" && c && c.tier !== "production")); };
  const canRead = () => role() !== "viewer";
  const canPlatform = () => { const c = cl(); return role() === "admin" || (role() === "operator" && c && c.tier !== "production"); };
  const POD_TONE = { running: "success", pending: "warning", error: "danger", completed: "secondary", other: "secondary" };
  const podBadge = (p) => `<span class="nx-badge b-${POD_TONE[p.statusClass] || "secondary"}">${esc(p.status)}</span>`;
  const loading = (msg) => `<div class="nx-empty"><i class="bi bi-hourglass-split"></i>${esc(msg || "Loading from the cluster…")}</div>`;
  const failBox = (e) => `<div class="alert alert-danger small"><i class="bi bi-exclamation-triangle me-1"></i>${esc(e.message)}</div>`;
  const table = (head, rows, empty) => rows.length ? `<div class="nx-card"><div class="nx-table-wrap"><table class="nx-table"><thead><tr>${head.map(h => `<th${h === "" ? ' class="text-end"' : ""}>${esc(h)}</th>`).join("")}</tr></thead>
    <tbody>${rows.join("")}</tbody></table></div></div>` : `<div class="nx-card"><div class="nx-empty"><i class="bi bi-inbox"></i>${esc(empty || "Nothing here.")}</div></div>`;
  const filt = (rows) => { const q = $("#k-search").value.trim().toLowerCase(), ns = $("#k-ns").value;
    return rows.filter(r => (!q || (r.name + " " + (r.namespace || "")).toLowerCase().includes(q)) && (!ns || !r.namespace || r.namespace === ns)); };

  /* ---------------- cluster picker ---------------- */
  async function loadClusters() {
    try { const r = await NX.api.get("/api/m04/clusters"); S.clusters = r.clusters; S.meta = r; }
    catch (e) { $("#k-empty").innerHTML = failBox(e); $("#k-empty").classList.remove("d-none"); return; }
    const sel = $("#k-cluster");
    if (!S.clusters.length) {
      sel.innerHTML = "<option>No clusters</option>"; sel.disabled = true; $("#k-test").disabled = $("#k-refresh").disabled = true;
      $("#k-main").classList.add("d-none"); $("#k-empty").classList.remove("d-none");
      $("#k-empty").innerHTML = `<div class="nx-card"><div class="nx-card-body">
        <h2 class="h6 fw-bold">No clusters yet</h2>
        <ul class="small mb-0"><li><b>Create one:</b> launch an <a href="launch.html?type=eks-cluster">EKS cluster</a> into an environment. It appears here automatically.</li>
          <li><b>Add an existing EKS cluster</b> from a connected AWS account, or a <b>kubeconfig context</b> from the portal host (admins: “Add cluster”).</li></ul></div></div>`;
      return;
    }
    if (!cl()) S.cid = S.clusters[0].id;
    sel.disabled = false; $("#k-test").disabled = $("#k-refresh").disabled = false;
    sel.innerHTML = S.clusters.map(c => `<option value="${esc(c.id)}" ${c.id === S.cid ? "selected" : ""}>${esc(c.label || c.name)} · ${esc(c.tier)}${c.source === "eks" ? ` · ${esc(c.region)}` : " · kubeconfig"}</option>`).join("");
    $("#k-empty").classList.add("d-none"); $("#k-main").classList.remove("d-none");
    drawMeta();
  }
  function drawMeta() {
    const c = cl(); if (!c) return;
    const st = c.last_status === "connected" ? '<span class="nx-badge b-success">connected</span>' : c.last_status === "failed" ? '<span class="nx-badge b-danger">connection failed</span>' : '<span class="nx-badge b-secondary">not tested</span>';
    $("#k-meta").innerHTML = `${st} <span class="nx-badge b-${c.tier === "production" ? "danger" : "secondary"}">${esc(c.tier)}</span>
      <span class="nx-badge b-secondary">${c.source === "eks" ? "EKS · " + esc(c.account_id) : "kubeconfig · " + esc(c.context)}</span>
      ${c.server_version ? `<span class="nx-badge b-secondary">${esc(c.server_version)}</span>` : ""}
      ${c.origin === "M02" ? `<a class="nx-badge b-primary text-decoration-none" href="environments.html?env=${encodeURIComponent(c.environment)}">from ${esc(c.environment)}</a>` : ""}
      ${c.source === "eks" && S.meta.simulated ? '<span class="nx-badge b-warning">simulation: not contacted</span>' : ""}
      ${c.last_note && c.last_status === "failed" ? `<span class="small text-danger">${esc(c.last_note.slice(0, 160))}</span>` : ""}`;
  }

  /* ---------------- tabs ---------------- */
  const TABS = {
    overview: { tools: [], fn: drawOverview },
    cluster: { tools: [], fn: drawCluster },
    namespaces: { tools: ["search", "system"], fn: drawNamespaces },
    access: { tools: ["search", "ns", "system"], fn: drawAccess },
    pods: { tools: ["search", "ns", "status", "system"], fn: drawPods },
    workloads: { tools: ["search", "ns", "kind", "system"], fn: drawWorkloads },
    nodes: { tools: ["search"], fn: drawNodes },
    network: { tools: ["search", "ns", "system"], fn: drawNetwork },
    config: { tools: ["search", "ns", "system"], fn: drawConfig },
    storage: { tools: ["search", "ns"], fn: drawStorage },
    events: { tools: ["search", "ns", "system"], fn: drawEvents },
    cleanup: { tools: ["system"], fn: drawCleanup },
  };
  function setTab(t) {
    S.tab = t;
    $$("#k-tabs [data-tab]").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
    const tools = TABS[t].tools;
    $("#k-toolbar").classList.toggle("d-none", !tools.length);
    $("#k-search").parentElement.classList.toggle("d-none", !tools.includes("search"));
    $("#k-ns").classList.toggle("d-none", !tools.includes("ns"));
    $("#k-status").classList.toggle("d-none", !tools.includes("status"));
    $("#k-kind").classList.toggle("d-none", !tools.includes("kind"));
    $("#k-system").closest(".form-check").classList.toggle("d-none", !tools.includes("system"));
    drawCreate(t);
    if (!tools.length && CREATE[t]) $("#k-toolbar").classList.remove("d-none");
    refresh();
  }
  async function refresh(fresh) {
    if (!cl()) return;
    try { await TABS[S.tab].fn(!!fresh); } catch (e) { $("#k-pane").innerHTML = failBox(e); }
  }
  const sys = () => $("#k-system").checked ? "&system=1" : "";
  async function list(kind, fresh) {
    const r = await NX.api.get(api(`/list/${kind}?x=1${sys()}${fresh ? "&refresh=1" : ""}`));
    return r.items;
  }
  function fillNamespaces(rows) {
    const sel = $("#k-ns"), cur = sel.value, set = [...new Set(rows.map(r => r.namespace).filter(Boolean))].sort();
    sel.innerHTML = `<option value="">All namespaces</option>` + set.map(n => `<option ${n === cur ? "selected" : ""}>${esc(n)}</option>`).join("");
  }

  /* ---------------- overview ---------------- */
  async function drawOverview(fresh) {
    $("#k-pane").innerHTML = loading();
    const o = (await NX.api.get(api("/overview" + (fresh ? "?refresh=1" : "")))).overview;
    const k = (label, v, icon, tone, sub) => `<div class="col-6 col-xl-2"><div class="nx-card h-100"><div class="nx-card-body nx-kpi"><div class="nx-kpi-icon tone-${tone}"><i class="bi ${icon}"></i></div>
      <div><div class="nx-kpi-value" style="font-size:20px">${esc(v)}</div><div class="nx-kpi-label">${esc(label)}</div>${sub ? `<div class="small nx-muted">${esc(sub)}</div>` : ""}</div></div></div></div>`;
    $("#k-pod-err").textContent = o.pods.error || "";
    const skew = o.nodes.versions.length > 1 ? `<div class="alert alert-warning py-2 small"><i class="bi bi-exclamation-triangle me-1"></i>Node versions differ: ${o.nodes.versions.map(esc).join(", ")} (control plane ${esc(o.version)}). Finish the node group upgrade.</div>` : "";
    $("#k-pane").innerHTML = `<div class="row g-3 mb-3">
        ${k("Nodes ready", `${o.nodes.ready}/${o.nodes.total}`, "bi-hdd-rack", o.nodes.ready === o.nodes.total ? "success" : "danger", o.nodes.notReady.length ? o.nodes.notReady.length + " not ready" : "")}
        ${k("Pods running", `${o.pods.running}/${o.pods.total}`, "bi-box", "primary", `${o.namespaces} namespaces`)}
        ${k("Pod errors", o.pods.error, "bi-x-octagon", o.pods.error ? "danger" : "success", `${o.pods.pending} pending`)}
        ${k("Restarts", o.pods.restarts, "bi-arrow-repeat", o.pods.restarts > 20 ? "warning" : "secondary", "application pods")}
        ${k("Degraded deployments", `${o.deployments.degraded.length}/${o.deployments.total}`, "bi-layers", o.deployments.degraded.length ? "warning" : "success")}
        ${k("Warning events", o.warningCount, "bi-exclamation-triangle", o.warningCount ? "warning" : "success", esc(o.version))}
      </div>${skew}
      <div class="row g-3">
        <div class="col-xl-7"><h2 class="h6 fw-bold">Problem pods</h2>${table(["Pod", "Namespace", "Status", "Restarts", ""],
          o.problemPods.map(p => `<tr><td class="nx-mono small">${esc(p.name)}</td><td>${esc(p.namespace)}</td><td>${podBadge(p)}${p.lastTermination ? ` <span class="small nx-muted">last: ${esc(p.lastTermination)}</span>` : ""}</td>
            <td>${p.restarts}</td><td class="text-end"><button class="btn btn-sm btn-primary" data-diag="${esc(p.namespace)}/${esc(p.name)}"><i class="bi bi-stethoscope me-1"></i>Diagnose</button></td></tr>`), "No failing or restarting pods.")}
          <h2 class="h6 fw-bold mt-3">Degraded deployments</h2>${table(["Deployment", "Namespace", "Ready", ""],
          o.deployments.degraded.map(d => `<tr><td class="nx-mono small">${esc(d.name)}</td><td>${esc(d.namespace)}</td><td><span class="nx-badge b-warning">${esc(d.ready)}</span></td>
            <td class="text-end">${canChange() ? `<button class="btn btn-sm btn-outline-primary" data-restart="${esc(d.namespace)}/${esc(d.name)}/deployment">Restart</button>` : ""}</td></tr>`), "All deployments have their desired replicas ready.")}</div>
        <div class="col-xl-5"><h2 class="h6 fw-bold">Recent warnings</h2>${o.warnings.length ? `<div class="nx-card"><div class="nx-card-body">${o.warnings.map(e => `<div class="nx-finding">
          <div class="d-flex justify-content-between"><span class="fw-semibold small">${esc(e.reason)} · <span class="nx-mono">${esc(e.object)}</span></span><span class="small nx-muted">${esc(e.last)} · x${e.count}</span></div>
          <div class="small">${esc(e.message)}</div><div class="small nx-muted">${esc(e.namespace)}</div></div>`).join("")}</div></div>` : table([], [], "No warning events.")}</div>
      </div>`;
    wireActions();
  }

  /* ---------------- pods ---------------- */
  async function drawPods(fresh) {
    $("#k-pane").innerHTML = loading();
    const st = $("#k-status").value;
    S.rows = await list("pods", fresh); fillNamespaces(S.rows);
    const rows = filt(S.rows).filter(p => !st || p.statusClass === st);
    $("#k-pane").innerHTML = `<div class="small nx-muted mb-2">${rows.length} of ${S.rows.length} pods</div>` + table(["Pod", "Namespace", "Ready", "Status", "Restarts", "Node", "Age", ""],
      rows.map(p => `<tr><td class="nx-mono small">${esc(p.name)}<div class="nx-muted">${esc(p.owner)}</div></td><td>${esc(p.namespace)}</td><td>${esc(p.ready)}</td>
        <td>${podBadge(p)}${p.lastTermination ? `<div class="small nx-muted">last: ${esc(p.lastTermination)}</div>` : ""}</td><td>${p.restarts}</td>
        <td class="small nx-mono">${esc(p.node)}</td><td class="small">${esc(p.age)}</td>
        <td class="text-end" style="white-space:nowrap">
          <button class="btn btn-sm btn-outline-primary" data-diag="${esc(p.namespace)}/${esc(p.name)}" title="Diagnose"><i class="bi bi-stethoscope"></i></button>
          ${canRead() ? `<button class="btn btn-sm btn-outline-secondary" data-logs="${esc(p.namespace)}/${esc(p.name)}" data-containers="${esc(p.containers.join(","))}" title="Logs"><i class="bi bi-journal-text"></i></button>` : ""}
          <button class="btn btn-sm btn-outline-secondary" data-describe="pod/${esc(p.namespace)}/${esc(p.name)}" title="Describe"><i class="bi bi-info-circle"></i></button>
          ${canExec() ? `<button class="btn btn-sm btn-outline-dark" data-exec="${esc(p.namespace)}/${esc(p.name)}" data-containers="${esc(p.containers.join(","))}" title="Run command"><i class="bi bi-terminal"></i></button>` : ""}
          ${canChange() ? `<button class="btn btn-sm btn-outline-danger" data-delpod="${esc(p.namespace)}/${esc(p.name)}" title="Delete pod"><i class="bi bi-trash"></i></button>` : ""}
        </td></tr>`), "No pods match.");
    wireActions();
  }

  /* ---------------- workloads ---------------- */
  async function drawWorkloads(fresh) {
    $("#k-pane").innerHTML = loading();
    const kind = $("#k-kind").value;
    S.rows = await list(kind, fresh); fillNamespaces(S.rows);
    const rows = filt(S.rows), single = { deployments: "deployment", statefulsets: "statefulset", daemonsets: "daemonset", cronjobs: "cronjob" }[kind];
    if (kind === "cronjobs") {
      $("#k-pane").innerHTML = table(["CronJob", "Namespace", "Schedule", "Suspended", "Last run", "Active", ""], rows.map(r => `<tr><td class="nx-mono small">${esc(r.name)}</td><td>${esc(r.namespace)}</td>
        <td class="nx-mono small">${esc(r.schedule)}</td><td>${r.suspend ? "yes" : "no"}</td><td>${esc(r.lastSchedule || "never")}</td><td>${r.active}</td>
        <td class="text-end"><button class="btn btn-sm btn-outline-secondary" data-describe="cronjob/${esc(r.namespace)}/${esc(r.name)}"><i class="bi bi-info-circle"></i></button></td></tr>`), "No CronJobs.");
      return wireActions();
    }
    $("#k-pane").innerHTML = table(["Name", "Namespace", "Ready", "Up to date", "Images", "Age", ""], rows.map(r => `<tr><td class="nx-mono small">${esc(r.name)}</td><td>${esc(r.namespace)}</td>
      <td><span class="nx-badge b-${r.healthy ? "success" : "warning"}">${esc(r.ready)}</span></td><td>${r.upToDate}</td><td class="small nx-mono">${r.images.map(esc).join("<br>")}</td><td class="small">${esc(r.age)}</td>
      <td class="text-end" style="white-space:nowrap">
        ${canChange() ? `<button class="btn btn-sm btn-outline-primary" data-restart="${esc(r.namespace)}/${esc(r.name)}/${single}" title="Rollout restart"><i class="bi bi-arrow-repeat"></i></button>
          ${single !== "daemonset" ? `<button class="btn btn-sm btn-outline-primary" data-scale="${esc(r.namespace)}/${esc(r.name)}/${single}/${r.replicas}" title="Scale"><i class="bi bi-arrows-angle-expand"></i></button>` : ""}` : ""}
        <button class="btn btn-sm btn-outline-secondary" data-describe="${single}/${esc(r.namespace)}/${esc(r.name)}" title="Describe"><i class="bi bi-info-circle"></i></button>
        ${canRead() ? `<button class="btn btn-sm btn-outline-secondary" data-yaml="${single}/${esc(r.namespace)}/${esc(r.name)}" title="YAML"><i class="bi bi-filetype-yml"></i></button>` : ""}
        ${canChange() ? `<button class="btn btn-sm btn-outline-secondary" data-setimg="${single}/${esc(r.namespace)}/${esc(r.name)}" data-images="${esc(r.images.join(","))}" title="Change image"><i class="bi bi-box-arrow-up"></i></button>
          <button class="btn btn-sm btn-outline-secondary" data-history="${single}/${esc(r.namespace)}/${esc(r.name)}" title="History / roll back"><i class="bi bi-clock-history"></i></button>
          <button class="btn btn-sm btn-outline-danger" data-delobj="${single}/${esc(r.namespace)}/${esc(r.name)}" title="Delete"><i class="bi bi-trash"></i></button>` : ""}
      </td></tr>`), "No workloads of this kind.");
    wireActions();
  }

  /* ---------------- nodes ---------------- */
  async function drawNodes(fresh) {
    $("#k-pane").innerHTML = loading();
    S.rows = await list("nodes", fresh);
    const rows = filt(S.rows);
    $("#k-pane").innerHTML = table(["Node", "Status", "Type / capacity", "Zone", "Node group", "Version", "Allocatable", "Taints", ""], rows.map(n => `<tr>
      <td class="nx-mono small">${esc(n.name)}<div class="nx-muted">${esc(n.internalIp)}</div></td>
      <td><span class="nx-badge b-${n.status === "Ready" ? "success" : "danger"}">${esc(n.status)}</span>${n.pressure.map(p => ` <span class="nx-badge b-warning">${esc(p)}</span>`).join("")}</td>
      <td class="small">${esc(n.instanceType)}<div class="nx-muted">${esc(n.capacityType)}</div></td><td class="small">${esc(n.zone)}</td><td class="small">${esc(n.nodegroup)}</td>
      <td class="small">${esc(n.version)}<div class="nx-muted">${esc(n.os)}</div></td><td class="small">${esc(n.cpu)} CPU · ${esc(n.memory)} · ${esc(n.pods)} pods</td>
      <td class="small nx-mono">${n.taints.map(esc).join("<br>")}</td>
      <td class="text-end" style="white-space:nowrap"><button class="btn btn-sm btn-outline-secondary" data-describe="node//${esc(n.name)}"><i class="bi bi-info-circle"></i></button>
        ${canPlatform() ? (n.status === "SchedulingDisabled"
          ? `<button class="btn btn-sm btn-outline-success" data-node="${esc(n.name)}/uncordon" title="Allow scheduling">Uncordon</button>`
          : `<button class="btn btn-sm btn-outline-warning" data-node="${esc(n.name)}/cordon" title="Stop new pods">Cordon</button>
             <button class="btn btn-sm btn-outline-danger" data-node="${esc(n.name)}/drain" title="Evict pods (respects PodDisruptionBudgets)">Drain</button>`) : ""}</td></tr>`), "No nodes.") +
      `<div class="small nx-muted mt-2">Node group size, instance types and versions are on the <b>Cluster</b> tab.</div>`;
    wireActions();
  }

  /* ---------------- networking / config / storage ---------------- */
  async function drawNetwork(fresh) {
    $("#k-pane").innerHTML = loading();
    const [svcs, ing] = await Promise.all([list("services", fresh), list("ingresses", fresh)]);
    fillNamespaces(svcs.concat(ing));
    $("#k-pane").innerHTML = `<h2 class="h6 fw-bold">Services</h2>` + table(["Service", "Namespace", "Type", "Cluster IP", "External", "Ports", ""], filt(svcs).map(s => `<tr>
      <td class="nx-mono small">${esc(s.name)}</td><td>${esc(s.namespace)}</td><td><span class="nx-badge b-${s.type === "LoadBalancer" ? "primary" : "secondary"}">${esc(s.type)}</span></td>
      <td class="nx-mono small">${esc(s.clusterIp)}</td><td class="nx-mono small">${esc(s.external)}</td><td class="small">${esc(s.ports)}</td>
      <td class="text-end"><button class="btn btn-sm btn-outline-secondary" data-describe="service/${esc(s.namespace)}/${esc(s.name)}"><i class="bi bi-info-circle"></i></button></td></tr>`), "No services.") +
      `<h2 class="h6 fw-bold mt-3">Ingresses</h2>` + table(["Ingress", "Namespace", "Class", "Hosts", "Address", "TLS", ""], filt(ing).map(i => `<tr>
      <td class="nx-mono small">${esc(i.name)}</td><td>${esc(i.namespace)}</td><td>${esc(i.className)}</td><td class="small">${esc(i.hosts)}</td><td class="nx-mono small">${esc(i.address)}</td>
      <td>${i.tls ? '<span class="nx-badge b-success">TLS</span>' : '<span class="nx-badge b-warning">none</span>'}</td>
      <td class="text-end"><button class="btn btn-sm btn-outline-secondary" data-describe="ingress/${esc(i.namespace)}/${esc(i.name)}"><i class="bi bi-info-circle"></i></button>
        ${canChange() ? `<button class="btn btn-sm btn-outline-danger" data-delobj="ingress/${esc(i.namespace)}/${esc(i.name)}"><i class="bi bi-trash"></i></button>` : ""}</td></tr>`), "No ingresses.");
    const np = await list("networkpolicies", fresh);
    $("#k-pane").innerHTML += `<h2 class="h6 fw-bold mt-3">Network policies</h2>` + table(["Policy", "Namespace", "Applies to", "Types", "Rules (in/out)", ""], filt(np).map(p => `<tr>
      <td class="nx-mono small">${esc(p.name)}</td><td>${esc(p.namespace)}</td><td class="small">${esc(p.selector)}</td><td>${esc(p.types)}</td><td>${p.ingressRules}/${p.egressRules}</td>
      <td class="text-end"><button class="btn btn-sm btn-outline-secondary" data-describe="networkpolicy/${esc(p.namespace)}/${esc(p.name)}"><i class="bi bi-info-circle"></i></button>
        ${canPlatform() ? `<button class="btn btn-sm btn-outline-danger" data-delobj="networkpolicy/${esc(p.namespace)}/${esc(p.name)}"><i class="bi bi-trash"></i></button>` : ""}</td></tr>`),
      "No network policies: all pods accept traffic from anywhere in the cluster.") +
      `<div class="small nx-muted mt-2">Network policies are enforced only if the cluster runs a policy engine (VPC CNI network policy, Calico or Cilium).</div>`;
    wireActions();
  }
  async function drawConfig(fresh) {
    $("#k-pane").innerHTML = loading();
    const [hpa, cms, rq] = await Promise.all([list("hpa", fresh), list("configmaps", fresh), list("resourcequotas", fresh)]);
    fillNamespaces(hpa.concat(cms));
    $("#k-pane").innerHTML = `<h2 class="h6 fw-bold">Horizontal pod autoscalers</h2>` + table(["HPA", "Namespace", "Target", "Replicas (min/cur/max)", "Metrics", ""], filt(hpa).map(h => `<tr>
      <td class="nx-mono small">${esc(h.name)}</td><td>${esc(h.namespace)}</td><td class="small">${esc(h.reference)}</td>
      <td>${h.min} / <b>${h.current ?? "?"}</b>${h.desired !== h.current && h.desired != null ? ` → ${h.desired}` : ""} / ${h.max}${h.current >= h.max ? ' <span class="nx-badge b-warning">at max</span>' : ""}</td>
      <td class="small">${esc(h.targets)}</td><td class="text-end" style="white-space:nowrap"><button class="btn btn-sm btn-outline-secondary" data-describe="hpa/${esc(h.namespace)}/${esc(h.name)}"><i class="bi bi-info-circle"></i></button>
        ${canChange() ? `<button class="btn btn-sm btn-outline-primary" data-hpa="${esc(h.namespace)}/${esc(h.name)}/${h.min}/${h.max}" title="Change min/max"><i class="bi bi-sliders"></i></button>
          <button class="btn btn-sm btn-outline-danger" data-delobj="hpa/${esc(h.namespace)}/${esc(h.name)}"><i class="bi bi-trash"></i></button>` : ""}</td></tr>`), "No autoscalers.") +
      `<h2 class="h6 fw-bold mt-3">Resource quotas</h2>` + table(["Quota", "Namespace", "Used / hard", ""], filt(rq).map(r => `<tr><td class="nx-mono small">${esc(r.name)}</td><td>${esc(r.namespace)}</td><td class="small">${esc(r.usage)}</td>
        <td class="text-end">${canPlatform() ? `<button class="btn btn-sm btn-outline-danger" data-delobj="resourcequota/${esc(r.namespace)}/${esc(r.name)}"><i class="bi bi-trash"></i></button>` : ""}</td></tr>`), "No quotas set.") +
      `<h2 class="h6 fw-bold mt-3">ConfigMaps</h2>` + table(["ConfigMap", "Namespace", "Keys", "Age", ""], filt(cms).map(m => `<tr><td class="nx-mono small">${esc(m.name)}</td><td>${esc(m.namespace)}</td><td>${m.keys}</td><td class="small">${esc(m.age)}</td>
      <td class="text-end">${canRead() ? `<button class="btn btn-sm btn-outline-secondary" data-describe="configmap/${esc(m.namespace)}/${esc(m.name)}"><i class="bi bi-info-circle"></i></button>` : ""}</td></tr>`), "No ConfigMaps.") +
      `<div class="small nx-muted mt-2">Secrets are never listed or shown here.</div>`;
    wireActions();
  }
  async function drawStorage(fresh) {
    $("#k-pane").innerHTML = loading();
    S.rows = await list("pvc", fresh); fillNamespaces(S.rows);
    $("#k-pane").innerHTML = table(["Claim", "Namespace", "Status", "Capacity", "Storage class", "Access", "Volume", ""], filt(S.rows).map(p => `<tr>
      <td class="nx-mono small">${esc(p.name)}</td><td>${esc(p.namespace)}</td><td><span class="nx-badge b-${p.status === "Bound" ? "success" : "warning"}">${esc(p.status)}</span></td>
      <td>${esc(p.capacity)}</td><td>${esc(p.storageClass)}</td><td class="small">${esc(p.access)}</td><td class="nx-mono small">${esc(p.volume)}</td>
      <td class="text-end"><button class="btn btn-sm btn-outline-secondary" data-describe="pvc/${esc(p.namespace)}/${esc(p.name)}"><i class="bi bi-info-circle"></i></button>
        ${canChange() ? `<button class="btn btn-sm btn-outline-danger" data-delobj="pvc/${esc(p.namespace)}/${esc(p.name)}" title="Delete claim (data may be deleted with it)"><i class="bi bi-trash"></i></button>` : ""}</td></tr>`), "No persistent volume claims.");
    const [sc, pv] = await Promise.all([list("storageclasses", fresh), list("pv", fresh)]);
    S.storageClasses = sc;
    $("#k-pane").innerHTML += `<h2 class="h6 fw-bold mt-3">Storage classes</h2>` + table(["Class", "Provisioner", "Type", "Reclaim", "Binding", "Expansion"], sc.map(c2 => `<tr>
      <td class="nx-mono small">${esc(c2.name)}${c2.default ? ' <span class="nx-badge b-primary">default</span>' : ""}</td><td class="small">${esc(c2.provisioner)}</td><td>${esc(c2.type)}</td>
      <td>${esc(c2.reclaim)}</td><td class="small">${esc(c2.binding)}</td><td>${c2.expansion ? "yes" : "no"}</td></tr>`), "No storage classes.") +
      `<h2 class="h6 fw-bold mt-3">Persistent volumes</h2>` + table(["Volume", "Status", "Capacity", "Class", "Reclaim", "Claim"], filt(pv).map(v => `<tr>
      <td class="nx-mono small">${esc(v.name)}</td><td><span class="nx-badge b-${v.status === "Bound" ? "success" : "warning"}">${esc(v.status)}</span></td><td>${esc(v.capacity)}</td>
      <td>${esc(v.storageClass)}</td><td>${esc(v.reclaim)}</td><td class="nx-mono small">${esc(v.claim)}</td></tr>`), "No persistent volumes.");
    wireActions();
  }

  /* ---------------- events ---------------- */
  async function drawEvents() {
    $("#k-pane").innerHTML = loading();
    const warn = !S.allEvents;
    const r = await NX.api.get(api(`/events?x=1${warn ? "&warnings=1" : ""}${sys()}`));
    fillNamespaces(r.items);
    $("#k-pane").innerHTML = `<div class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" id="k-allev" ${S.allEvents ? "checked" : ""}><label class="form-check-label small" for="k-allev">Include Normal events</label></div>` +
      table(["Last", "Type", "Reason", "Object", "Namespace", "Count", "Message"], filt(r.items.map(e => ({ ...e, name: e.object }))).map(e => `<tr>
        <td class="small">${esc(e.last)}</td><td><span class="nx-badge b-${e.type === "Warning" ? "warning" : "secondary"}">${esc(e.type)}</span></td><td class="small fw-semibold">${esc(e.reason)}</td>
        <td class="nx-mono small">${esc(e.object)}</td><td>${esc(e.namespace)}</td><td>${e.count}</td><td class="small">${esc(e.message)}</td></tr>`), "No events.");
    $("#k-allev").onchange = (ev) => { S.allEvents = ev.target.checked; drawEvents(); };
  }

  /* ---------------- cleanup ---------------- */
  async function drawCleanup() {
    const allowed = ["admin", "operator"].includes(role());
    $("#k-pane").innerHTML = `<div class="nx-card"><div class="nx-card-body">
      <h2 class="h6 fw-bold">Clean up failed pods</h2>
      <p class="small nx-muted">Finds pods in Error, ErrImagePull, Evicted, CrashLoopBackOff, ImagePullBackOff, Failed or Unknown state. A dry run lists them; deleting lets their controllers create fresh pods. Every deletion is audited.</p>
      ${allowed ? '<button class="btn btn-outline-primary" id="k-dry"><i class="bi bi-search me-1"></i>Dry run</button>' : '<div class="small nx-muted">Only admins and operators can run cleanup.</div>'}
      <div id="k-clean-out" class="mt-3"></div></div></div>`;
    if (!allowed) return;
    $("#k-dry").onclick = async () => {
      $("#k-clean-out").innerHTML = loading("Scanning pods…");
      try {
        const r = await NX.api.post(api("/cleanup"), { dry_run: true, include_system: $("#k-system").checked });
        $("#k-clean-out").innerHTML = r.pods.length ? table(["Pod", "Namespace", "Status", "Owner"], r.pods.map(p => `<tr><td class="nx-mono small">${esc(p.name)}</td><td>${esc(p.namespace)}</td><td>${podBadge(p)}</td><td class="small">${esc(p.owner)}</td></tr>`)) +
          `<button class="btn btn-danger mt-3" id="k-clean-go"><i class="bi bi-trash me-1"></i>Delete these ${r.pods.length} pods</button>` : '<div class="alert alert-success py-2 small">No failed pods found.</div>';
        const go = $("#k-clean-go");
        if (go) go.onclick = async () => {
          if (!confirm(`Delete ${r.pods.length} pods on ${cl().name}?`)) return;
          go.disabled = true;
          try { const x = await NX.api.post(api("/cleanup"), { dry_run: false, include_system: $("#k-system").checked });
            NX.toast(`Deleted ${x.deleted.length} pods${x.failed.length ? `, ${x.failed.length} failed` : ""}.`, x.failed.length ? "warning" : "success"); $("#k-dry").click(); }
          catch (e) { NX.toast(UI.errorText(e), "danger"); go.disabled = false; }
        };
      } catch (e) { $("#k-clean-out").innerHTML = failBox(e); }
    };
  }

  /* ---------------- row actions ---------------- */
  function wireActions() {
    $$("[data-diag]").forEach(b => b.onclick = () => { const [ns, p] = b.dataset.diag.split("/"); openDiagnose(ns, p); });
    $$("[data-logs]").forEach(b => b.onclick = () => { const [ns, p] = b.dataset.logs.split("/"); openLogs(ns, p, b.dataset.containers.split(",").filter(Boolean)); });
    $$("[data-describe]").forEach(b => b.onclick = () => { const [k, ns, n] = b.dataset.describe.split("/"); openText(`describe ${k} ${n}`, api(`/describe/${k}/${encodeURIComponent(n)}?namespace=${encodeURIComponent(ns)}`)); });
    $$("[data-yaml]").forEach(b => b.onclick = () => { const [k, ns, n] = b.dataset.yaml.split("/"); openText(`${k} ${n} (YAML)`, api(`/yaml/${k}/${encodeURIComponent(n)}?namespace=${encodeURIComponent(ns)}`)); });
    $$("[data-exec]").forEach(b => b.onclick = () => { const [ns, p] = b.dataset.exec.split("/"); openExec(ns, p, b.dataset.containers.split(",").filter(Boolean)); });
    $$("[data-delpod]").forEach(b => b.onclick = async () => {
      const [ns, p] = b.dataset.delpod.split("/");
      if (!confirm(`Delete pod ${p} in ${ns}? If a controller owns it, a new pod is created.`)) return;
      try { await NX.api.post(api(`/pods/${encodeURIComponent(ns)}/${encodeURIComponent(p)}/delete`)); NX.toast(`${p} deleted.`, "success"); refresh(true); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
    $$("[data-restart]").forEach(b => b.onclick = async () => {
      const [ns, n, kind] = b.dataset.restart.split("/");
      if (!confirm(`Rollout restart ${kind} ${n} in ${ns}? Pods are replaced one by one.`)) return;
      b.disabled = true; NX.toast(`Restarting ${n}… waiting for the rollout.`, "info");
      try { const r = await NX.api.post(api("/restart"), { namespace: ns, name: n, kind, wait: true });
        NX.toast(r.ok ? `${n}: ${r.status || "restarted"}` : `${n} restarted, rollout not finished yet: ${r.status}`, r.ok ? "success" : "warning"); refresh(true); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); b.disabled = false; }
    });
    $$("[data-delobj]").forEach(b => b.onclick = async () => {
      const [kind, ns, name] = b.dataset.delobj.split("/");
      if (!confirm(`Delete ${kind} ${name} in ${ns}?${kind === "pvc" ? " With the default Delete reclaim policy the volume's data is deleted too." : ""}`)) return;
      try { await NX.api.post(api("/delete"), { kind, namespace: ns, name }); NX.toast(`${kind} ${name} deleted.`, "success"); refresh(true); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
    $$("[data-node]").forEach(b => b.onclick = async () => {
      const [node, action] = b.dataset.node.split("/");
      const msg = { cordon: `Cordon ${node}? No new pods are scheduled on it.`, uncordon: `Allow scheduling on ${node} again?`,
        drain: `Drain ${node}? It is cordoned and its pods are evicted (DaemonSets stay). PodDisruptionBudgets are respected.` }[action];
      if (!confirm(msg)) return;
      b.disabled = true; if (action === "drain") NX.toast(`Draining ${node}…`, "info");
      try { const r = await NX.api.post(api(`/nodes/${encodeURIComponent(node)}/${action}`), {}); NX.toast(r.output.split("\n").pop() || `${node}: ${action} done`, "success"); refresh(true); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); b.disabled = false; refresh(true); }
    });
    $$("[data-hpa]").forEach(b => b.onclick = async () => {
      const [ns, name, lo, hi] = b.dataset.hpa.split("/");
      const v = prompt(`Min and max replicas for HPA ${name} (now ${lo}-${hi}), e.g. 2-10:`, `${lo}-${hi}`);
      if (v === null) return;
      const [a, z] = v.split("-").map(x => parseInt(x, 10));
      try { await NX.api.post(api("/hpa"), { namespace: ns, name, min: a, max: z }); NX.toast(`${name}: ${a}-${z} replicas.`, "success"); refresh(true); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
    $$("[data-setimg]").forEach(b => b.onclick = () => openSetImage(...b.dataset.setimg.split("/"), b.dataset.images.split(",")));
    $$("[data-history]").forEach(b => b.onclick = () => openHistory(...b.dataset.history.split("/")));
    $$("[data-ng-scale]").forEach(b => b.onclick = () => openNodegroupScale(JSON.parse(b.dataset.ngScale)));
    $$("[data-ng-upgrade]").forEach(b => b.onclick = async () => {
      if (!confirm(`Upgrade node group ${b.dataset.ngUpgrade} to the control plane version? Nodes are replaced one at a time.`)) return;
      try { const r = await NX.api.post(api(`/nodegroups/${encodeURIComponent(b.dataset.ngUpgrade)}/upgrade`), {}); NX.toast(`Node group upgrade started (${r.update.id}).`, "success"); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
    $$("[data-addon]").forEach(b => b.onclick = async () => {
      const [name, ver] = b.dataset.addon.split("|");
      if (!confirm(`Update add-on ${name} to ${ver}? Existing custom settings are preserved.`)) return;
      try { const r = await NX.api.post(api(`/addons/${encodeURIComponent(name)}/update`), { version: ver }); NX.toast(`${name} update started (${r.update.id}).`, "success"); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
    $$("[data-delns]").forEach(b => b.onclick = async () => {
      const ns = b.dataset.delns;
      const typed = prompt(`Delete namespace ${ns} and EVERYTHING in it?\nType the namespace name to confirm:`);
      if (typed === null) return;
      try { await NX.api.post(api("/delete"), { kind: "namespace", name: ns, confirm: typed.trim() }); NX.toast(`Namespace ${ns} is being deleted.`, "warning"); refresh(true); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
    $$("[data-scale]").forEach(b => b.onclick = async () => {
      const [ns, n, kind, cur] = b.dataset.scale.split("/");
      const v = prompt(`Replicas for ${kind} ${n} (now ${cur}). If an HPA manages it, the HPA may change this again.`, cur);
      if (v === null) return;
      try { await NX.api.post(api("/scale"), { namespace: ns, name: n, kind, replicas: +v }); NX.toast(`${n} scaled to ${v}.`, "success"); refresh(true); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    });
  }

  /* ---------------- cluster lifecycle (EKS) ---------------- */
  async function drawCluster() {
    const c = cl();
    if (c.source !== "eks") {
      $("#k-pane").innerHTML = `<div class="nx-card"><div class="nx-card-body small">
        <b>${esc(c.name)}</b> is a kubeconfig cluster (${esc(c.context)}). Control plane, node groups, add-ons and upgrades are managed here for <b>EKS</b> clusters.
        Everything inside the cluster (workloads, namespaces, access, storage) works on the other tabs.
        <div class="mt-2"><a class="btn btn-sm btn-primary" href="launch.html?type=eks-cluster"><i class="bi bi-plus-lg me-1"></i>Create an EKS cluster</a></div></div></div>`;
      return;
    }
    $("#k-pane").innerHTML = loading("Reading the EKS control plane…");
    const r = await NX.api.get(api("/eks"));
    const k = r.cluster, tf = r.managed_by === "terraform";
    const via = tf ? `<span class="nx-badge b-primary">managed by Terraform</span> <span class="small nx-muted">changes become reviewed IaC changes in <a href="environments.html?env=${encodeURIComponent(r.environment)}">${esc(r.environment)}</a></span>`
      : `<span class="nx-badge b-secondary">not created by the portal</span> <span class="small nx-muted">changes call the EKS API directly (live mode only)</span>`;
    const bad = (r.insights || []).filter(i => i.status && i.status !== "PASSING");
    $("#k-pane").innerHTML = `<div class="nx-card mb-3"><div class="nx-card-body">
        <div class="d-flex flex-wrap gap-2 align-items-center mb-2"><span class="fw-bold">${esc(k.name)}</span><span class="nx-badge b-${k.status === "ACTIVE" ? "success" : "warning"}">${esc(k.status)}</span>
          <span class="nx-badge b-secondary">Kubernetes ${esc(k.version)}</span><span class="nx-badge b-secondary">${esc(k.platform || "")}</span>
          <span class="nx-badge b-${k.endpoint_public ? "warning" : "success"}">${k.endpoint_public ? "public API" : "private API"}</span>
          ${k.upgrade_policy ? `<span class="nx-badge b-${k.upgrade_policy === "EXTENDED" ? "warning" : "secondary"}">${esc(k.upgrade_policy)} support</span>` : ""}</div>
        <div class="mb-2">${via}</div>
        <div class="d-flex flex-wrap gap-2">
          ${role() === "admin" && r.next_version ? `<button class="btn btn-sm btn-outline-primary" id="k-upgrade"><i class="bi bi-arrow-up-circle me-1"></i>Upgrade control plane to ${esc(r.next_version)}</button>` : ""}
          ${tf && canPlatform() ? `<button class="btn btn-sm btn-outline-danger" id="k-delcluster"><i class="bi bi-trash me-1"></i>Delete cluster</button>` : ""}
        </div></div></div>
      <h2 class="h6 fw-bold">Upgrade readiness ${bad.length ? `<span class="nx-badge b-warning">${bad.length} to check</span>` : (r.insights || []).length ? '<span class="nx-badge b-success">passing</span>' : ""}</h2>
      ${table(["Check", "Category", "Status", "Detail"], (r.insights || []).map(i => `<tr><td class="small">${esc(i.name)}</td><td class="small">${esc(i.category || "")}</td>
        <td><span class="nx-badge b-${i.status === "PASSING" ? "success" : i.status === "ERROR" ? "danger" : "warning"}">${esc(i.status)}</span></td><td class="small">${esc(i.reason || "")}</td></tr>`), "No upgrade insights reported.")}
      <h2 class="h6 fw-bold mt-3">Node groups</h2>
      ${table(["Node group", "Status", "Version", "Instance types", "Capacity", "Min / desired / max", "Health", ""], r.nodegroups.map(g => `<tr>
        <td class="nx-mono small">${esc(g.name)}</td><td><span class="nx-badge b-${g.status === "ACTIVE" ? "success" : "warning"}">${esc(g.status)}</span></td>
        <td>${esc(g.version || "")}${g.version && g.version !== k.version ? ' <span class="nx-badge b-warning">behind</span>' : ""}</td>
        <td class="small">${esc((g.instance_types || []).join(", "))}</td><td class="small">${esc(g.capacity || "")}</td>
        <td>${g.scaling ? `${g.scaling.minSize} / <b>${g.scaling.desiredSize}</b> / ${g.scaling.maxSize}` : ""}</td><td class="small text-danger">${esc((g.health || []).join("; "))}${esc(g.error || "")}</td>
        <td class="text-end" style="white-space:nowrap">${canPlatform() && g.scaling ? `<button class="btn btn-sm btn-outline-primary" data-ng-scale='${esc(JSON.stringify({ name: g.name, ...g.scaling, types: g.instance_types }))}'>Scale</button>` : ""}
          ${canPlatform() && !tf && g.version && g.version !== k.version ? `<button class="btn btn-sm btn-outline-warning" data-ng-upgrade="${esc(g.name)}">Upgrade</button>` : ""}</td></tr>`),
        r.errors && r.errors.nodegroups ? r.errors.nodegroups : "No managed node groups (Karpenter or self-managed nodes appear on the Nodes tab).")}
      <h2 class="h6 fw-bold mt-3">Add-ons</h2>
      ${table(["Add-on", "Version", "Status", "Latest compatible", ""], r.addons.map(a => `<tr><td class="nx-mono small">${esc(a.name)}</td><td class="small">${esc(a.version || "")}</td>
        <td><span class="nx-badge b-${a.status === "ACTIVE" ? "success" : "warning"}">${esc(a.status)}</span></td><td class="small">${esc(a.latest || "")}</td>
        <td class="text-end">${canPlatform() && a.update_available ? `<button class="btn btn-sm btn-outline-primary" data-addon="${esc(a.name)}|${esc(a.latest)}">Update</button>` : ""}</td></tr>`),
        r.errors && r.errors.addons ? "Add-ons could not be read: " + r.errors.addons : "No EKS-managed add-ons.")}`;
    const up = $("#k-upgrade");
    if (up) up.onclick = async () => {
      if (!confirm(`Upgrade ${k.name} from ${k.version} to ${r.next_version}?\n\nCheck the upgrade readiness list first. Node groups and add-ons are upgraded afterwards. ${tf ? "This creates a reviewed Terraform change." : "This calls eks:UpdateClusterVersion now and cannot be undone."}`)) return;
      try { const x = await NX.api.post(api("/upgrade"), { version: r.next_version });
        NX.toast(x.via === "terraform" ? `Upgrade proposed as change ${x.change.id} (${x.change.status}).` : `Control plane upgrade started (${x.update.id}).`, "success"); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    };
    const dl = $("#k-delcluster");
    if (dl) dl.onclick = async () => {
      if (prompt(`Delete EKS cluster ${k.name}? This creates a reviewed Terraform destroy change.\nType the cluster name to confirm:`) !== k.name) return;
      try { const x = await NX.api.post(api("/decommission"), {}); NX.toast(`Delete proposed as change ${x.change.id}.`, "warning"); }
      catch (e) { NX.toast(UI.errorText(e), "danger"); }
    };
    wireActions();
  }

  function openNodegroupScale(g) {
    const m = UI.modal(`Scale node group ${g.name}`, `<div class="row g-3">
        <div class="col-4"><label class="form-label small fw-semibold">Min</label><input type="number" class="form-control" id="ng-min" value="${g.minSize}" min="0" max="200"></div>
        <div class="col-4"><label class="form-label small fw-semibold">Desired</label><input type="number" class="form-control" id="ng-des" value="${g.desiredSize}" min="0" max="200"></div>
        <div class="col-4"><label class="form-label small fw-semibold">Max</label><input type="number" class="form-control" id="ng-max" value="${g.maxSize}" min="1" max="200"></div></div>
      <div class="small nx-muted mt-2">If the Cluster Autoscaler or Karpenter manages this group, it adjusts desired within min and max.</div>
      <div class="alert alert-danger py-2 small mt-2 d-none" id="ng-err"></div>`, { size: "", footer: '<button class="btn btn-primary" id="ng-go">Apply</button>' });
    $("#ng-go", m.el).onclick = async () => {
      try { const x = await NX.api.post(api(`/nodegroups/${encodeURIComponent(g.name)}/scale`), { min: +$("#ng-min", m.el).value, desired: +$("#ng-des", m.el).value, max: +$("#ng-max", m.el).value });
        m.hide(); NX.toast(x.via === "terraform" ? `Proposed as change ${x.change.id} (${x.change.status}).` : `Scaling started (${x.update.id}).`, "success"); }
      catch (e) { const er = $("#ng-err", m.el); er.textContent = UI.errorText(e); er.classList.remove("d-none"); }
    };
  }

  /* ---------------- namespaces & access ---------------- */
  async function drawNamespaces(fresh) {
    $("#k-pane").innerHTML = loading();
    const [ns, pods] = await Promise.all([list("namespaces", fresh), list("pods", fresh)]);
    const count = pods.reduce((m, p) => (m[p.namespace] = (m[p.namespace] || 0) + 1, m), {});
    $("#k-pane").innerHTML = table(["Namespace", "Status", "Pods", "Team", "Pod security", "Age", ""], filt(ns).map(n => `<tr>
      <td class="nx-mono small">${esc(n.name)}</td><td><span class="nx-badge b-${n.status === "Active" ? "success" : "warning"}">${esc(n.status)}</span></td><td>${count[n.name] || 0}</td>
      <td class="small">${esc((n.labels || {}).team || "")}</td><td class="small">${esc((n.labels || {})["pod-security.kubernetes.io/enforce"] || "")}</td><td class="small">${esc(n.age)}</td>
      <td class="text-end"><button class="btn btn-sm btn-outline-secondary" data-describe="namespace//${esc(n.name)}"><i class="bi bi-info-circle"></i></button>
        ${canPlatform() && !n.system && n.name !== "default" ? `<button class="btn btn-sm btn-outline-danger" data-delns="${esc(n.name)}"><i class="bi bi-trash"></i></button>` : ""}</td></tr>`), "No namespaces.");
    wireActions();
  }
  async function drawAccess(fresh) {
    $("#k-pane").innerHTML = loading();
    const [rb, crb] = await Promise.all([list("rolebindings", fresh), list("clusterrolebindings", fresh)]);
    fillNamespaces(rb);
    $("#k-pane").innerHTML = `<h2 class="h6 fw-bold">Role bindings (per namespace)</h2>` + table(["Binding", "Namespace", "Role", "Subjects", ""], filt(rb).map(b => `<tr>
      <td class="nx-mono small">${esc(b.name)}${b.managed ? ' <span class="nx-badge b-primary">portal</span>' : ""}</td><td>${esc(b.namespace)}</td><td class="small">${esc(b.role)}</td><td class="small nx-mono">${esc(b.subjects)}</td>
      <td class="text-end">${canPlatform() ? `<button class="btn btn-sm btn-outline-danger" data-delobj="rolebinding/${esc(b.namespace)}/${esc(b.name)}"><i class="bi bi-trash"></i></button>` : ""}</td></tr>`), "No role bindings.") +
      `<h2 class="h6 fw-bold mt-3">Cluster role bindings</h2>` + table(["Binding", "Role", "Subjects"], filt(crb).map(b => `<tr><td class="nx-mono small">${esc(b.name)}</td><td class="small">${esc(b.role)}</td><td class="small nx-mono">${esc(b.subjects)}</td></tr>`), "No cluster role bindings outside the system ones.") +
      `<div class="small nx-muted mt-2">Who can reach the cluster at all is set by EKS access entries (IAM). Cluster-wide bindings are read-only here; grant namespace access with “Grant access”.</div>`;
    wireActions();
  }

  /* ---------------- create forms (template -> dry run -> apply) ---------------- */
  const nsOpts = () => [...$("#k-ns").options].map(o => o.value).filter(Boolean);
  const FORMS = {
    deployment: { title: "Deploy an application", fields: [
      ["name", "Name", "text", "", "web"], ["namespace", "Namespace", "ns"], ["image", "Container image", "text", "", "public.ecr.aws/nginx/nginx:1.27"],
      ["replicas", "Replicas", "number", 2], ["port", "Container port", "number", 8080], ["probe_path", "Readiness probe path (optional)", "text", "", "/healthz"],
      ["cpu", "CPU request", "text", "100m"], ["memory", "Memory request", "text", "128Mi"], ["memory_limit", "Memory limit", "text", "256Mi"],
      ["service", "Service", "select", "ClusterIP", ["ClusterIP", "LoadBalancer", "none"]], ["service_port", "Service port", "number", 80],
      ["internal_lb", "Internal load balancer (if LoadBalancer)", "bool", true], ["pdb", "PodDisruptionBudget (keeps 1 pod during drains)", "bool", true],
      ["run_as_non_root", "Run as non-root", "bool", true]] },
    namespace: { title: "Create a namespace", platform: true, fields: [
      ["name", "Name", "text", "", "team-payments"], ["team", "Owning team", "text", ""], ["labels", "Extra labels (key=value, comma separated)", "text", ""],
      ["pod_security", "Pod Security level", "select", "baseline", ["baseline", "restricted", "privileged"]],
      ["quota_cpu", "CPU quota (requests, optional)", "text", "", "8"], ["quota_memory", "Memory quota (optional)", "text", "", "16Gi"], ["quota_pods", "Max pods (optional)", "number", ""],
      ["default_deny", "Default-deny ingress + allow same namespace", "bool", true]] },
    hpa: { title: "Create an autoscaler (HPA)", fields: [
      ["namespace", "Namespace", "ns"], ["target", "Deployment name", "text", ""], ["kind", "Kind", "select", "Deployment", ["Deployment", "StatefulSet"]],
      ["min", "Min replicas", "number", 2], ["max", "Max replicas", "number", 10], ["cpu", "Target CPU %", "number", 70], ["memory", "Target memory % (optional)", "number", ""]] },
    ingress: { title: "Expose a service (Ingress)", fields: [
      ["name", "Name", "text", ""], ["namespace", "Namespace", "ns"], ["service", "Service name", "text", ""], ["port", "Service port", "number", 80],
      ["host", "Host (optional)", "text", "", "app.example.com"], ["path", "Path", "text", "/"], ["class", "Ingress class", "text", "alb"],
      ["public", "Internet-facing (ALB)", "bool", false], ["certificate_arn", "ACM certificate ARN (ALB, optional)", "text", ""], ["tls_secret", "TLS secret (non-ALB, optional)", "text", ""]] },
    networkpolicy: { title: "Add a network policy", platform: true, fields: [
      ["namespace", "Namespace", "ns"], ["policy", "Policy", "select", "default-deny", ["default-deny", "allow-same-namespace", "allow-from-namespace", "allow-port"]],
      ["from_namespace", "Allow from namespace (allow-from-namespace)", "text", ""], ["app", "App label (allow-port)", "text", ""], ["port", "Port (allow-port)", "number", ""]] },
    quota: { title: "Set a resource quota", platform: true, fields: [
      ["namespace", "Namespace", "ns"], ["requests_cpu", "CPU requests", "text", "", "4"], ["limits_cpu", "CPU limits", "text", ""], ["requests_memory", "Memory requests", "text", "", "8Gi"],
      ["limits_memory", "Memory limits", "text", "", "16Gi"], ["requests_storage", "Storage", "text", "", "200Gi"], ["pods", "Pods", "number", ""], ["services", "Services", "number", ""],
      ["persistentvolumeclaims", "Volume claims", "number", ""]] },
    pvc: { title: "Create a volume claim (PVC)", fields: [
      ["name", "Name", "text", "", "data"], ["namespace", "Namespace", "ns"], ["size", "Size", "text", "10Gi"], ["storage_class", "Storage class", "sc"],
      ["access_mode", "Access mode", "select", "ReadWriteOnce", ["ReadWriteOnce", "ReadWriteMany", "ReadOnlyMany", "ReadWriteOncePod"]]] },
    rolebinding: { title: "Grant namespace access", platform: true, fields: [
      ["namespace", "Namespace", "ns"], ["role", "Access level", "select", "view", ["view", "edit", "admin"]],
      ["subject_kind", "Who", "select", "Group", ["Group", "User", "ServiceAccount"]], ["subject", "Group / user / service account name", "text", "", "payments-developers"]] },
  };
  const CREATE = {
    workloads: [["deployment", "Deploy app", "bi-rocket-takeoff"]], namespaces: [["namespace", "Create namespace", "bi-folder-plus"]],
    network: [["ingress", "Create ingress", "bi-signpost"], ["networkpolicy", "Network policy", "bi-shield-lock"]],
    config: [["hpa", "Create HPA", "bi-arrows-angle-expand"], ["quota", "Set quota", "bi-speedometer"]],
    storage: [["pvc", "Create PVC", "bi-hdd"]], access: [["rolebinding", "Grant access", "bi-person-plus"]],
  };
  function drawCreate(t) {
    const host = $("#k-create"); if (!host) return;
    const items = (CREATE[t] || []).filter(([k]) => FORMS[k].platform ? canPlatform() : canChange());
    host.innerHTML = items.map(([k, l, i]) => `<button class="btn btn-sm btn-primary" data-form="${k}"><i class="bi ${i} me-1"></i>${esc(l)}</button>`).join("") +
      (canChange() && ["workloads", "network", "config", "storage", "namespaces", "access"].includes(t) ? '<button class="btn btn-sm btn-outline-secondary" id="k-yaml"><i class="bi bi-filetype-yml me-1"></i>Apply YAML</button>' : "");
    $$("[data-form]", host).forEach(b => b.onclick = () => openForm(b.dataset.form));
    const y = $("#k-yaml", host); if (y) y.onclick = openYaml;
  }

  function previewBlock(r) {
    return `<div class="small fw-semibold mt-3">Server-side dry run <span class="nx-badge b-success">accepted</span></div>
      <div class="small nx-mono">${r.objects.map(esc).join("<br>")}</div>
      <div class="small fw-semibold mt-3">Changes against the live cluster</div>${UI.diffHtml(r.diff)}
      <details class="mt-2"><summary class="small fw-semibold">Full manifest</summary><pre class="nx-log" style="max-height:300px">${esc(r.manifest)}</pre></details>`;
  }

  function openForm(key) {
    const f = FORMS[key], cur = $("#k-ns").value;
    const input = ([name, label, type, def, ph]) => {
      const id = "kf-" + name;
      if (type === "ns") return `<div class="col-md-6"><label class="form-label small fw-semibold" for="${id}">${esc(label)}</label><input class="form-control" id="${id}" list="kf-nslist" value="${esc(cur || "")}" placeholder="namespace"></div>`;
      if (type === "sc") return `<div class="col-md-6"><label class="form-label small fw-semibold" for="${id}">${esc(label)}</label><select class="form-select" id="${id}"><option value="">cluster default</option>${(S.storageClasses || []).map(s => `<option>${esc(s.name)}</option>`).join("")}</select></div>`;
      if (type === "select") return `<div class="col-md-6"><label class="form-label small fw-semibold" for="${id}">${esc(label)}</label><select class="form-select" id="${id}">${ph.map(o => `<option ${o === def ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></div>`;
      if (type === "bool") return `<div class="col-md-6"><div class="form-check form-switch mt-md-4"><input class="form-check-input" type="checkbox" id="${id}" ${def ? "checked" : ""}><label class="form-check-label small" for="${id}">${esc(label)}</label></div></div>`;
      return `<div class="col-md-6"><label class="form-label small fw-semibold" for="${id}">${esc(label)}</label><input class="form-control" id="${id}" type="${type === "number" ? "number" : "text"}" value="${esc(def ?? "")}" placeholder="${esc(ph || "")}"></div>`;
    };
    const m = UI.modal(f.title + ` · ${cl().name}`, `<datalist id="kf-nslist">${nsOpts().map(n => `<option value="${esc(n)}">`).join("")}</datalist>
      <div class="row g-3">${f.fields.map(input).join("")}</div>
      <div class="alert alert-danger py-2 small mt-3 d-none" id="kf-err"></div><div id="kf-prev"></div>`,
      { size: "modal-xl", footer: '<button class="btn btn-outline-primary" id="kf-dry"><i class="bi bi-eye me-1"></i>Preview (dry run)</button><button class="btn btn-primary" id="kf-apply" disabled>Apply</button>' });
    const params = () => Object.fromEntries(f.fields.map(([name, , type]) => {
      const el = $("#kf-" + name, m.el); let v = type === "bool" ? el.checked : el.value.trim();
      if (type === "number" && v !== "") v = Number(v);
      return [name, v];
    }).filter(([, v]) => v !== ""));
    const err = (e) => { const x = $("#kf-err", m.el); x.textContent = UI.errorText(e); x.classList.remove("d-none"); };
    $$("input,select", m.el).forEach(el => el.addEventListener("input", () => { $("#kf-apply", m.el).disabled = true; }));
    $("#kf-dry", m.el).onclick = async () => {
      $("#kf-err", m.el).classList.add("d-none"); $("#kf-prev", m.el).innerHTML = loading("Validating with the API server…");
      try { const r = await NX.api.post(api("/apply"), { template: key, params: params(), dry_run: true }); $("#kf-prev", m.el).innerHTML = previewBlock(r); $("#kf-apply", m.el).disabled = false; }
      catch (e) { $("#kf-prev", m.el).innerHTML = ""; err(e); }
    };
    $("#kf-apply", m.el).onclick = async () => {
      $("#kf-apply", m.el).disabled = true;
      try { const r = await NX.api.post(api("/apply"), { template: key, params: params(), dry_run: false }); m.hide(); NX.toast(r.output.split("\n").join(" · "), "success"); refresh(true); }
      catch (e) { err(e); }
    };
  }

  function openYaml() {
    const m = UI.modal(`Apply YAML · ${cl().name}`, `<p class="small nx-muted">Namespaced objects only: Deployments, Services, Ingresses, ConfigMaps, HPAs, PVCs, NetworkPolicies, Quotas, RoleBindings and similar. Secrets and cluster-wide RBAC are not accepted. Always previewed with a server-side dry run first.</p>
      <textarea class="form-control nx-mono" id="ky-text" rows="16" placeholder="apiVersion: v1&#10;kind: ConfigMap&#10;metadata:&#10;  name: app-config&#10;  namespace: shop&#10;data:&#10;  LOG_LEVEL: info"></textarea>
      <div class="alert alert-danger py-2 small mt-3 d-none" id="ky-err"></div><div id="ky-prev"></div>`,
      { size: "modal-xl", footer: '<button class="btn btn-outline-primary" id="ky-dry"><i class="bi bi-eye me-1"></i>Preview (dry run)</button><button class="btn btn-primary" id="ky-apply" disabled>Apply</button>' });
    const err = (e) => { const x = $("#ky-err", m.el); x.textContent = UI.errorText(e); x.classList.remove("d-none"); };
    $("#ky-text", m.el).oninput = () => { $("#ky-apply", m.el).disabled = true; };
    $("#ky-dry", m.el).onclick = async () => {
      $("#ky-err", m.el).classList.add("d-none");
      try { const r = await NX.api.post(api("/apply"), { yaml: $("#ky-text", m.el).value, dry_run: true }); $("#ky-prev", m.el).innerHTML = previewBlock(r); $("#ky-apply", m.el).disabled = false; }
      catch (e) { $("#ky-prev", m.el).innerHTML = ""; err(e); }
    };
    $("#ky-apply", m.el).onclick = async () => {
      try { const r = await NX.api.post(api("/apply"), { yaml: $("#ky-text", m.el).value, dry_run: false }); m.hide(); NX.toast(r.output.split("\n").join(" · "), "success"); refresh(true); }
      catch (e) { err(e); }
    };
  }

  function openSetImage(kind, ns, name, images) {
    const m = UI.modal(`Change image · ${name}`, `<div class="row g-3">
        <div class="col-md-4"><label class="form-label small fw-semibold">Container</label><input class="form-control" id="si-c" value="${esc(name)}"></div>
        <div class="col-md-8"><label class="form-label small fw-semibold">New image</label><input class="form-control nx-mono" id="si-i" value="${esc(images[0] || "")}"></div></div>
      <div class="small nx-muted mt-2">Current: ${images.map(esc).join(", ")}. A rolling update starts immediately; roll back from History.</div>
      <div class="alert alert-danger py-2 small mt-2 d-none" id="si-err"></div>`, { footer: '<button class="btn btn-primary" id="si-go">Update</button>' });
    $("#si-go", m.el).onclick = async () => {
      try { await NX.api.post(api("/set-image"), { kind, namespace: ns, name, container: $("#si-c", m.el).value.trim(), image: $("#si-i", m.el).value.trim() });
        m.hide(); NX.toast(`${name}: rolling out the new image.`, "success"); refresh(true); }
      catch (e) { const x = $("#si-err", m.el); x.textContent = UI.errorText(e); x.classList.remove("d-none"); }
    };
  }

  async function openHistory(kind, ns, name) {
    const m = UI.modal(`Rollout history · ${name}`, `<div id="kh">${loading()}</div>`, { size: "modal-lg" });
    try {
      const r = await NX.api.post(api("/rollout"), { kind, namespace: ns, name, action: "history" });
      const revs = (r.text.match(/^\s*(\d+)\s/gm) || []).map(x => x.trim());
      $("#kh", m.el).innerHTML = `<pre class="nx-log">${esc(r.text)}</pre>
        ${canChange() && revs.length > 1 ? `<div class="d-flex gap-2 align-items-center mt-2"><select class="form-select form-select-sm" id="kh-rev" style="max-width:200px">${revs.slice(0, -1).reverse().map(v => `<option>${esc(v)}</option>`).join("")}</select>
          <button class="btn btn-sm btn-warning" id="kh-undo">Roll back to this revision</button></div>` : '<div class="small nx-muted">Only one revision: nothing to roll back to.</div>'}`;
      const u = $("#kh-undo", m.el);
      if (u) u.onclick = async () => {
        const rev = $("#kh-rev", m.el).value;
        if (!confirm(`Roll ${name} back to revision ${rev}?`)) return;
        try { await NX.api.post(api("/rollout"), { kind, namespace: ns, name, action: "undo", revision: rev }); m.hide(); NX.toast(`${name} rolled back to revision ${rev}.`, "success"); refresh(true); }
        catch (e) { NX.toast(UI.errorText(e), "danger"); }
      };
    } catch (e) { $("#kh", m.el).innerHTML = failBox(e); }
  }

  async function openText(title, url) {
    const m = UI.modal(title, `<div id="k-text">${loading()}</div>`, { size: "modal-xl" });
    try { const r = await NX.api.get(url); $("#k-text", m.el).innerHTML = `<pre class="nx-log" style="max-height:65vh">${esc(r.text)}</pre>`; }
    catch (e) { $("#k-text", m.el).innerHTML = failBox(e); }
  }

  async function openDiagnose(ns, pod) {
    const m = UI.modal(`Diagnose ${pod}`, `<div id="k-dg">${loading("Reading pod status and events…")}</div>`, { size: "modal-xl" });
    try {
      const r = await NX.api.get(api(`/diagnose/${encodeURIComponent(ns)}/${encodeURIComponent(pod)}`));
      const tone = { error: "danger", warning: "warning", ok: "success" };
      $("#k-dg", m.el).innerHTML = `<div class="d-flex flex-wrap gap-2 mb-3">${podBadge(r.pod)} <span class="nx-badge b-secondary">${esc(r.pod.ready)} ready</span>
          <span class="nx-badge b-secondary">${r.pod.restarts} restarts</span><span class="nx-badge b-secondary">node ${esc(r.pod.node || "none")}</span><span class="nx-badge b-secondary">QoS ${esc(r.pod.qos)}</span></div>
        ${r.hints.map(h => `<div class="alert alert-${tone[h.severity]} py-2"><div class="fw-semibold small">${esc(h.title)}</div><div class="small">${esc(h.detail)}</div></div>`).join("")}
        <h6 class="fw-bold mt-3">Events for this pod</h6>${r.events.length ? r.events.map(e => `<div class="small"><span class="nx-badge b-${e.type === "Warning" ? "warning" : "secondary"}">${esc(e.reason)}</span> ${esc(e.message)} <span class="nx-muted">(${esc(e.last)}, x${e.count})</span></div>`).join("") : '<div class="small nx-muted">None recorded (events expire after about an hour).</div>'}
        <div class="d-flex gap-2 mt-3">
          ${canRead() ? `<button class="btn btn-sm btn-outline-secondary" id="dg-logs">Logs</button><button class="btn btn-sm btn-outline-secondary" id="dg-prev">Previous container logs</button>` : ""}
          <button class="btn btn-sm btn-outline-secondary" id="dg-desc">Describe</button></div>`;
      const cs = r.pod.containers;
      const go = (fn) => { m.hide(); setTimeout(fn, 300); };
      if ($("#dg-logs", m.el)) { $("#dg-logs", m.el).onclick = () => go(() => openLogs(ns, pod, cs)); $("#dg-prev", m.el).onclick = () => go(() => openLogs(ns, pod, cs, true)); }
      $("#dg-desc", m.el).onclick = () => go(() => openText(`describe pod ${pod}`, api(`/describe/pod/${encodeURIComponent(pod)}?namespace=${encodeURIComponent(ns)}`)));
    } catch (e) { $("#k-dg", m.el).innerHTML = failBox(e); }
  }

  function openLogs(ns, pod, containers, previous) {
    const m = UI.modal(`Logs · ${pod}`, `<div class="d-flex flex-wrap gap-2 mb-2 align-items-center">
        ${containers.length > 1 ? `<select class="form-select form-select-sm" id="lg-c" style="max-width:180px">${containers.map(c => `<option>${esc(c)}</option>`).join("")}</select>` : ""}
        <select class="form-select form-select-sm" id="lg-tail" style="max-width:140px"><option value="200">last 200</option><option value="1000">last 1000</option><option value="5000">last 5000</option></select>
        <select class="form-select form-select-sm" id="lg-since" style="max-width:140px"><option value="">any time</option><option>5m</option><option>15m</option><option>1h</option><option>6h</option><option>24h</option></select>
        <div class="form-check mb-0"><input class="form-check-input" type="checkbox" id="lg-prev" ${previous ? "checked" : ""}><label class="form-check-label small" for="lg-prev">Previous container</label></div>
        <input class="form-control form-control-sm" id="lg-q" placeholder="Highlight text" style="max-width:200px">
        <button class="btn btn-sm btn-primary" id="lg-go"><i class="bi bi-arrow-clockwise"></i></button></div>
      <pre class="nx-log" id="lg-out" style="max-height:62vh">${esc("Loading…")}</pre>`, { size: "modal-xl" });
    let text = "";
    const paint = () => {
      const q = $("#lg-q", m.el).value.trim();
      $("#lg-out", m.el).innerHTML = q ? esc(text).split(esc(q)).join(`<mark>${esc(q)}</mark>`) : esc(text || "(no output)");
    };
    const load = async () => {
      const c = $("#lg-c", m.el);
      const qs = new URLSearchParams({ tail: $("#lg-tail", m.el).value });
      if (c) qs.set("container", c.value);
      if ($("#lg-since", m.el).value) qs.set("since", $("#lg-since", m.el).value);
      if ($("#lg-prev", m.el).checked) qs.set("previous", "1");
      $("#lg-out", m.el).textContent = "Loading…";
      try { text = (await NX.api.get(api(`/logs/${encodeURIComponent(ns)}/${encodeURIComponent(pod)}?${qs}`))).text; paint();
        const o = $("#lg-out", m.el); o.scrollTop = o.scrollHeight; }
      catch (e) { $("#lg-out", m.el).textContent = UI.errorText(e); }
    };
    $("#lg-go", m.el).onclick = load; $("#lg-q", m.el).oninput = paint;
    ["#lg-c", "#lg-tail", "#lg-since", "#lg-prev"].forEach(s => { const n = $(s, m.el); if (n) n.onchange = load; });
    load();
  }

  function openExec(ns, pod, containers) {
    const c = cl(), hist = [];
    const m = UI.modal(`Run command · ${pod}`, `
      <div class="alert alert-${c.tier === "production" ? "danger" : "warning"} py-2 small"><i class="bi bi-shield-exclamation me-1"></i>
        Commands run as the container user on <b>${esc(c.name)}</b> (${esc(c.tier)}). Each command is recorded in the audit log, with values that look like passwords or tokens masked. Not an interactive shell: each command runs once with <span class="nx-mono">sh -c</span>.</div>
      <div class="d-flex gap-2 mb-2">${containers.length > 1 ? `<select class="form-select" id="ex-c" style="max-width:180px">${containers.map(x => `<option>${esc(x)}</option>`).join("")}</select>` : ""}
        <input class="form-control nx-mono" id="ex-cmd" placeholder="env | sort, df -h, cat /etc/resolv.conf, wget -qO- localhost:8080/health" autocomplete="off">
        <button class="btn btn-dark" id="ex-go">Run</button></div>
      <div class="d-flex flex-wrap gap-1 mb-2">${["id", "df -h", "cat /etc/resolv.conf", "ps aux", "env | sort", "netstat -tlnp || ss -tlnp"].map(q => `<button class="btn btn-sm btn-outline-secondary nx-mono" data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
      <pre class="nx-log" id="ex-out" style="max-height:55vh;background:#0b1220;color:#d1e7ff"></pre>`, { size: "modal-xl" });
    const out = $("#ex-out", m.el), input = $("#ex-cmd", m.el);
    const run = async () => {
      const cmd = input.value.trim(); if (!cmd) return;
      hist.push(cmd); input.value = ""; $("#ex-go", m.el).disabled = true;
      out.textContent += `$ ${cmd}\n`;
      try {
        const sel = $("#ex-c", m.el);
        const r = await NX.api.post(api("/exec"), { namespace: ns, pod, container: sel ? sel.value : "", command: cmd, timeout: 30 });
        out.textContent += (r.stdout || "") + (r.stderr ? r.stderr + "\n" : "") + (r.exit ? `[exit ${r.exit}]\n` : "");
      } catch (e) { out.textContent += UI.errorText(e) + "\n"; }
      out.scrollTop = out.scrollHeight; $("#ex-go", m.el).disabled = false; input.focus();
    };
    let hi = 0;
    input.onkeydown = (e) => {
      if (e.key === "Enter") run();
      if (e.key === "ArrowUp" && hist.length) { hi = Math.max(0, (hi || hist.length) - 1); input.value = hist[hi]; }
    };
    $("#ex-go", m.el).onclick = run;
    $$("[data-q]", m.el).forEach(b => b.onclick = () => { input.value = b.dataset.q; run(); });
    setTimeout(() => input.focus(), 400);
  }

  /* ---------------- add cluster (admin) ---------------- */
  async function openAdd() {
    const accts = (await NX.loadAccounts()).filter(a => a.status === "connected");
    const m = UI.modal("Add a cluster", `
      <div class="btn-group mb-3 w-100" role="group">
        <input type="radio" class="btn-check" name="ka-src" id="ka-eks" value="eks" checked><label class="btn btn-outline-primary" for="ka-eks"><i class="bi bi-cloud me-1"></i>EKS in an AWS account</label>
        <input type="radio" class="btn-check" name="ka-src" id="ka-ctx" value="kubeconfig"><label class="btn btn-outline-primary" for="ka-ctx"><i class="bi bi-file-earmark-code me-1"></i>kubeconfig context</label></div>
      <div id="ka-eks-f"><div class="row g-3">
        <div class="col-md-6"><label class="form-label small fw-semibold">AWS account</label><select class="form-select" id="ka-acct">${accts.map(a => `<option value="${esc(a.id)}" data-region="${esc(a.region)}">${esc(a.alias)} (${esc(a.id)})</option>`).join("")}</select></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Region</label><input class="form-control" id="ka-region" value="${esc((accts[0] || {}).region || "")}"></div>
        <div class="col-12"><label class="form-label small fw-semibold">Cluster name</label><div class="input-group"><input class="form-control" id="ka-name" placeholder="prod-payments-apps">
          <button class="btn btn-outline-secondary" id="ka-disc" type="button">List clusters</button></div><div id="ka-found" class="mt-2"></div></div></div>
        <div class="small nx-muted mt-2">The portal calls eks:DescribeCluster with the account's role and authenticates with <span class="nx-mono">aws eks get-token</span>. The role needs an EKS access entry in the cluster.</div></div>
      <div id="ka-ctx-f" class="d-none"><label class="form-label small fw-semibold">Context on the portal host</label><select class="form-select" id="ka-context"><option>Loading…</option></select>
        <div class="small nx-muted mt-2">Contexts from the kubeconfig of the user running the portal (<span class="nx-mono">kubectl config get-contexts</span>).</div></div>
      <div class="row g-3 mt-1"><div class="col-md-6"><label class="form-label small fw-semibold">Tier</label><select class="form-select" id="ka-tier"><option>sandbox</option><option selected>development</option><option>staging</option><option>production</option></select></div>
        <div class="col-md-6"><label class="form-label small fw-semibold">Display name (optional)</label><input class="form-control" id="ka-label"></div></div>
      <div class="alert alert-danger py-2 small mt-3 d-none" id="ka-err"></div>`, { footer: '<button class="btn btn-primary" id="ka-go">Add cluster</button>' });
    const src = () => $("input[name=ka-src]:checked", m.el).value;
    $$("input[name=ka-src]", m.el).forEach(r => r.onchange = async () => {
      $("#ka-eks-f", m.el).classList.toggle("d-none", src() !== "eks"); $("#ka-ctx-f", m.el).classList.toggle("d-none", src() !== "kubeconfig");
      if (src() === "kubeconfig") {
        try { const r2 = await NX.api.get("/api/m04/contexts");
          $("#ka-context", m.el).innerHTML = r2.contexts.length ? r2.contexts.map(c => `<option>${esc(c)}</option>`).join("") : "<option value=''>No contexts found on the host</option>"; }
        catch (e) { $("#ka-context", m.el).innerHTML = `<option value=''>${esc(e.message)}</option>`; }
      }
    });
    $("#ka-acct", m.el).onchange = (e) => { $("#ka-region", m.el).value = e.target.selectedOptions[0].dataset.region; };
    $("#ka-disc", m.el).onclick = async () => {
      try { const r2 = await NX.api.get(`/api/m04/discover?account=${encodeURIComponent($("#ka-acct", m.el).value)}&region=${encodeURIComponent($("#ka-region", m.el).value)}`);
        $("#ka-found", m.el).innerHTML = r2.message ? `<div class="small nx-muted">${esc(r2.message)}</div>` : r2.clusters.length ? r2.clusters.map(c => `<button class="btn btn-sm btn-outline-primary me-1 mb-1" data-pick="${esc(c.name)}" ${c.registered ? "disabled" : ""}>${esc(c.name)}${c.registered ? " (added)" : ""}</button>`).join("") : '<div class="small nx-muted">No clusters in this region.</div>';
        $$("[data-pick]", m.el).forEach(b => b.onclick = () => { $("#ka-name", m.el).value = b.dataset.pick; });
      } catch (e) { $("#ka-found", m.el).innerHTML = `<div class="small text-danger">${esc(UI.errorText(e))}</div>`; }
    };
    $("#ka-go", m.el).onclick = async () => {
      const ctxv = $("#ka-context", m.el).value;
      const body = src() === "eks" ? { source: "eks", account_id: $("#ka-acct", m.el).value, region: $("#ka-region", m.el).value.trim(), name: $("#ka-name", m.el).value.trim() }
        : { source: "kubeconfig", context: ctxv, name: (ctxv || "").replace(/[^A-Za-z0-9_-]+/g, "-").slice(0, 90) };
      body.tier = $("#ka-tier", m.el).value; body.label = $("#ka-label", m.el).value.trim();
      try { const r2 = await NX.api.post("/api/m04/clusters", body); m.hide(); S.cid = r2.cluster.id; localStorage.setItem("nx-k8s-cluster", S.cid);
        await loadClusters(); testCluster(); setTab("overview"); }
      catch (e) { const er = $("#ka-err", m.el); er.textContent = UI.errorText(e); er.classList.remove("d-none"); }
    };
  }

  async function testCluster() {
    const b = $("#k-test"); b.disabled = true;
    try { const r = await NX.api.post(`/api/m04/clusters/${encodeURIComponent(S.cid)}/test`);
      const i = S.clusters.findIndex(c => c.id === S.cid); S.clusters[i] = r.cluster; drawMeta();
      NX.toast(r.cluster.last_note, r.cluster.last_status === "connected" ? "success" : "danger"); }
    catch (e) { NX.toast(UI.errorText(e), "danger"); }
    b.disabled = false;
  }

  async function init() {
    if (!$("#k-pane")) return;
    await loadClusters();
    if (NX.session.isAdmin()) { $("#k-add").classList.remove("d-none"); $("#k-add").onclick = openAdd; }
    $("#k-cluster").onchange = (e) => { S.cid = e.target.value; localStorage.setItem("nx-k8s-cluster", S.cid); $("#k-ns").value = ""; drawMeta(); refresh(); };
    $("#k-test").onclick = testCluster;
    $("#k-refresh").onclick = () => refresh(true);
    $$("#k-tabs [data-tab]").forEach(b => b.onclick = () => setTab(b.dataset.tab));
    let deb; $("#k-search").oninput = () => { clearTimeout(deb); deb = setTimeout(() => refresh(), 200); };
    ["#k-ns", "#k-status", "#k-kind", "#k-system"].forEach(s => $(s).onchange = () => refresh());
    if (cl()) setTab(UI.qs("tab") || "overview");
    S.timer = setInterval(() => { if (!document.hidden && ["overview", "pods"].includes(S.tab) && !document.querySelector(".modal.show")) refresh(); }, 30000);
  }
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
})();
