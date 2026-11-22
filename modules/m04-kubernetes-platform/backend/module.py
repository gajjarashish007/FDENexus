"""M04 Kubernetes & Container Platform Management: day-2 operations for EKS and other clusters.

Ported from the standalone pod dashboard (pod/), rebuilt on the platform core:
one login and role model, one audit log, per-account AWS credentials, per-cluster kubeconfig.
Creating, resizing and deleting clusters stays in M02/M03 (Terraform); this module operates them.
"""
from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify, request

import k8s_client as kc
import k8s_ops as ko
import k8s_summary as ks

API = "/api/m04"
SECRET_RE = re.compile(r"(?i)((?:password|passwd|token|secret|api[_-]?key)\s*[=:]\s*)(\S+)")
SCHEMA = """
CREATE TABLE IF NOT EXISTS m04_clusters (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL, account_id TEXT, region TEXT,
    context TEXT, tier TEXT NOT NULL DEFAULT 'development', label TEXT, origin TEXT NOT NULL DEFAULT 'manual',
    environment TEXT, last_status TEXT, last_note TEXT, server_version TEXT, last_checked TEXT,
    created_by TEXT, created_at TEXT NOT NULL
);
"""
TIERS = ("sandbox", "development", "staging", "production")


def register(app, ctx):
    store, cfg = ctx.store, ctx.config
    auth, admin, role = ctx.auth_required, ctx.admin_required, ctx.role_required
    data_dir = Path(cfg.DATA_DIR) / "m04"
    with store._LOCK, store._connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    cache: dict = {}
    cache_lock = threading.Lock()

    def now():
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def q(sql, args=(), one=False):
        with store._connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
        return (rows[0] if rows else None) if one else rows

    def x(sql, args=()):
        with store._LOCK, store._connect() as conn:
            conn.execute(sql, args)
            conn.commit()

    def session_factory(account):
        import ec2 as m01_ec2  # M01 helper: AssumeRole (with external ID) or instance role
        return m01_ec2._session(account)

    def err(msg, code=400, **extra):
        return jsonify({"error": msg, **extra}), code

    def audit(action, target, details="", level="info"):
        u = request.current_user
        store.add_audit(u["id"], u["username"], action, target=target, details=details[:500], level=level)

    # ------------------------------------------------------------------ cluster registry
    def sync_m02_clusters():
        """Every EKS cluster defined in an M02 environment shows up here automatically."""
        eng = ctx.services.get("iac")
        if not eng:
            return
        for s in eng.list_stacks():
            for inst, c in s["components"].items():
                if c["component"] != "eks-cluster":
                    continue
                name = f"{s['env']}-{c['vars'].get('cluster_name', '')}"
                cid = f"eks-{s['meta'].get('account_id')}-{name}"[:120]
                if q("SELECT 1 FROM m04_clusters WHERE id=?", (cid,), one=True):
                    continue
                x("INSERT INTO m04_clusters (id,name,source,account_id,region,tier,label,origin,environment,created_by,created_at) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (cid, name, "eks", s["meta"].get("account_id"), s["meta"].get("region"), s["meta"].get("tier", "development"),
                   name, "M02", s["env"], "m02", now()))

    def get_cluster(cid):
        c = q("SELECT * FROM m04_clusters WHERE id=?", (cid,), one=True)
        if not c:
            raise kc.KubeError("Unknown cluster. Register it first.")
        return c

    def target(c):
        if c["source"] == "eks" and not cfg.LIVE_READS:
            raise kc.KubeError("Live reads are off (M01_LIVE_READS=0): EKS clusters are not contacted.")
        acct = store.get_aws_account(c["account_id"]) if c.get("account_id") else None
        return kc.ClusterTarget(c, acct, data_dir, session_factory)

    def cached(c, key, fn, ttl=15, fresh=False):
        k = (c["id"], key)
        with cache_lock:
            hit = cache.get(k)
        if hit and not fresh and time.time() - hit[0] < ttl:
            return hit[1], int(time.time() - hit[0])
        val = fn()
        with cache_lock:
            cache[k] = (time.time(), val)
        return val, 0

    def invalidate(c):
        with cache_lock:
            for k in [k for k in cache if k[0] == c["id"]]:
                cache.pop(k, None)

    def handle(fn):
        try:
            return fn()
        except PermissionError as e:
            return err(str(e), 403)
        except kc.KubeError as e:
            return err(str(e), 502 if "kubectl" in str(e).lower() or "failed" in str(e).lower() else 400)

    def can_mutate(c, u, what):
        r = u["role"]
        if r == "viewer":
            return "Viewers have read-only access."
        if what in ("exec",):
            if not ctx.get_setting("m04.exec_enabled", True):
                return "Pod exec is turned off by an administrator."
            if r not in ("admin", "operator"):
                return "Only admins and operators can run commands in pods."
            if c["tier"] == "production" and r != "admin":
                return "Only admins can run commands in production pods."
        elif what == "cleanup":
            if r not in ("admin", "operator"):
                return "Only admins and operators can run bulk cleanup."
        elif what == "platform":  # RBAC, namespace delete, node drain, node groups, add-ons, upgrades
            if r not in ("admin", "operator"):
                return "Only admins and operators can change cluster-level settings."
            if c["tier"] == "production" and r != "admin":
                return "Only admins can change cluster-level settings in production."
        else:
            if r not in ("admin", "operator", "developer"):
                return "Your role cannot change workloads."
            if r == "developer" and c["tier"] == "production":
                return "Developers cannot change production workloads."
        return None

    @app.route(f"{API}/clusters")
    @auth
    def clusters():
        sync_m02_clusters()
        rows = q("SELECT * FROM m04_clusters ORDER BY tier DESC, name")
        return jsonify({"clusters": rows, "simulated": bool(cfg.DEMO_MODE), "live_reads": bool(cfg.LIVE_READS), "kubectl": kc.KUBECTL,
                        "exec_enabled": bool(ctx.get_setting("m04.exec_enabled", True))}), 200

    @app.route(f"{API}/contexts")
    @admin
    def contexts():
        return jsonify({"contexts": kc.kubeconfig_contexts()}), 200

    @app.route(f"{API}/discover")
    @admin
    def discover():
        acct = store.get_aws_account(request.args.get("account", ""))
        if not acct:
            return err("Unknown AWS account")
        if not cfg.LIVE_READS:
            return jsonify({"clusters": [], "message": "Live reads are off (M01_LIVE_READS=0)."}), 200
        region = request.args.get("region") or acct["region"]
        try:
            names = session_factory(acct).client("eks", region_name=region).list_clusters()["clusters"]
        except Exception as e:
            return err(f"eks:ListClusters failed: {str(e)[:200]}", 502)
        known = {r["name"] for r in q("SELECT name FROM m04_clusters WHERE account_id=?", (acct["id"],))}
        return jsonify({"clusters": [{"name": n, "region": region, "registered": n in known} for n in names]}), 200

    @app.route(f"{API}/clusters", methods=["POST"])
    @admin
    def add_cluster():
        d = request.get_json(silent=True) or {}
        source, tier = d.get("source"), d.get("tier", "development")
        if source not in ("eks", "kubeconfig"):
            return err("Source must be eks or kubeconfig.")
        if tier not in TIERS:
            return err("Pick a tier.")
        name = str(d.get("name", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", name):
            return err("Cluster name: letters, digits, '-' and '_' (EKS naming).")
        if source == "eks":
            acct = store.get_aws_account(str(d.get("account_id", "")))
            if not acct:
                return err("Pick a registered AWS account.")
            region = d.get("region") or acct["region"]
            if not re.fullmatch(r"[a-z]{2}(-[a-z]+)+-\d", str(region)):
                return err("Invalid region.")
            cid, context = f"eks-{acct['id']}-{name}"[:120], None
        else:
            context = str(d.get("context", ""))
            if context not in kc.kubeconfig_contexts():
                return err("That context is not in the portal host's kubeconfig.")
            acct, region, cid = None, None, "ctx-" + re.sub(r"[^a-z0-9-]+", "-", context.lower()).strip("-")[:100]
        if q("SELECT 1 FROM m04_clusters WHERE id=?", (cid,), one=True):
            return err("This cluster is already registered.", 409)
        x("INSERT INTO m04_clusters (id,name,source,account_id,region,context,tier,label,origin,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
          (cid, name, source, acct["id"] if acct else None, region, context, tier, str(d.get("label") or name)[:80], "manual",
           request.current_user["username"], now()))
        audit("k8s_cluster_registered", cid, f"{source} tier={tier}")
        return jsonify({"cluster": get_cluster(cid)}), 201

    @app.route(f"{API}/clusters/<cid>", methods=["DELETE"])
    @admin
    def remove_cluster(cid):
        c = q("SELECT * FROM m04_clusters WHERE id=?", (cid,), one=True)
        if not c:
            return err("Unknown cluster", 404)
        x("DELETE FROM m04_clusters WHERE id=?", (cid,))
        p = data_dir / f"{cid}.kubeconfig"
        if p.exists():
            p.unlink()
        audit("k8s_cluster_removed", cid, "registry only; the cluster itself is untouched", "warn")
        return jsonify({"message": "Removed from the portal. The cluster is not deleted."}), 200

    @app.route(f"{API}/clusters/<cid>/test", methods=["POST"])
    @auth
    def test_cluster(cid):
        def go():
            c = get_cluster(cid)
            try:
                v = target(c).json(["version"], timeout=20).get("serverVersion", {})
                status, note, ver = "connected", f"API server reachable, Kubernetes {v.get('gitVersion', '?')}.", v.get("gitVersion", "")
            except kc.KubeError as e:
                status, note, ver = "failed", str(e), c.get("server_version")
            x("UPDATE m04_clusters SET last_status=?, last_note=?, server_version=?, last_checked=? WHERE id=?", (status, note[:500], ver, now(), cid))
            invalidate(c)
            return jsonify({"cluster": get_cluster(cid)}), 200
        return handle(go)

    # ------------------------------------------------------------------ reads
    def ns_args(ns):
        return ["-n", kc.check_ns(ns)] if ns else ["-A"]

    @app.route(f"{API}/c/<cid>/overview")
    @auth
    def overview(cid):
        def go():
            c = get_cluster(cid)
            t = target(c)
            fresh = request.args.get("refresh") == "1"

            def build():
                with ThreadPoolExecutor(5) as pool:
                    f_ver = pool.submit(t.json, ["version"], 20)
                    f_nodes = pool.submit(t.json, ["get", "nodes"])
                    f_pods = pool.submit(t.json, ["get", "pods", "-A"], 90)
                    f_dep = pool.submit(t.json, ["get", "deployments", "-A"])
                    f_ev = pool.submit(t.json, ["get", "events", "-A", "--field-selector", "type=Warning"])
                nodes = [ks.node_summary(n) for n in f_nodes.result().get("items", [])]
                pods = [ks.pod_summary(p) for p in f_pods.result().get("items", [])]
                deps = [ks.workload_summary(d, "deployments") for d in f_dep.result().get("items", [])]
                evs = sorted((ks.event_summary(e) for e in f_ev.result().get("items", [])), key=lambda e: e["ts"], reverse=True)
                app_pods = [p for p in pods if not p["system"]]
                return {
                    "version": f_ver.result().get("serverVersion", {}).get("gitVersion", ""),
                    "nodes": {"total": len(nodes), "ready": sum(1 for n in nodes if n["status"] == "Ready"),
                              "notReady": [n["name"] for n in nodes if n["status"] != "Ready"],
                              "versions": sorted({n["version"] for n in nodes}), "pressure": [n["name"] for n in nodes if n["pressure"]]},
                    "pods": ks.pod_stats(app_pods), "systemPods": ks.pod_stats([p for p in pods if p["system"]]),
                    "problemPods": [p for p in app_pods if p["statusClass"] == "error" or p["restarts"] >= 5][:25],
                    "deployments": {"total": len([d for d in deps if not d["system"]]),
                                    "degraded": [d for d in deps if not d["healthy"] and not d["system"]][:25]},
                    "namespaces": len({p["namespace"] for p in app_pods}),
                    "warnings": evs[:20], "warningCount": len(evs),
                }
            data, age_s = cached(c, "overview", build, ttl=20, fresh=fresh)
            return jsonify({"overview": data, "cacheAge": age_s, "cluster": c}), 200
        return handle(go)

    @app.route(f"{API}/c/<cid>/list/<kind>")
    @auth
    def list_kind(cid, kind):
        def go():
            if kind not in kc.KINDS or kind == "events":
                raise kc.KubeError("Unsupported kind.")
            c = get_cluster(cid)
            t = target(c)
            ns = request.args.get("namespace", "")
            args = ["get", kc.KINDS[kind]] + ([] if kind in kc.CLUSTER_SCOPED else ns_args(ns))
            data, age_s = cached(c, f"list:{kind}:{ns}", lambda: t.json(args, 90), fresh=request.args.get("refresh") == "1")
            items = data.get("items", [])
            if kind == "pods":
                rows = [ks.pod_summary(p) for p in items]
            elif kind == "nodes":
                rows = [ks.node_summary(n) for n in items]
            elif kind in ("deployments", "statefulsets", "daemonsets"):
                rows = [ks.workload_summary(i, kind) for i in items]
            else:
                rows = [ks.generic_summary(i, kind) for i in items]
            if request.args.get("system") != "1":
                rows = [r for r in rows if not r.get("system")]
            st = request.args.get("status")
            if kind == "pods" and st:
                rows = [r for r in rows if r["statusClass"] == st]
            return jsonify({"items": rows, "cacheAge": age_s, "count": len(rows)}), 200
        return handle(go)

    @app.route(f"{API}/c/<cid>/events")
    @auth
    def events(cid):
        def go():
            c = get_cluster(cid)
            t = target(c)
            ns = request.args.get("namespace", "")
            args = ["get", "events"] + ns_args(ns)
            if request.args.get("warnings") == "1":
                args += ["--field-selector", "type=Warning"]
            obj = request.args.get("object", "")
            if obj:
                args += ["--field-selector", f"involvedObject.name={kc.check_name(obj)}"]
            data, _ = cached(c, "ev:" + " ".join(args), lambda: t.json(args), ttl=10)
            evs = sorted((ks.event_summary(e) for e in data.get("items", [])), key=lambda e: e["ts"], reverse=True)
            if request.args.get("system") != "1":
                evs = [e for e in evs if e["namespace"] not in ks.SYSTEM_NAMESPACES]
            return jsonify({"items": evs[:300]}), 200
        return handle(go)

    def reader_only_guard():
        return request.current_user["role"] == "viewer"

    @app.route(f"{API}/c/<cid>/describe/<kind>/<name>")
    @auth
    def describe(cid, kind, name):
        def go():
            if kind not in kc.DESCRIBE_KINDS:
                raise kc.KubeError("Unsupported kind.")
            if kind == "configmap" and reader_only_guard():
                raise PermissionError("Viewers cannot read ConfigMap contents.")
            c = get_cluster(cid)
            args = ["describe", kind, kc.check_name(name)] + ([] if kind in kc.CLUSTER_SCOPED else ["-n", kc.check_ns(request.args.get("namespace", "default"))])
            return jsonify({"text": target(c).text(args)}), 200
        return handle(go)

    @app.route(f"{API}/c/<cid>/yaml/<kind>/<name>")
    @auth
    def get_yaml(cid, kind, name):
        def go():
            if reader_only_guard():
                raise PermissionError("Viewers cannot read full manifests.")
            if kind not in kc.DESCRIBE_KINDS:
                raise kc.KubeError("Unsupported kind.")
            c = get_cluster(cid)
            args = ["get", kind, kc.check_name(name), "-o", "yaml", "--show-managed-fields=false"] + \
                   ([] if kind in kc.CLUSTER_SCOPED else ["-n", kc.check_ns(request.args.get("namespace", "default"))])
            return jsonify({"text": target(c).text(args)}), 200
        return handle(go)

    @app.route(f"{API}/c/<cid>/logs/<ns>/<pod>")
    @auth
    def logs(cid, ns, pod):
        def go():
            if reader_only_guard():
                raise PermissionError("Viewers cannot read pod logs.")
            c = get_cluster(cid)
            tail = max(10, min(int(request.args.get("tail", 200)), 5000))
            args = ["logs", "-n", kc.check_ns(ns), kc.check_name(pod, "pod"), f"--tail={tail}", "--timestamps"]
            if request.args.get("container"):
                args += ["-c", kc.check_name(request.args["container"], "container")]
            if request.args.get("previous") == "1":
                args.append("--previous")
            if request.args.get("since") in ("5m", "15m", "1h", "6h", "24h"):
                args.append(f"--since={request.args['since']}")
            return jsonify({"text": target(c).text(args, timeout=40)}), 200
        return handle(go)

    @app.route(f"{API}/c/<cid>/diagnose/<ns>/<pod>")
    @auth
    def diagnose(cid, ns, pod):
        def go():
            c = get_cluster(cid)
            t = target(c)
            p = t.json(["get", "pod", kc.check_name(pod, "pod"), "-n", kc.check_ns(ns)])
            ev = t.json(["get", "events", "-n", ns, "--field-selector", f"involvedObject.name={pod}"])
            evs = sorted((ks.event_summary(e) for e in ev.get("items", [])), key=lambda e: e["ts"])
            return jsonify({"pod": ks.pod_summary(p), "hints": ks.diagnose(p, [{**e, "type": e["type"]} for e in ev.get("items", [])]),
                            "events": evs[-30:]}), 200
        return handle(go)

    # ------------------------------------------------------------------ actions (audited)
    def mutate(cid, what, fn):
        def go():
            c = get_cluster(cid)
            if c["source"] == "eks" and cfg.DEMO_MODE:
                return err("Simulation mode (M01_DEMO=1): EKS clusters are read-only. Start with ./start-portal.sh --prod to change workloads.", 403)
            why = can_mutate(c, request.current_user, what)
            if why:
                return err(why, 403)
            res = fn(c, target(c), request.get_json(silent=True) or {})
            invalidate(c)
            return res
        return handle(go)

    @app.route(f"{API}/c/<cid>/pods/<ns>/<pod>/delete", methods=["POST"])
    @auth
    def delete_pod(cid, ns, pod):
        def act(c, t, d):
            out = t.text(["delete", "pod", kc.check_name(pod, "pod"), "-n", kc.check_ns(ns), "--wait=false"])
            audit("k8s_pod_deleted", f"{c['name']}/{ns}/{pod}", "controller will recreate it if owned", "warn")
            return jsonify({"output": out.strip()}), 200
        return mutate(cid, "delete", act)

    @app.route(f"{API}/c/<cid>/restart", methods=["POST"])
    @auth
    def restart(cid):
        def act(c, t, d):
            ns, name = kc.check_ns(d.get("namespace", "")), kc.check_name(d.get("name", ""))
            kinds = [d["kind"]] if d.get("kind") in ("deployment", "statefulset", "daemonset") else ["deployment", "statefulset"]
            last, kind = None, None
            for k in kinds:
                r = t.run(["rollout", "restart", f"{k}/{name}", "-n", ns])
                if r.returncode == 0:
                    kind, last = k, r.stdout.strip()
                    break
                last = r.stderr
            if not kind:
                raise kc.KubeError(kc._clean_err(last))
            status = ""
            if d.get("wait", True):
                secs = max(10, min(int(d.get("timeout", 180)), 600))
                r = t.run(["rollout", "status", f"{kind}/{name}", "-n", ns, f"--timeout={secs}s"], timeout=secs + 10)
                status = (r.stdout + r.stderr).strip()
                ok = r.returncode == 0
            else:
                ok = True
            audit("k8s_rollout_restart", f"{c['name']}/{ns}/{kind}/{name}", "ok" if ok else "rollout not finished", "info" if ok else "warn")
            return jsonify({"kind": kind, "output": last, "status": status, "ok": ok}), 200
        return mutate(cid, "restart", act)

    @app.route(f"{API}/c/<cid>/scale", methods=["POST"])
    @auth
    def scale(cid):
        def act(c, t, d):
            ns, name = kc.check_ns(d.get("namespace", "")), kc.check_name(d.get("name", ""))
            kind = d.get("kind", "deployment")
            if kind not in ("deployment", "statefulset"):
                raise kc.KubeError("Only deployments and statefulsets can be scaled here.")
            try:
                n = int(d.get("replicas"))
            except (TypeError, ValueError):
                raise kc.KubeError("Replicas must be a number.") from None
            if not 0 <= n <= 100:
                raise kc.KubeError("Replicas must be between 0 and 100.")
            if n == 0 and c["tier"] == "production" and request.current_user["role"] != "admin":
                raise PermissionError("Only admins can scale production workloads to zero.")
            out = t.text(["scale", f"{kind}/{name}", "-n", ns, f"--replicas={n}"])
            audit("k8s_scaled", f"{c['name']}/{ns}/{kind}/{name}", f"replicas={n}", "warn" if n == 0 else "info")
            return jsonify({"output": out.strip()}), 200
        return mutate(cid, "scale", act)

    @app.route(f"{API}/c/<cid>/cleanup", methods=["POST"])
    @auth
    def cleanup(cid):
        def act(c, t, d):
            pods = [ks.pod_summary(p) for p in t.json(["get", "pods", "-A"], 90).get("items", [])]
            bad = ks.bad_pods(pods, include_system=bool(d.get("include_system")))[:200]
            if d.get("dry_run", True):
                return jsonify({"dry_run": True, "pods": bad}), 200
            done, failed = [], []
            for p in bad:
                r = t.run(["delete", "pod", p["name"], "-n", p["namespace"], "--wait=false"])
                (done if r.returncode == 0 else failed).append({**p, "error": kc._clean_err(r.stderr) if r.returncode else ""})
            audit("k8s_cleanup", c["name"], f"deleted {len(done)} pods, {len(failed)} failed", "warn")
            return jsonify({"dry_run": False, "deleted": done, "failed": failed}), 200
        return mutate(cid, "cleanup", act)

    @app.route(f"{API}/c/<cid>/exec", methods=["POST"])
    @auth
    def exec_pod(cid):
        def act(c, t, d):
            ns, pod = kc.check_ns(d.get("namespace", "")), kc.check_name(d.get("pod", ""), "pod")
            cmd = str(d.get("command", "")).strip()
            if not cmd or len(cmd) > 4000:
                raise kc.KubeError("Enter a command (up to 4000 characters).")
            secs = max(5, min(int(d.get("timeout", 30)), 120))
            args = ["exec", "-n", ns, pod]
            if d.get("container"):
                args += ["-c", kc.check_name(d["container"], "container")]
            args += ["--", "sh", "-c", cmd]
            r = t.run(args, timeout=secs)
            audit("k8s_exec", f"{c['name']}/{ns}/{pod}", SECRET_RE.sub(r"\1***", cmd), "warn")
            return jsonify({"exit": r.returncode, "stdout": r.stdout[-200000:], "stderr": kc._clean_err(r.stderr) if r.stderr else ""}), 200
        return mutate(cid, "exec", act)

    @app.route(f"{API}/settings", methods=["PUT"])
    @admin
    def settings():
        d = request.get_json(silent=True) or {}
        if "exec_enabled" in d:
            ctx.set_setting("m04.exec_enabled", bool(d["exec_enabled"]))
            audit("m04_settings_updated", "exec_enabled", str(bool(d["exec_enabled"])))
        return jsonify({"exec_enabled": bool(ctx.get_setting("m04.exec_enabled", True))}), 200


    # ================================================================== write operations (manifests)
    def _apply(c, t, docs, dry_run):
        text = ko.to_yaml(docs)
        if dry_run:
            r = t.run(["apply", "-f", "-", "--dry-run=server", "-o", "name"], timeout=60, stdin=text)
            if r.returncode != 0:
                raise kc.KubeError(kc._clean_err(r.stderr or r.stdout))
            d = t.run(["diff", "-f", "-"], timeout=60, stdin=text)  # exit 1 = differences, >1 = error
            diff = d.stdout if d.returncode in (0, 1) else ""
            return {"dry_run": True, "manifest": text, "objects": r.stdout.split(), "diff": diff or ("(no changes)" if d.returncode == 0 else "")}
        r = t.run(["apply", "-f", "-"], timeout=90, stdin=text)
        if r.returncode != 0:
            raise kc.KubeError(kc._clean_err(r.stderr or r.stdout))
        return {"dry_run": False, "manifest": text, "output": r.stdout.strip()}

    @app.route(f"{API}/c/<cid>/apply", methods=["POST"])
    @auth
    def apply_manifest(cid):
        def act(c, t, d):
            u = request.current_user
            if d.get("yaml"):
                docs = ko.parse_yaml(str(d["yaml"]), u["role"] == "admin")
                label = "yaml"
            else:
                docs = ko.build(str(d.get("template", "")), d.get("params") or {})
                label = d["template"]
            kinds = {x["kind"] for x in docs}
            if kinds & {"RoleBinding", "Role", "Namespace", "NetworkPolicy", "ResourceQuota", "LimitRange"}:
                why = can_mutate(c, u, "platform")
                if why:
                    raise PermissionError(why)
            res = _apply(c, t, docs, bool(d.get("dry_run", True)))
            if not res["dry_run"]:
                names = ", ".join(f"{x['kind']}/{x['metadata']['name']}" for x in docs)
                audit("k8s_apply", f"{c['name']}/{','.join(sorted(ko.namespaces_of(docs)))}", f"{label}: {names}"[:480])
            return jsonify(res), 200
        return mutate(cid, "apply", act)

    @app.route(f"{API}/c/<cid>/delete", methods=["POST"])
    @auth
    def delete_object(cid):
        def act(c, t, d):
            kind, name = str(d.get("kind", "")), kc.check_name(d.get("name", ""))
            if kind not in ko.DELETE_KINDS:
                raise kc.KubeError("That kind cannot be deleted here.")
            if kind == "namespace":
                why = can_mutate(c, request.current_user, "platform")
                if why:
                    raise PermissionError(why)
                if name in ko.SYSTEM_NS:
                    raise kc.KubeError("System namespaces cannot be deleted.")
                if str(d.get("confirm", "")) != name:
                    raise kc.KubeError(f"Type the namespace name ({name}) to confirm. Everything in it is deleted.")
                args = ["delete", "namespace", name, "--wait=false"]
            else:
                if kind == "rolebinding":
                    why = can_mutate(c, request.current_user, "platform")
                    if why:
                        raise PermissionError(why)
                args = ["delete", kind, name, "-n", kc.check_ns(d.get("namespace", "")), "--wait=false"]
            out = t.text(args)
            audit("k8s_deleted", f"{c['name']}/{d.get('namespace', '')}/{kind}/{name}", "", "warn")
            return jsonify({"output": out.strip()}), 200
        return mutate(cid, "delete", act)

    @app.route(f"{API}/c/<cid>/rollout", methods=["POST"])
    @auth
    def rollout(cid):
        def act(c, t, d):
            kind = d.get("kind", "deployment")
            if kind not in ("deployment", "statefulset", "daemonset"):
                raise kc.KubeError("Unsupported kind.")
            ns, name = kc.check_ns(d.get("namespace", "")), kc.check_name(d.get("name", ""))
            if d.get("action") == "history":
                return jsonify({"text": t.text(["rollout", "history", f"{kind}/{name}", "-n", ns])}), 200
            if d.get("action") != "undo":
                raise kc.KubeError("Action must be history or undo.")
            args = ["rollout", "undo", f"{kind}/{name}", "-n", ns]
            if d.get("revision") not in (None, ""):
                args.append(f"--to-revision={int(d['revision'])}")
            out = t.text(args)
            audit("k8s_rollback", f"{c['name']}/{ns}/{kind}/{name}", f"revision={d.get('revision') or 'previous'}", "warn")
            return jsonify({"output": out.strip()}), 200
        return mutate(cid, "rollout", act)

    @app.route(f"{API}/c/<cid>/set-image", methods=["POST"])
    @auth
    def set_image(cid):
        def act(c, t, d):
            kind = d.get("kind", "deployment")
            if kind not in ("deployment", "statefulset", "daemonset"):
                raise kc.KubeError("Unsupported kind.")
            ns, name, cont = kc.check_ns(d.get("namespace", "")), kc.check_name(d.get("name", "")), kc.check_name(d.get("container", ""), "container")
            image = str(d.get("image", "")).strip()
            if not ko.IMAGE_RE.match(image):
                raise kc.KubeError("Image must look like registry/repo:tag.")
            out = t.text(["set", "image", f"{kind}/{name}", f"{cont}={image}", "-n", ns])
            audit("k8s_set_image", f"{c['name']}/{ns}/{kind}/{name}", f"{cont}={image}")
            return jsonify({"output": out.strip()}), 200
        return mutate(cid, "set-image", act)

    @app.route(f"{API}/c/<cid>/hpa", methods=["POST"])
    @auth
    def patch_hpa(cid):
        def act(c, t, d):
            ns, name = kc.check_ns(d.get("namespace", "")), kc.check_name(d.get("name", ""))
            lo, hi = int(d.get("min", 1)), int(d.get("max", 1))
            if not 1 <= lo <= hi <= 500:
                raise kc.KubeError("Need 1 <= min <= max <= 500.")
            patch = json.dumps({"spec": {"minReplicas": lo, "maxReplicas": hi}})
            out = t.text(["patch", "hpa", name, "-n", ns, "--type=merge", "-p", patch])
            audit("k8s_hpa_updated", f"{c['name']}/{ns}/{name}", f"min={lo} max={hi}")
            return jsonify({"output": out.strip()}), 200
        return mutate(cid, "hpa", act)

    @app.route(f"{API}/c/<cid>/nodes/<node>/<action>", methods=["POST"])
    @auth
    def node_action(cid, node, action):
        def act(c, t, d):
            why = can_mutate(c, request.current_user, "platform")
            if why:
                raise PermissionError(why)
            n = kc.check_name(node, "node")
            if action == "cordon":
                out = t.text(["cordon", n])
            elif action == "uncordon":
                out = t.text(["uncordon", n])
            elif action == "drain":
                secs = max(30, min(int(d.get("timeout", 300)), 900))
                r = t.run(["drain", n, "--ignore-daemonsets", "--delete-emptydir-data", f"--timeout={secs}s"], timeout=secs + 15)
                if r.returncode != 0:
                    raise kc.KubeError("Drain stopped (a PodDisruptionBudget or timeout may block it; the node stays cordoned): " + kc._clean_err(r.stderr or r.stdout))
                out = r.stdout
            else:
                raise kc.KubeError("Action must be cordon, uncordon or drain.")
            audit(f"k8s_node_{action}", f"{c['name']}/{n}", "", "warn" if action == "drain" else "info")
            return jsonify({"output": out.strip()[-4000:]}), 200
        return mutate(cid, "node", act)

    # ================================================================== EKS control plane, node groups, add-ons, upgrades
    def eks_client(c):
        if c["source"] != "eks":
            raise kc.KubeError("This is a kubeconfig cluster; control-plane details are only available for EKS.")
        if not cfg.LIVE_READS:
            raise kc.KubeError("Live reads are off (M01_LIVE_READS=0).")
        acct = store.get_aws_account(c["account_id"])
        if not acct:
            raise kc.KubeError("The cluster's AWS account is not registered.")
        return session_factory(acct).client("eks", region_name=c["region"])

    def m02_instance(c):
        """(stack, instance) for clusters created through M02, else (None, None)."""
        eng = ctx.services.get("iac")
        if c.get("origin") != "M02" or not eng:
            return None, None
        stack = eng.get_stack(c.get("environment") or "")
        for inst, comp in ((stack or {}).get("components") or {}).items():
            if comp["component"] == "eks-cluster" and f"{stack['env']}-{comp['vars'].get('cluster_name')}" == c["name"]:
                return stack, inst
        return None, None

    def next_minor(v):
        try:
            a, b = str(v).split(".")[:2]
            return f"{a}.{int(b) + 1}"
        except ValueError:
            return None

    @app.route(f"{API}/c/<cid>/eks")
    @auth
    def eks_details(cid):
        def go():
            c = get_cluster(cid)
            eks = eks_client(c)
            try:
                d = eks.describe_cluster(name=c["name"])["cluster"]
            except Exception as e:
                raise kc.KubeError(f"eks:DescribeCluster failed: {str(e)[:200]}") from None
            ver = d.get("version")
            ngs, addons, errors = [], [], {}

            def safe_list(fn, key):
                try:
                    return fn(clusterName=c["name"]).get(key, [])
                except Exception as e:
                    errors[key] = str(e)[:200]
                    return []
            for n in safe_list(eks.list_nodegroups, "nodegroups"):
                try:
                    g = eks.describe_nodegroup(clusterName=c["name"], nodegroupName=n)["nodegroup"]
                    ngs.append({"name": n, "status": g.get("status"), "version": g.get("version"), "release": g.get("releaseVersion"),
                                "instance_types": g.get("instanceTypes", []), "capacity": g.get("capacityType"), "ami": g.get("amiType"),
                                "scaling": g.get("scalingConfig", {}), "health": [i.get("message") for i in (g.get("health") or {}).get("issues", [])]})
                except Exception as e:
                    ngs.append({"name": n, "status": "?", "error": str(e)[:160]})
            for a in safe_list(eks.list_addons, "addons"):
                try:
                    x = eks.describe_addon(clusterName=c["name"], addonName=a)["addon"]
                    latest = None
                    try:
                        vs = eks.describe_addon_versions(addonName=a, kubernetesVersion=ver)["addons"][0]["addonVersions"]
                        latest = next((v["addonVersion"] for v in vs if any(cc.get("defaultVersion") for cc in v.get("compatibilities", []))), vs[0]["addonVersion"] if vs else None)
                    except Exception:
                        pass
                    addons.append({"name": a, "version": x.get("addonVersion"), "status": x.get("status"), "latest": latest,
                                   "update_available": bool(latest and latest != x.get("addonVersion"))})
                except Exception as e:
                    addons.append({"name": a, "status": "?", "error": str(e)[:160]})
            insights = []
            try:
                for i in eks.list_insights(clusterName=c["name"]).get("insights", []):
                    insights.append({"name": i.get("name"), "category": i.get("category"), "status": (i.get("insightStatus") or {}).get("status"),
                                     "reason": (i.get("insightStatus") or {}).get("reason", ""), "kubernetes_version": i.get("kubernetesVersion")})
            except Exception as e:
                insights = [{"name": "Upgrade insights unavailable", "status": "UNKNOWN", "reason": str(e)[:160]}]
            stack, inst = m02_instance(c)
            return jsonify({"cluster": {"name": d["name"], "version": ver, "platform": d.get("platformVersion"), "status": d.get("status"),
                                        "endpoint_public": d.get("resourcesVpcConfig", {}).get("endpointPublicAccess"),
                                        "vpc": d.get("resourcesVpcConfig", {}).get("vpcId"), "created": str(d.get("createdAt", ""))[:19],
                                        "auth_mode": (d.get("accessConfig") or {}).get("authenticationMode"),
                                        "upgrade_policy": (d.get("upgradePolicy") or {}).get("supportType")},
                            "nodegroups": ngs, "addons": addons, "insights": insights, "next_version": next_minor(ver), "errors": errors,
                            "managed_by": "terraform" if inst else "direct", "environment": c.get("environment"), "instance": inst}), 200
        return handle(go)

    def platform_guard(c):
        why = can_mutate(c, request.current_user, "platform")
        if why:
            raise PermissionError(why)

    def propose_tf(c, stack, inst, new_vars, title):
        eng = ctx.services["iac"]
        cur = dict(stack["components"][inst]["vars"])
        for k in ("owner", "request_id"):
            cur.pop(k, None)
        cur.update(new_vars)
        return eng.propose(stack["env"], stack["meta"], {inst: {"component": "eks-cluster", "vars": cur}}, "update", title,
                           request.current_user, "M04")

    def eks_change(c, label, fn, tf_vars=None, tf_title=None):
        """M02 clusters change through a reviewed Terraform change; others through the EKS API (live mode only)."""
        platform_guard(c)
        stack, inst = m02_instance(c)
        if inst and tf_vars is not None:
            ch = propose_tf(c, stack, inst, tf_vars, tf_title)
            audit(f"k8s_{label}_proposed", f"{c['name']}", ch["id"])
            return jsonify({"via": "terraform", "change": {"id": ch["id"], "status": ch["status"]}}), 201
        if cfg.DEMO_MODE:
            raise PermissionError("Simulation mode (M01_DEMO=1): EKS changes are disabled. Start with ./start-portal.sh --prod.")
        try:
            out = fn(eks_client(c))
        except kc.KubeError:
            raise
        except Exception as e:
            raise kc.KubeError(f"EKS API error: {str(e)[:240]}") from None
        audit(f"k8s_{label}", c["name"], json.dumps(out, default=str)[:300], "warn")
        return jsonify({"via": "eks-api", "update": out}), 200

    @app.route(f"{API}/c/<cid>/nodegroups/<ng>/scale", methods=["POST"])
    @auth
    def nodegroup_scale(cid, ng):
        def go():
            c = get_cluster(cid)
            d = request.get_json(silent=True) or {}
            lo, want, hi = int(d.get("min", 1)), int(d.get("desired", 1)), int(d.get("max", 1))
            if not 0 <= lo <= want <= hi <= 200 or hi < 1:
                raise kc.KubeError("Need 0 <= min <= desired <= max <= 200.")
            if c["tier"] == "production" and lo < 2:
                raise kc.KubeError("Production node groups need at least 2 nodes.")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}", ng):
                raise kc.KubeError("Invalid node group name.")
            name = ng
            return eks_change(c, "nodegroup_scaled",
                              lambda eks: eks.update_nodegroup_config(clusterName=c["name"], nodegroupName=name,
                                                                      scalingConfig={"minSize": lo, "desiredSize": want, "maxSize": hi})["update"],
                              {"node_min": lo, "node_desired": want, "node_max": hi}, f"Scale node group of {c['name']} to {lo}/{want}/{hi}")
        return handle(go)

    @app.route(f"{API}/c/<cid>/upgrade", methods=["POST"])
    @auth
    def cluster_upgrade(cid):
        def go():
            c = get_cluster(cid)
            if request.current_user["role"] != "admin":
                raise PermissionError("Only admins can upgrade Kubernetes versions.")
            target = str((request.get_json(silent=True) or {}).get("version", ""))
            if not re.fullmatch(r"1\.\d{2}", target):
                raise kc.KubeError("Version must look like 1.37.")
            stack, inst = m02_instance(c)
            if inst:  # Terraform-managed: the stack is the source of truth
                cur = str(stack["components"][inst]["vars"].get("cluster_version", ""))
            elif c["source"] == "eks":
                try:
                    cur = eks_client(c).describe_cluster(name=c["name"])["cluster"]["version"]
                except kc.KubeError:
                    raise
                except Exception as e:
                    raise kc.KubeError(f"eks:DescribeCluster failed: {str(e)[:200]}") from None
            else:
                raise kc.KubeError("Version upgrades are only managed here for EKS clusters.")
            if cur and target != next_minor(cur):
                raise kc.KubeError(f"EKS upgrades one minor version at a time: {cur} -> {next_minor(cur)}.")
            return eks_change(c, "control_plane_upgrade",
                              lambda eks: eks.update_cluster_version(name=c["name"], version=target)["update"],
                              {"cluster_version": target}, f"Upgrade {c['name']} control plane to {target}")
        return handle(go)

    @app.route(f"{API}/c/<cid>/nodegroups/<ng>/upgrade", methods=["POST"])
    @auth
    def nodegroup_upgrade(cid, ng):
        def go():
            c = get_cluster(cid)
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}", ng):
                raise kc.KubeError("Invalid node group name.")
            return eks_change(c, "nodegroup_upgrade",
                              lambda eks: eks.update_nodegroup_version(clusterName=c["name"], nodegroupName=ng)["update"])
        return handle(go)

    @app.route(f"{API}/c/<cid>/addons/<addon>/update", methods=["POST"])
    @auth
    def addon_update(cid, addon):
        def go():
            c = get_cluster(cid)
            if not re.fullmatch(r"[a-z0-9-]{1,60}", addon):
                raise kc.KubeError("Invalid add-on.")
            ver = str((request.get_json(silent=True) or {}).get("version", ""))
            if not re.fullmatch(r"v[0-9][0-9A-Za-z.+_-]{1,60}", ver):
                raise kc.KubeError("Invalid add-on version.")
            return eks_change(c, "addon_updated",
                              lambda eks: eks.update_addon(clusterName=c["name"], addonName=addon, addonVersion=ver, resolveConflicts="PRESERVE")["update"])
        return handle(go)

    @app.route(f"{API}/c/<cid>/decommission", methods=["POST"])
    @auth
    def cluster_decommission(cid):
        """Delete a cluster: M02 clusters through a reviewed Terraform destroy; others are only unregistered."""
        def go():
            c = get_cluster(cid)
            platform_guard(c)
            stack, inst = m02_instance(c)
            if not inst:
                raise kc.KubeError("This cluster was not created by the portal. Remove it from the portal (admin) or delete it with its own tooling.")
            ch = ctx.services["iac"].propose(stack["env"], stack["meta"], {inst: None}, "destroy", f"Delete EKS cluster {c['name']}",
                                             request.current_user, "M04")
            audit("k8s_cluster_delete_proposed", c["name"], ch["id"], "warn")
            return jsonify({"change": {"id": ch["id"], "status": ch["status"]}}), 201
        return handle(go)
