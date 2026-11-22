/* FDE Nexus: EC2 instance list and lifecycle actions (M01 backend). Launching is done in launch.html (Terraform via M03). */
(function () {
  "use strict";
  const NX = window.NEXUS, esc = NX.esc;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => [...(r || document).querySelectorAll(s)];

  const state = { simulated: true, instances: [], timer: null };

  /* ---------------- list ---------------- */
  const STATE_TONE = { running: "success", stopped: "secondary", pending: "warning", stopping: "warning", "shutting-down": "warning", terminated: "danger" };
  async function loadList() {
    const body = $("#ec2-body");
    if (!NX.activeAccount.get()) { body.innerHTML = `<tr><td colspan="9"><div class="nx-empty"><i class="bi bi-cloud-plus"></i>Connect an AWS account first (AWS Accounts page).</div></td></tr>`; return; }
    try {
      const r = await NX.api.get("/api/ec2/instances?account=" + encodeURIComponent(NX.activeAccount.getId()));
      state.instances = r.instances || []; state.simulated = !!r.simulated; modeBadge(); renderList();
    } catch (e) { body.innerHTML = `<tr><td colspan="9"><div class="nx-empty"><i class="bi bi-exclamation-triangle"></i>${esc(e.message)}</div></td></tr>`; }
  }
  function renderList() {
    const q = $("#ec2-search").value.trim().toLowerCase(), st = $("#ec2-state").value;
    const list = state.instances.filter(i => (!q || (i.name + i.instanceId + i.publicIp + i.privateIp).toLowerCase().includes(q)) && (!st || i.state === st));
    const canTerm = ["admin", "operator"].includes((NX.session.get() || {}).role), viewer = (NX.session.get() || {}).role === "viewer";
    $("#ec2-body").innerHTML = list.length ? list.map(i => {
      const dead = i.state === "terminated", can = i.managed && !dead && !viewer;
      const btn = (a, icon, title, cls) => `<button class="btn btn-sm btn-outline-${cls}" data-act="${a}" data-id="${esc(i.instanceId)}" title="${title}" ${can ? "" : "disabled"}><i class="bi bi-${icon}"></i></button>`;
      return `<tr><td>${esc(i.name || "-")}${i.managed ? "" : '<div class="small nx-muted">not managed by FDE Nexus</div>'}</td>
        <td class="nx-mono small">${esc(i.instanceId)}</td>
        <td><span class="nx-badge b-${STATE_TONE[i.state] || "secondary"}"><span class="nx-state-dot" style="background:currentColor"></span>${esc(i.state)}</span></td>
        <td>${esc(i.instanceType)}</td><td class="small">${esc(i.os)}</td><td class="nx-mono small">${esc(i.publicIp || "-")}</td>
        <td class="small">${esc(i.environment)}</td><td class="small nx-muted">${esc(i.launchTime)}</td>
        <td class="text-end" style="white-space:nowrap">${btn("start", "play-fill", "Start", "success")} ${btn("stop", "stop-fill", "Stop", "secondary")} ${btn("reboot", "arrow-repeat", "Reboot", "primary")}
          ${canTerm ? btn("terminate", "trash", "Terminate", "danger") : ""}</td></tr>`;
    }).join("") : `<tr><td colspan="9"><div class="nx-empty"><i class="bi bi-server"></i>${state.instances.length ? "No instances match." : "No instances yet. Use “Launch instance”."}</div></td></tr>`;
    $$("[data-act]").forEach(b => b.onclick = () => doAction(b.dataset.id, b.dataset.act));
  }
  async function doAction(id, act) {
    if (act === "terminate" && !window.confirm(`Terminate ${id}? This cannot be undone.`)) return;
    if (act === "stop" && !window.confirm(`Stop ${id}?`)) return;
    try {
      const r = await NX.api.post(`/api/ec2/instances/${encodeURIComponent(id)}/${act}?account=${encodeURIComponent(NX.activeAccount.getId())}`);
      NX.toast(`${id}: ${r.state}`, "success"); loadList();
    } catch (e) { NX.toast(e.message, "danger"); }
  }

  /* ---------------- shell ---------------- */
  function modeBadge() {
    const a = NX.activeAccount.get();
    $("#ec2-mode").innerHTML = `${a ? `<span class="nx-badge b-primary"><i class="bi bi-cloud"></i>${esc(a.alias)} · ${esc(a.region)}</span>` : '<a class="btn btn-sm btn-warning" href="aws-accounts.html">Connect an AWS account</a>'}
      <span class="nx-badge b-${state.simulated ? "warning" : "success"} ms-2">${state.simulated ? "Live data · changes simulated" : "Live AWS"}</span>`;
  }


  async function init() {
    if (!$("#ec2-body")) return;
    await NX.loadAccounts();
    try { const h = await NX.api.health(); state.simulated = !!h.demo; } catch (e) { /* shown by list */ }
    modeBadge();
    $("#ec2-search").oninput = renderList; $("#ec2-state").onchange = renderList; $("#ec2-refresh").onclick = loadList;
    document.addEventListener("nx-account-changed", () => { modeBadge(); loadList(); });
    state.timer = setInterval(loadList, 15000);
    loadList();
  }
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
})();
