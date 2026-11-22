/* FDE Nexus shared UI helpers for module pages (M02/M03 and later modules). */
(function () {
  "use strict";
  const NX = window.NEXUS, esc = NX.esc;
  const UI = NX.ui = {};

  UI.$ = (s, r) => (r || document).querySelector(s);
  UI.$$ = (s, r) => [...(r || document).querySelectorAll(s)];
  UI.money = (n) => (n < 0 ? "-$" : "$") + Math.abs(Number(n || 0)).toFixed(2);
  UI.qs = (k) => new URLSearchParams(location.search).get(k) || "";

  const CHANGE_TONE = {
    pending_approval: ["warning", "Pending approval"], approved: ["info", "Approved"], queued: ["secondary", "Queued"],
    mr_open: ["primary", "MR open"], merged: ["info", "Merged, CI applying"], committed: ["info", "Committed"],
    applied: ["success", "Applied"], blocked: ["danger", "Blocked by policy"], rejected: ["danger", "Rejected"],
    cancelled: ["secondary", "Cancelled"], failed: ["danger", "Failed"], closed: ["secondary", "MR closed"], conflict: ["danger", "Conflict"]
  };
  UI.changeBadge = (s) => { const [t, l] = CHANGE_TONE[s] || ["secondary", s]; return `<span class="nx-badge b-${t}">${esc(l)}</span>`; };
  UI.riskBadge = (r) => `<span class="nx-badge b-${{ low: "success", medium: "warning", high: "danger" }[r] || "secondary"}">${esc(r)} risk</span>`;
  const ENV_TONE = { active: "success", provisioning: "info", decommissioning: "warning", retired: "secondary", blocked: "danger", rejected: "danger", failed: "danger", cancelled: "secondary" };
  UI.envBadge = (s) => `<span class="nx-badge b-${ENV_TONE[s] || "secondary"}">${esc(s)}</span>`;
  UI.capBadge = (s) => `<span class="nx-badge b-${{ live: "success", partial: "warning", planned: "secondary" }[s] || "secondary"}">${esc(s)}</span>`;

  UI.modal = function (title, body, opts) {
    opts = opts || {};
    const id = "nxm-" + Math.random().toString(36).slice(2, 8);
    const host = document.createElement("div");
    host.className = "modal fade"; host.id = id; host.tabIndex = -1;
    host.innerHTML = `<div class="modal-dialog modal-dialog-scrollable ${opts.size || "modal-lg"}"><div class="modal-content">
      <div class="modal-header"><h5 class="modal-title">${esc(title)}</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
      <div class="modal-body">${body}</div>
      <div class="modal-footer">${opts.footer || ""}<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Close</button></div></div></div>`;
    document.body.appendChild(host);
    const inst = bootstrap.Modal.getOrCreateInstance(host);
    host.addEventListener("hidden.bs.modal", () => { host.remove(); if (opts.onClose) opts.onClose(); });
    inst.show();
    return { el: host, hide: () => inst.hide() };
  };

  UI.diffHtml = function (diff) {
    if (!diff) return '<div class="small nx-muted">No textual change.</div>';
    return `<pre class="nx-diff">${diff.split("\n").map(l => {
      const cls = l.startsWith("+++") || l.startsWith("---") ? "h" : l.startsWith("+") ? "a" : l.startsWith("-") ? "d" : l.startsWith("@@") ? "h" : "";
      return `<span class="${cls}">${esc(l)}</span>`;
    }).join("\n")}</pre>`;
  };

  UI.policyHtml = function (p) {
    if (!p) return "";
    const head = `<div class="d-flex flex-wrap gap-2 mb-2">
      ${p.passed ? '<span class="nx-badge b-success"><i class="bi bi-check-circle"></i>Policy passed</span>' : '<span class="nx-badge b-danger"><i class="bi bi-x-octagon"></i>Blocked by policy</span>'}
      <span class="nx-badge b-secondary">${p.rules_evaluated} rules</span>
      <span class="nx-badge b-${p.denies ? "danger" : "secondary"}">${p.denies} deny</span>
      <span class="nx-badge b-${p.warnings ? "warning" : "secondary"}">${p.warnings} warn</span></div>`;
    if (!p.findings.length) return head + '<div class="small nx-muted">No findings.</div>';
    return head + p.findings.map(f => `<div class="nx-finding f-${f.severity}">
      <div class="d-flex justify-content-between gap-2"><span class="fw-semibold small">${esc(f.rule)} · ${esc(f.title)}</span>
        <span class="nx-badge b-${f.severity === "deny" ? "danger" : "warning"}">${esc(f.severity)}</span></div>
      <div class="small">${esc(f.message)}${f.instance ? ` <span class="nx-muted">(${esc(f.instance)})</span>` : ""}</div>
      <div class="small nx-muted">${(f.frameworks || []).map(esc).join(" · ")}</div></div>`).join("");
  };

  UI.costHtml = function (c) {
    if (!c) return "";
    return `<div class="nx-sum-row fw-bold"><span>Estimated monthly change</span><span>${UI.money(c.monthly)}</span></div>
      ${(c.items || []).map(i => `<div class="nx-sum-row"><span class="nx-muted">${esc(i.item)}</span><span>${UI.money(i.monthly)}</span></div>`).join("")}
      ${(c.notes || []).length ? `<ul class="small nx-muted mt-2 mb-0">${c.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}`;
  };

  UI.validationHtml = function (v) {
    if (!v) return "";
    const row = (label, r) => `<div class="mb-2"><div class="small fw-semibold">${esc(label)} ${r.ok === true ? '<span class="nx-badge b-success">ok</span>' : r.ok === false ? '<span class="nx-badge b-danger">failed</span>' : '<span class="nx-badge b-secondary">skipped</span>'}</div>
      <pre class="nx-log">${esc(r.output || "")}</pre></div>`;
    return row("Atmos validation", v.atmos || {}) + row("Security scan" + (v.scan && v.scan.tool ? ` (${v.scan.tool})` : ""), v.scan || {});
  };

  /* Review block shared by every wizard: policy + cost + validation + YAML diff. */
  UI.reviewHtml = function (pv) {
    return `<div class="row g-3">
      <div class="col-lg-6"><div class="nx-card h-100"><div class="nx-card-body"><div class="fw-bold mb-2"><i class="bi bi-shield-check me-1"></i>Policy</div>${UI.policyHtml(pv.policy)}</div></div></div>
      <div class="col-lg-6"><div class="nx-card h-100"><div class="nx-card-body"><div class="fw-bold mb-2"><i class="bi bi-cash-coin me-1"></i>Cost</div>${UI.costHtml(pv.cost)}
        <div class="mt-3 d-flex gap-2 flex-wrap">${UI.riskBadge(pv.risk)} ${UI.changeBadge(pv.status === "approved" ? "approved" : pv.status)}</div>
        <div class="small nx-muted mt-1">${pv.status === "approved" ? "Low risk: this will be approved automatically." : pv.status === "blocked" ? "Fix the deny findings before submitting." : "An approver must review this change."}</div></div></div></div>
      <div class="col-12"><div class="nx-card"><div class="nx-card-body"><div class="fw-bold mb-2"><i class="bi bi-file-diff me-1"></i>Generated Atmos stack <span class="nx-mono small nx-muted">${esc(pv.stack_file || "")}</span></div>${UI.diffHtml(pv.diff)}</div></div></div>
      <div class="col-12"><div class="nx-card"><div class="nx-card-body"><div class="fw-bold mb-2"><i class="bi bi-terminal me-1"></i>Validation</div>${UI.validationHtml(pv.validation)}</div></div></div>
    </div>`;
  };

  UI.errorText = (e) => e.message + (e.details && e.details.length ? ": " + e.details.join(" ") : "");

  /* Steps bar */
  UI.steps = function (host, names, current, onGo) {
    host.innerHTML = names.map((s, i) => `<div class="nx-step ${i === current ? "active" : ""} ${i < current ? "done" : ""}" data-go="${i}">
      <span class="n">${i < current ? '<i class="bi bi-check-lg"></i>' : i + 1}</span><span>${esc(s)}</span></div>`).join("");
    UI.$$("[data-go]", host).forEach(n => n.onclick = () => { if (+n.dataset.go < current) onGo(+n.dataset.go); });
  };

  /* Dynamic form from a field schema (M02 resource types). */
  UI.fieldsHtml = function (fields, values) {
    const visible = (f) => {
      if (!f.show_if) return true;
      const [k, want] = Object.entries(f.show_if)[0];
      const def = (fields.find(x => x.name === k) || {}).default;
      const have = values[k] !== undefined ? values[k] : def;
      return want === "*" ? !!have : have === want;
    };
    return fields.filter(visible).map(f => {
      const v = values[f.name] !== undefined ? values[f.name] : f.default;
      const id = "fld-" + f.name, req = f.required ? " *" : "";
      const label = `<label class="form-label small fw-semibold" for="${id}">${esc(f.label)}${req}</label>`;
      const help = f.help ? `<div class="form-text">${esc(f.help)}</div>` : "";
      if (f.type === "choice") {
        const cur = Array.isArray(v) ? v[0] : v;
        return `<div class="col-12">${label}<div class="row g-2">${f.options.map(o => `<div class="col-6 col-md-4 col-xxl-3">
          <div class="nx-choice ${String(cur) === String(o.value) ? "selected" : ""}" data-field="${esc(f.name)}" data-value="${esc(o.value)}" tabindex="0" role="button">
            <div class="d-flex justify-content-between gap-2"><span class="fw-semibold small">${esc(o.label)}</span>${o.badge ? `<span class="nx-badge b-primary">${esc(o.badge)}</span>` : ""}</div>
            ${o.desc ? `<div class="small nx-muted">${esc(o.desc)}</div>` : ""}</div></div>`).join("")}</div>${help}</div>`;
      }
      if (f.type === "bool") {
        return `<div class="col-md-6"><div class="form-check form-switch mt-md-4"><input class="form-check-input" type="checkbox" id="${id}" data-bool="${esc(f.name)}" ${v ? "checked" : ""}>
          <label class="form-check-label small fw-semibold" for="${id}">${esc(f.label)}</label></div>${help}</div>`;
      }
      if (f.type === "multi") {
        const cur = (v || []).map(String);
        return `<div class="col-12">${label}<div class="d-flex flex-wrap gap-2">${f.options.map(o => `<input type="checkbox" class="btn-check" id="${id}-${esc(o.value)}" data-multi="${esc(f.name)}" value="${esc(o.value)}" ${cur.includes(String(o.value)) ? "checked" : ""}>
          <label class="btn btn-sm btn-outline-primary" for="${id}-${esc(o.value)}">${esc(o.label)}</label>`).join("")}</div>${help}</div>`;
      }
      if (f.type === "textarea") {
        return `<div class="col-12">${label}<textarea class="form-control nx-mono" rows="4" id="${id}" data-text="${esc(f.name)}" placeholder="${esc(f.placeholder || "")}">${esc(v || "")}</textarea>${help}</div>`;
      }
      const t = f.type === "number" ? "number" : "text";
      const val = Array.isArray(v) ? v.join(", ") : (v == null ? "" : v);
      return `<div class="col-md-6">${label}<input class="form-control" id="${id}" type="${t}" data-text="${esc(f.name)}" data-kind="${esc(f.type)}"
        value="${esc(val)}" placeholder="${esc(f.placeholder || "")}" ${f.min != null ? `min="${f.min}"` : ""} ${f.max != null ? `max="${f.max}"` : ""}>${help}</div>`;
    }).join("");
  };

  UI.bindFields = function (host, fields, values, redraw) {
    UI.$$("[data-field]", host).forEach(c => {
      const pick = () => {
        const f = fields.find(x => x.name === c.dataset.field);
        const opt = f.options.find(o => String(o.value) === c.dataset.value);
        values[f.name] = opt.value; redraw();
      };
      c.onclick = pick; c.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } };
    });
    UI.$$("[data-bool]", host).forEach(c => c.onchange = () => { values[c.dataset.bool] = c.checked; redraw(); });
    UI.$$("[data-multi]", host).forEach(c => c.onchange = () => {
      const f = fields.find(x => x.name === c.dataset.multi);
      values[f.name] = UI.$$(`[data-multi="${f.name}"]:checked`, host).map(x => f.options.find(o => String(o.value) === x.value).value);
    });
    const drivers = fields.reduce((m, x) => { if (x.show_if) m[Object.keys(x.show_if)[0]] = 1; return m; }, {});
    UI.$$("[data-text]", host).forEach(c => {
      const f = fields.find(x => x.name === c.dataset.text);
      c.oninput = () => {
        values[f.name] = f.type === "number" ? (c.value === "" ? "" : Number(c.value)) : f.type === "list" ? c.value.split(",").map(s => s.trim()).filter(Boolean) : c.value;
      };
      if (drivers[f.name]) c.onchange = () => redraw();  // redraw on blur so typing keeps focus
    });
  };
})();
