/* Live inventory: read-only snapshot of a connected AWS account (M02 /live/inventory). */
(function () {
  "use strict";
  const NX = window.NEXUS, UI = NX.ui, esc = NX.esc, $ = UI.$, $$ = UI.$$;
  const yes = (v) => v ? '<span class="nx-badge b-warning">yes</span>' : '<span class="nx-badge b-secondary">no</span>';
  const st = (v) => `<span class="nx-badge b-${/running|active|available|ACTIVE|in-use/i.test(v) ? "success" : /stopp|fail|delet/i.test(v) ? "danger" : "secondary"}">${esc(v)}</span>`;
  const SECTIONS = [
    { key: "ec2", title: "EC2 instances", icon: "bi-server", cols: [["name", "Name"], ["id", "Instance", "mono"], ["state", "State", st], ["type", "Type"], ["az", "AZ"], ["private_ip", "Private IP", "mono"], ["public_ip", "Public IP", "mono"], ["launched", "Launched"]] },
    { key: "vpcs", title: "VPCs", icon: "bi-diagram-3", cols: [["name", "Name"], ["id", "VPC", "mono"], ["cidr", "CIDR", "mono"], ["subnets", "Subnets"], ["public_subnets", "Public"], ["azs", "AZs"], ["default", "Default", yes]] },
    { key: "eks", title: "EKS clusters", icon: "bi-boxes", cols: [["name", "Name"], ["version", "Version"], ["status", "Status", st], ["nodegroups", "Node groups"], ["endpoint_public", "Public API", yes], ["vpc", "VPC", "mono"]] },
    { key: "load_balancers", title: "Load balancers", icon: "bi-signpost-split", cols: [["name", "Name"], ["type", "Type"], ["scheme", "Scheme"], ["state", "State", st], ["dns", "DNS", "mono"]] },
    { key: "rds", title: "RDS databases", icon: "bi-database", cols: [["id", "Identifier"], ["engine", "Engine"], ["class", "Class"], ["status", "Status", st], ["multi_az", "Multi-AZ", yes], ["encrypted", "Encrypted", yes], ["public", "Public", yes]] },
    { key: "dynamodb", title: "DynamoDB tables", icon: "bi-table", cols: [["name", "Table"], ["status", "Status", st], ["keys", "Keys"], ["billing", "Billing"], ["items", "Items"], ["size_mb", "Size (MB)"]] },
    { key: "s3", title: "S3 buckets (all regions)", icon: "bi-bucket", cols: [["name", "Bucket", "mono"], ["region", "Region"], ["created", "Created"]] },
    { key: "lambda", title: "Lambda functions", icon: "bi-lightning", cols: [["name", "Function"], ["runtime", "Runtime"], ["memory", "Memory (MB)"], ["modified", "Modified"]] },
  ];

  function cell(row, c) {
    const v = row[c[0]];
    if (typeof c[2] === "function") return c[2](v);
    if (v == null || v === "") return '<span class="nx-muted">-</span>';
    return c[2] === "mono" ? `<span class="nx-mono small">${esc(v)}</span>` : esc(v);
  }
  function sectionHtml(s, data) {
    const d = data[s.key] || { items: [], error: "not loaded" };
    const head = `<div class="nx-card-head"><i class="bi ${s.icon} text-primary"></i><h2>${esc(s.title)}</h2>
      <span class="nx-badge b-${d.error ? "danger" : "secondary"} ms-2">${d.error ? "error" : d.items.length}</span></div>`;
    if (d.error) return `<div class="nx-card mb-3">${head}<div class="nx-card-body"><div class="alert alert-danger py-2 small mb-0">${esc(d.error)}</div></div></div>`;
    if (!d.items.length) return `<div class="nx-card mb-3">${head}<div class="nx-card-body small nx-muted">None in this region.</div></div>`;
    return `<div class="nx-card mb-3">${head}<div class="nx-table-wrap" style="max-height:420px"><table class="nx-table"><thead><tr>${s.cols.map(c => `<th>${esc(c[1])}</th>`).join("")}</tr></thead>
      <tbody>${d.items.map(r => `<tr>${s.cols.map(c => `<td>${cell(r, c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>`;
  }

  async function fetchLive() {
    const acct = $("#iv-acct").value, region = $("#iv-region").value;
    if (!acct) return;
    const b = $("#iv-go"); b.disabled = true; b.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Reading AWS…';
    $("#iv-body").innerHTML = '<div class="nx-empty"><i class="bi bi-hourglass-split"></i>Reading the account. Large accounts take a few seconds.</div>';
    try {
      const r = await NX.api.get(`/api/m02/live/inventory?account=${encodeURIComponent(acct)}&region=${encodeURIComponent(region)}`);
      const d = r.sections, n = (k) => (d[k] && !d[k].error) ? d[k].items.length : "!";
      const running = d.ec2 && !d.ec2.error ? d.ec2.items.filter(i => i.state === "running").length : "!";
      const errors = Object.values(d).filter(x => x.error);
      const k = (l, v, i, t) => `<div class="col-6 col-xl-2"><div class="nx-card h-100"><div class="nx-card-body nx-kpi"><div class="nx-kpi-icon tone-${t}"><i class="bi ${i}"></i></div>
        <div><div class="nx-kpi-value" style="font-size:20px">${esc(v)}</div><div class="nx-kpi-label">${esc(l)}</div></div></div></div></div>`;
      $("#iv-kpis").innerHTML = k("EC2 running", `${running}/${n("ec2")}`, "bi-server", "primary") + k("VPCs", n("vpcs"), "bi-diagram-3", "info") +
        k("EKS clusters", n("eks"), "bi-boxes", "secondary") + k("Databases", `${n("rds")} RDS · ${n("dynamodb")} DDB`, "bi-database", "secondary") +
        k("S3 buckets", n("s3"), "bi-bucket", "secondary") + k("Load balancers", n("load_balancers"), "bi-signpost-split", "secondary");
      $("#iv-body").innerHTML = (errors.length === Object.keys(d).length
        ? `<div class="alert alert-danger small">Nothing could be read: ${esc(errors[0].error)} Test the account on the <a href="aws-accounts.html">AWS Accounts</a> page.</div>` : "") +
        `<div class="d-flex gap-2 mb-3"><a class="btn btn-sm btn-outline-primary" href="environments.html#import"><i class="bi bi-box-arrow-in-down me-1"></i>Use an existing VPC as an environment</a>
          <a class="btn btn-sm btn-outline-secondary" href="kubernetes.html">Operate EKS clusters</a></div>` +
        SECTIONS.map(s => sectionHtml(s, d)).join("");
      $("#iv-stamp").textContent = `${r.alias} (${r.account}) · ${r.region} · read ${r.fetched_at} UTC`;
    } catch (e) { $("#iv-body").innerHTML = `<div class="alert alert-danger small">${esc(UI.errorText(e))}</div>`; }
    b.disabled = false; b.innerHTML = '<i class="bi bi-cloud-download me-1"></i>Fetch live data';
  }

  async function init() {
    if (!$("#iv-body")) return;
    const accts = await NX.loadAccounts();
    if (!accts.length) { $("#iv-body").innerHTML = '<div class="nx-empty"><i class="bi bi-cloud-plus"></i>Connect an AWS account first on the <a href="aws-accounts.html">AWS Accounts</a> page.</div>'; $("#iv-go").disabled = true; return; }
    const want = UI.qs("account") || NX.activeAccount.getId() || accts[0].id;
    $("#iv-acct").innerHTML = accts.map(a => `<option value="${esc(a.id)}" ${a.id === want ? "selected" : ""}>${esc(a.alias)} (${esc(a.id)})${a.status === "connected" ? "" : " · " + esc(a.status)}</option>`).join("");
    const fillRegions = async () => {
      const a = accts.find(x => x.id === $("#iv-acct").value);
      let regs = [];
      try { regs = (await NX.api.get("/api/m02/regions?account=" + encodeURIComponent(a.id))).regions; } catch (e) { /* fall back below */ }
      if (!regs.find(r => r.code === a.region)) regs.unshift({ code: a.region, name: a.region });
      $("#iv-region").innerHTML = regs.map(r => `<option value="${esc(r.code)}" ${r.code === a.region ? "selected" : ""}>${esc(r.name)} · ${esc(r.code)}</option>`).join("");
    };
    $("#iv-acct").onchange = async () => { await fillRegions(); fetchLive(); };
    $("#iv-region").onchange = fetchLive;
    $("#iv-go").onclick = fetchLive;
    await fillRegions();
    fetchLive();
  }
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
})();
