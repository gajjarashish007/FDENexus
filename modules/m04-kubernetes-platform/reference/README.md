# Reference: legacy pod dashboard (EKSense)

Copy of `FDENexus/pod/` (stdlib HTTP server + kubectl). Nothing in M04 imports it at runtime.

Ported into M04 (`backend/`, `kubernetes.html`): pod/node/deployment status rules, overview counts,
cluster registry (now in the portal DB), describe, logs, delete pod, rollout restart with
statefulset fallback and rollout wait, Services/Ingress/ConfigMaps/HPA views, failed-pod cleanup
(`pods.sh` logic), pod exec, system-namespace hiding.

Changed on purpose while porting:
- No global `kubectl config use-context`: every call uses its own kubeconfig/context, so users on different clusters cannot interfere.
- All names are validated (DNS-1123) before reaching kubectl; no flag injection.
- One login and role model (portal JWT); the separate users/sessions DB is not used.
- Exec is admin/operator only (admin only in production), always audited with secrets masked, and can be switched off.
- EKS credentials come from each connected AWS account's role (AssumeRole + external ID), not the host's default profile.
- Cleanup uses a normal delete (no `--force --grace-period=0`).

Kept only here (not ported, tenant-specific): `service_versions.py` / `version_cache.py` and the
`data/service_version_*.json` catalog (Arlo/Comcast hostnames), `route53_traffic.py` +
`data/traffic_migration_hosts.json`, `validator_integration.py`, the Android wrappers.

Excluded from the copy: `data/rbac*.db` (password hashes and live session tokens),
`data/auth.defaults`, `data/service_versions.db`, `server.log`, `__pycache__/`.
