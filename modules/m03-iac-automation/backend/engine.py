"""M03 IaC engine: turns requested infrastructure into reviewed Atmos/Terraform changes.

Lifecycle of a change
  propose ──► blocked            (a deny policy failed; fix inputs and resubmit)
          ├─► pending_approval   (production, destroy, warnings, or auto-approve off)
          └─► approved (auto)    (low-risk non-production create/update)
  approved ─► queued             (another merge request for the same environment is open)
          ├─► mr_open ─► merged ─► applied     (GitLab configured: CI runs atmos)
          │          └─► closed (stack rolled back to the previous version)
          └─► committed ─► applied             (no GitLab: files written locally)
  pending_approval ─► rejected | cancelled ; approve may also end in "conflict".

The environment stack (stacks/deploy/<tier>/<env>.yaml) is rendered from the DB model, so
the YAML in Git is always generated, reviewable and reproducible.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import yaml

import cost as cost_mod
import gitlab as gitlab_mod
import policy as policy_mod

MODULE_DIR = Path(__file__).resolve().parents[1]
IAC_DIR = Path(os.environ.get("M03_IAC_DIR", MODULE_DIR / "iac"))
COMPONENTS_DIR = IAC_DIR / "components" / "terraform"
ATMOS = shutil.which("atmos")
TERRAFORM = shutil.which("terraform")
SINGLETONS = {"vpc", "account-baseline"}
SHARED_VARS = {"region", "assume_role_arn", "external_id", "environment_id", "tier", "team", "extra_tags"}
ENGINE_VARS = {"owner", "request_id"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
DESTROY_ORDER = ["eks-cluster", "alb", "ec2-instance", "efs", "dynamodb-table", "s3-static-website", "s3-bucket",
                 "acm-certificate", "route53-zone", "vpc", "account-baseline", "aws-account"]
_PUBLISH_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS iac_stacks (
    env TEXT PRIMARY KEY, meta TEXT NOT NULL, components TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS iac_stack_versions (
    env TEXT NOT NULL, version INTEGER NOT NULL, components TEXT NOT NULL,
    change_id TEXT, created_at TEXT NOT NULL, PRIMARY KEY (env, version)
);
CREATE TABLE IF NOT EXISTS iac_changes (
    id TEXT PRIMARY KEY, env TEXT NOT NULL, action TEXT NOT NULL, title TEXT NOT NULL,
    delta TEXT NOT NULL, base_version INTEGER NOT NULL, proposed_yaml TEXT, diff TEXT,
    policy TEXT, cost TEXT, validation TEXT, risk TEXT, status TEXT NOT NULL,
    requester_id INTEGER, requester TEXT, approver TEXT, reason TEXT, decided_at TEXT,
    mr TEXT, source_module TEXT, applied_at TEXT, log TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""


class ChangeError(Exception):
    def __init__(self, msg, details=None, status=400):
        super().__init__(msg)
        self.details = details or []
        self.status = status


class Engine:
    def __init__(self, ctx):
        self.ctx = ctx
        self.store = ctx.store
        with self.store._LOCK, self.store._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()
        self._registry = None

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _now():
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def _q(self, sql, args=(), one=False):
        with self.store._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        rows = [dict(r) for r in rows]
        return (rows[0] if rows else None) if one else rows

    def _x(self, sql, args=()):
        with self.store._LOCK, self.store._connect() as conn:
            conn.execute(sql, args)
            conn.commit()

    @property
    def simulated(self) -> bool:
        return bool(self.ctx.config.DEMO_MODE)

    def settings(self) -> dict:
        g = self.ctx.get_setting("m03.gitlab", {}) or {}
        return {
            "auto_approve_nonprod": bool(self.ctx.get_setting("m03.auto_approve_nonprod", True)),
            "gitlab": {"url": g.get("url", ""), "project": g.get("project", ""),
                       "target_branch": g.get("target_branch", "main"), "path_prefix": g.get("path_prefix", ""),
                       "token_present": gitlab_mod.token_present()},
            "state_bucket_pattern": self.ctx.get_setting("m03.state_bucket_pattern", "fde-nexus-tfstate-{account_id}"),
            "portal_apply": os.environ.get("M03_PORTAL_APPLY") == "1",
            "tools": {"atmos": bool(ATMOS), "terraform": bool(TERRAFORM),
                      "checkov": bool(shutil.which("checkov")), "trivy": bool(shutil.which("trivy"))},
            "iac_dir": str(IAC_DIR), "simulated": self.simulated,
        }

    def gitlab_client(self):
        g = self.settings()["gitlab"]
        if not g["url"] or not g["project"]:
            return None
        return gitlab_mod.GitLab(g["url"], g["project"])

    # ------------------------------------------------------------------ registry
    def registry(self) -> dict:
        if self._registry is None:
            meta = json.loads((IAC_DIR / "components" / "registry.json").read_text())
            out = {}
            for name, info in meta.items():
                d = COMPONENTS_DIR / name
                if not d.is_dir():
                    continue
                variables = {}
                for tf in sorted(d.glob("*.tf")):
                    variables.update(_parse_variables(tf.read_text(), shared=(tf.name == "context.tf")))
                outputs = re.findall(r'^output\s+"([^"]+)"', (d / "outputs.tf").read_text(), re.M) if (d / "outputs.tf").exists() else []
                out[name] = {**info, "name": name, "variables": variables, "outputs": outputs,
                             "files": sorted(p.name for p in d.glob("*.tf"))}
            self._registry = out
        return self._registry

    def component_source(self, name: str) -> dict:
        if name not in self.registry():
            raise ChangeError("Unknown component", status=404)
        d = COMPONENTS_DIR / name
        return {p.name: p.read_text() for p in sorted(d.glob("*.tf"))}

    def _check_vars(self, component: str, v: dict) -> tuple[dict, list[str]]:
        reg = self.registry().get(component)
        if not reg:
            return v, [f"Unknown component {component}."]
        if reg["status"] == "deprecated":
            return v, [f"{component} is deprecated{': use ' + reg['replaced_by'] if reg.get('replaced_by') else ''}."]
        errs, clean = [], {}
        defs = {k: d for k, d in reg["variables"].items() if not d["shared"]}
        for key, val in v.items():
            if key in SHARED_VARS or key in ENGINE_VARS:
                continue
            d = defs.get(key)
            if not d:
                errs.append(f"Unknown input '{key}' for {component}.")
                continue
            ok, cv = _coerce(d["type"], val)
            if not ok:
                errs.append(f"'{key}' must be {d['type']}.")
            else:
                clean[key] = cv
        for key, d in defs.items():
            if d["required"] and key not in clean and key not in ENGINE_VARS:
                errs.append(f"'{key}' is required for {component}.")
        return clean, errs

    @staticmethod
    def estimate(component: str, v: dict) -> dict:
        return cost_mod.estimate(component, v)

    # ------------------------------------------------------------------ stacks
    def ensure_stack(self, env: str, meta: dict) -> dict:
        s = self.get_stack(env)
        if s:
            return s
        meta = dict(meta)
        meta.setdefault("state_bucket", self.settings()["state_bucket_pattern"].format(account_id=meta.get("account_id", "unknown")))
        meta.setdefault("state_region", meta.get("region"))
        self._x("INSERT INTO iac_stacks (env,meta,components,version,updated_at) VALUES (?,?,?,?,?)",
                (env, json.dumps(meta), "{}", 0, self._now()))
        return self.get_stack(env)

    def get_stack(self, env: str):
        r = self._q("SELECT * FROM iac_stacks WHERE env=?", (env,), one=True)
        if not r:
            return None
        r["meta"] = json.loads(r["meta"])
        r["components"] = json.loads(r["components"])
        return r

    def list_stacks(self) -> list[dict]:
        out = []
        for r in self._q("SELECT * FROM iac_stacks ORDER BY env"):
            r["meta"] = json.loads(r["meta"])
            r["components"] = json.loads(r["components"])
            out.append(r)
        return out

    def stack_versions(self, env: str) -> list[dict]:
        rows = self._q("SELECT env,version,change_id,created_at,components FROM iac_stack_versions WHERE env=? ORDER BY version DESC", (env,))
        for r in rows:
            r["components"] = sorted(json.loads(r["components"]).keys())
        return rows

    @staticmethod
    def stack_path(meta: dict, env: str) -> str:
        return f"stacks/deploy/{meta['tier']}/{env}.yaml"

    def render(self, env: str, meta: dict, components: dict) -> str:
        used = sorted({c["component"] for c in components.values()})
        top = {k: meta[k] for k in ("region", "tier", "team") if meta.get(k)}
        for k in ("assume_role_arn", "external_id"):
            if meta.get(k):
                top[k] = meta[k]
        doc = {
            "import": ["mixins/backend"] + [f"catalog/{c}" for c in used],
            "vars": {"stage": env, "environment_id": env, **top},
            "terraform": {"backend": {"s3": {"bucket": meta["state_bucket"], "region": meta.get("state_region") or meta["region"]}}},
            "components": {"terraform": {
                inst: {"metadata": {"type": "real", "component": c["component"], "inherits": [f"{c['component']}/defaults"]},
                       "vars": c["vars"]}
                for inst, c in sorted(components.items())}},
        }
        head = (f"# Managed by FDE Nexus M03. Generated from the portal; do not edit by hand.\n"
                f"# Environment {env} · account {meta.get('account_id', '-')} · {meta['tier']}\n")
        return head + yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)

    # ------------------------------------------------------------------ validation
    def atmos_validate(self, env: str, meta: dict, components: dict, instances: list[str]) -> dict:
        if not ATMOS:
            return {"ok": None, "tool": "atmos", "output": "atmos is not installed on the portal host; skipped."}
        with tempfile.TemporaryDirectory(prefix="fde-atmos-") as tmp:
            t = Path(tmp)
            shutil.copy(IAC_DIR / "atmos.yaml", t / "atmos.yaml")
            shutil.copytree(IAC_DIR / "stacks" / "catalog", t / "stacks" / "catalog")
            shutil.copytree(IAC_DIR / "stacks" / "mixins", t / "stacks" / "mixins")
            (t / "components").symlink_to(IAC_DIR / "components")
            p = t / self.stack_path(meta, env)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(self.render(env, meta, components))
            base = ["--base-path", str(t), "--config", str(t / "atmos.yaml")]
            out, ok = [], True
            r = _run([ATMOS, "validate", "stacks", *base], t)
            out.append("$ atmos validate stacks\n" + r["output"].strip())
            ok = ok and r["code"] == 0
            for inst in instances:
                r = _run([ATMOS, "describe", "component", inst, "-s", env, "--format", "json", *base], t)
                if r["code"] == 0:
                    try:
                        d = json.loads(r["stdout"])
                        out.append(f"$ atmos describe component {inst} -s {env}\n  component={d.get('component')} "
                                   f"vars={len(d.get('vars', {}))} backend={d.get('backend_type')}")
                    except ValueError:
                        out.append(f"$ atmos describe component {inst}: unreadable output")
                        ok = False
                else:
                    ok = False
                    out.append(f"$ atmos describe component {inst} -s {env}\n" + r["output"].strip()[-800:])
            return {"ok": ok, "tool": "atmos", "output": "\n".join(out)}

    def security_scan(self, components: list[str]) -> dict:
        """Run an external IaC scanner over the touched components when one is installed."""
        for tool, args in (("checkov", ["--quiet", "--compact", "--framework", "terraform", "-d"]),
                           ("trivy", ["config", "--quiet", "--severity", "HIGH,CRITICAL"])):
            exe = shutil.which(tool)
            if not exe:
                continue
            outs, ok = [], True
            for c in sorted(set(components)):
                r = _run([exe, *args, str(COMPONENTS_DIR / c)], IAC_DIR, timeout=300)
                ok = ok and r["code"] == 0
                outs.append(f"[{c}] " + r["output"].strip()[-1500:])
            return {"ok": ok, "tool": tool, "output": "\n".join(outs)}
        return {"ok": None, "tool": None,
                "output": "No external scanner installed (checkov or trivy). Built-in policy rules still ran."}

    # ------------------------------------------------------------------ propose
    def propose(self, env: str, meta: dict, delta: dict, action: str, title: str, user: dict,
                source_module: str = "M03", dry_run: bool = False) -> dict:
        """delta: {instance: {"component": c, "vars": {...}} | None (destroy)}."""
        if dry_run:
            stack = self.get_stack(env) or {"meta": {**meta, "state_bucket": self.settings()["state_bucket_pattern"].format(
                account_id=meta.get("account_id", "unknown")), "state_region": meta.get("region")}, "components": {}, "version": 0}
        else:
            stack = self.ensure_stack(env, meta)
        meta = stack["meta"]
        current = stack["components"]
        cid = "CHG-" + secrets.token_hex(3)
        errors, clean_delta = [], {}
        for inst, spec in delta.items():
            if spec is None:
                if inst not in current:
                    errors.append(f"{inst} does not exist in {env}.")
                clean_delta[inst] = None
                continue
            comp = spec["component"]
            short = inst.split("/", 1)[-1]
            if comp not in SINGLETONS and not NAME_RE.match(short):
                errors.append(f"Name '{short}' must be 1-40 chars: lowercase letters, digits, hyphens.")
            v, errs = self._check_vars(comp, spec.get("vars", {}))
            errors += errs
            v["owner"] = user["username"]
            v["request_id"] = cid
            clean_delta[inst] = {"component": comp, "vars": v}
        if errors:
            raise ChangeError("Validation failed", errors)

        proposed = _apply_delta(current, clean_delta)
        account_cidrs = {s["env"]: c["vars"]["cidr"] for s in self.list_stacks() if s["env"] != env
                         and s["meta"].get("account_id") == meta.get("account_id")
                         for c in s["components"].values() if c["component"] == "vpc" and c["vars"].get("cidr")}
        pctx = {"tier": meta["tier"], "team": meta.get("team", ""), "account_cidrs": account_cidrs}
        pol = {"passed": True, "warnings": 0, "denies": 0, "findings": [], "rules_evaluated": len(policy_mod.RULES)}
        costs = {"monthly": 0.0, "items": [], "notes": []}
        for inst, spec in clean_delta.items():
            if spec is None:
                old = current[inst]
                est = cost_mod.estimate(old["component"], old["vars"])
                costs["items"].append({"item": f"remove {inst}", "monthly": -est["monthly"]})
                costs["monthly"] -= est["monthly"]
                continue
            r = policy_mod.evaluate(spec["component"], spec["vars"], pctx)
            for f in r["findings"]:
                f["instance"] = inst
            pol["findings"] += r["findings"]
            est = cost_mod.estimate(spec["component"], spec["vars"])
            if inst in current:  # update: show the difference
                prev = cost_mod.estimate(current[inst]["component"], current[inst]["vars"])["monthly"]
                costs["items"].append({"item": f"{inst} (change)", "monthly": round(est["monthly"] - prev, 2)})
                costs["monthly"] += est["monthly"] - prev
            else:
                costs["items"] += [{**i, "item": f"{inst}: {i['item']}"} for i in est["items"]]
                costs["monthly"] += est["monthly"]
            costs["notes"] += [f"{inst}: {n}" for n in est["notes"]]
        pol["denies"] = sum(1 for f in pol["findings"] if f["severity"] == "deny")
        pol["warnings"] = sum(1 for f in pol["findings"] if f["severity"] == "warn")
        pol["passed"] = pol["denies"] == 0
        costs["monthly"] = round(costs["monthly"], 2)

        old_yaml = self.render(env, meta, current) if current else ""
        new_yaml = self.render(env, meta, proposed)
        diff = "".join(difflib.unified_diff(old_yaml.splitlines(True), new_yaml.splitlines(True),
                                            fromfile=f"a/{self.stack_path(meta, env)}", tofile=f"b/{self.stack_path(meta, env)}"))
        touched = [i for i, s in clean_delta.items() if s is not None]
        validation = {"atmos": self.atmos_validate(env, meta, proposed, touched) if proposed else
                      {"ok": True, "tool": "atmos", "output": "Stack becomes empty; nothing to validate."},
                      "scan": self.security_scan([s["component"] for s in clean_delta.values() if s])}

        destroying = any(s is None for s in clean_delta.values())
        if meta["tier"] == "production" or destroying or pol["warnings"]:
            risk = "high"
        elif meta["tier"] == "staging" or any((s or {}).get("component") in ("eks-cluster", "aws-account") for s in clean_delta.values()):
            risk = "medium"
        else:
            risk = "low"
        if not pol["passed"] or validation["atmos"]["ok"] is False:
            status = "blocked"
        elif risk == "low" and action in ("create", "update", "create-environment") and self.settings()["auto_approve_nonprod"]:
            status = "approved"
        else:
            status = "pending_approval"
        if dry_run:
            return {"env": env, "action": action, "risk": risk, "status": status, "policy": pol, "cost": costs,
                    "validation": validation, "diff": diff, "proposed_yaml": new_yaml,
                    "stack_file": self.stack_path(meta, env)}
        now = self._now()
        self._x("INSERT INTO iac_changes (id,env,action,title,delta,base_version,proposed_yaml,diff,policy,cost,validation,"
                "risk,status,requester_id,requester,approver,decided_at,source_module,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, env, action, title[:200], json.dumps(clean_delta), stack["version"], new_yaml, diff, json.dumps(pol),
                 json.dumps(costs), json.dumps(validation), risk, status, user["id"], user["username"],
                 "policy:auto-approve" if status == "approved" else None, now if status == "approved" else None,
                 source_module, now, now))
        self.store.add_audit(user["id"], user["username"], "iac_change_proposed", target=cid,
                             details=f"{env} {action} risk={risk} status={status}")
        if status == "approved":
            self.store.add_audit(None, "policy:auto-approve", "iac_change_auto_approved", target=cid,
                                 details=f"low risk {meta['tier']} change, {pol['rules_evaluated']} rules passed")
            self.publish(cid)
        elif status == "pending_approval":
            self.store.add_notification(None, "info", "Infrastructure change needs approval",
                                        f"{user['username']}: {title} ({cid}, {env}, risk {risk}).")
        return self.get_change(cid)

    # ------------------------------------------------------------------ read
    def get_change(self, cid: str):
        r = self._q("SELECT * FROM iac_changes WHERE id=?", (cid,), one=True)
        if not r:
            return None
        for k in ("delta", "policy", "cost", "validation", "mr"):
            r[k] = json.loads(r[k]) if r.get(k) else None
        return r

    def list_changes(self, env: str | None = None, status: str | None = None) -> list[dict]:
        sql, args = "SELECT id,env,action,title,risk,status,requester,approver,created_at,updated_at,mr,cost FROM iac_changes", []
        cond = []
        if env:
            cond.append("env=?"); args.append(env)
        if status:
            cond.append("status=?"); args.append(status)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        rows = self._q(sql + " ORDER BY created_at DESC LIMIT 500", tuple(args))
        for r in rows:
            r["mr"] = json.loads(r["mr"]) if r["mr"] else None
            r["monthly"] = (json.loads(r.pop("cost")) or {}).get("monthly")
        return rows

    # ------------------------------------------------------------------ decide
    def approve(self, cid: str, user: dict, reason: str = "") -> dict:
        ch = self._require(cid, ("pending_approval",))
        if ch["requester_id"] == user["id"]:
            raise ChangeError("You cannot approve your own change (separation of duties).", status=403)
        self._set(cid, status="approved", approver=user["username"], reason=reason, decided_at=self._now())
        self.store.add_audit(user["id"], user["username"], "iac_change_approved", target=cid, details=reason[:200])
        return self.publish(cid)

    def reject(self, cid: str, user: dict, reason: str = "") -> dict:
        ch = self._require(cid, ("pending_approval", "blocked"))
        if ch["requester_id"] == user["id"] and ch["status"] == "pending_approval":
            raise ChangeError("You cannot decide your own change (separation of duties).", status=403)
        self._set(cid, status="rejected", approver=user["username"], reason=reason, decided_at=self._now())
        self.store.add_audit(user["id"], user["username"], "iac_change_rejected", target=cid, level="warn", details=reason[:200])
        self.store.add_notification(ch["requester_id"], "warning", "Change rejected", f"{ch['title']} ({cid}). {reason}".strip())
        return self.get_change(cid)

    def cancel(self, cid: str, user: dict) -> dict:
        ch = self._require(cid, ("pending_approval", "blocked", "queued"))
        if ch["requester_id"] != user["id"] and user["role"] != "admin":
            raise ChangeError("Only the requester or an admin can cancel.", status=403)
        self._set(cid, status="cancelled")
        self.store.add_audit(user["id"], user["username"], "iac_change_cancelled", target=cid)
        return self.get_change(cid)

    # ------------------------------------------------------------------ publish
    def publish(self, cid: str) -> dict:
        with _PUBLISH_LOCK:
            ch = self.get_change(cid)
            stack = self.get_stack(ch["env"])
            if self._q("SELECT id FROM iac_changes WHERE env=? AND status='mr_open' AND id<>?", (ch["env"], cid)):
                self._set(cid, status="queued", log="Waiting for the open merge request on this environment.")
                return self.get_change(cid)
            # conflict detection: another published change touched the same instance since this one was proposed
            if stack["version"] != ch["base_version"]:
                touched = set(ch["delta"].keys())
                for v in self._q("SELECT change_id FROM iac_stack_versions WHERE env=? AND version>?", (ch["env"], ch["base_version"])):
                    other = self.get_change(v["change_id"])
                    if other and touched & set(other["delta"].keys()):
                        self._set(cid, status="conflict",
                                  log=f"{', '.join(sorted(touched & set(other['delta'].keys())))} changed by {other['id']} after this change was proposed. Submit it again.")
                        return self.get_change(cid)
            components = _apply_delta(stack["components"], ch["delta"])
            new_version = stack["version"] + 1
            yaml_text = self.render(ch["env"], stack["meta"], components)
            manifest = self.change_manifest(ch, stack["meta"], stack["components"])
            self._x("UPDATE iac_stacks SET components=?, version=?, updated_at=? WHERE env=?",
                    (json.dumps(components), new_version, self._now(), ch["env"]))
            self._x("INSERT INTO iac_stack_versions (env,version,components,change_id,created_at) VALUES (?,?,?,?,?)",
                    (ch["env"], new_version, json.dumps(components), cid, self._now()))
            self._x("UPDATE iac_changes SET proposed_yaml=? WHERE id=?", (yaml_text, cid))
            files = {self.stack_path(stack["meta"], ch["env"]): yaml_text,
                     f"changes/{cid}.json": json.dumps(manifest, indent=2) + "\n"}
            gl = None
            try:
                gl = self.gitlab_client()
            except gitlab_mod.GitLabError as e:
                self._set(cid, log=f"GitLab not used: {e}")
            if gl:
                return self._publish_gitlab(ch, gl, files, manifest)
            return self._publish_local(ch, files, manifest)

    def change_manifest(self, ch: dict, meta: dict, before: dict) -> dict:
        ops = []
        for inst, spec in ch["delta"].items():
            comp = spec["component"] if spec else before[inst]["component"]
            ops.append({"instance": inst, "component": comp, "op": "destroy" if spec is None else "apply"})
        order = {c: i for i, c in enumerate(DESTROY_ORDER)}
        applies = sorted([o for o in ops if o["op"] == "apply"], key=lambda o: -order.get(o["component"], 50))
        destroys = sorted([o for o in ops if o["op"] == "destroy"], key=lambda o: order.get(o["component"], 50))
        return {"id": ch["id"], "environment": ch["env"], "tier": meta["tier"], "account_id": meta.get("account_id"),
                "stack": ch["env"], "stack_file": self.stack_path(meta, ch["env"]), "title": ch["title"],
                "requested_by": ch["requester"], "approved_by": ch["approver"], "risk": ch["risk"],
                "operations": destroys + applies}

    def _publish_local(self, ch, files, manifest):
        for rel, content in files.items():
            p = IAC_DIR / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        self._set(ch["id"], status="committed", log=f"Wrote {', '.join(files)} under {IAC_DIR}.")
        self.store.add_audit(None, "m03", "iac_change_committed", target=ch["id"], details="local files")
        if self.simulated:
            self._simulate_apply(ch, manifest)
        return self.get_change(ch["id"])

    def _publish_gitlab(self, ch, gl, files, manifest):
        g = self.settings()["gitlab"]
        prefix = g["path_prefix"].strip("/")
        files = {(f"{prefix}/{k}" if prefix else k): v for k, v in files.items()}
        branch = f"fde/{ch['id'].lower()}"
        pol, cst = ch["policy"], ch["cost"]
        desc = "\n".join([
            f"**{ch['title']}**", "",
            f"- Change: `{ch['id']}` · environment `{ch['env']}` · tier `{manifest['tier']}` · risk **{ch['risk']}**",
            f"- Requested by `{ch['requester']}` · approved in portal by `{ch['approver']}`",
            f"- Policy: {pol['rules_evaluated']} rules, {pol['denies']} deny, {pol['warnings']} warn",
            f"- Estimated monthly cost delta: ${cst['monthly']}",
            "", "Operations:", *[f"- `{o['op']}` {o['instance']} ({o['component']})" for o in manifest["operations"]],
            "", "Generated by FDE Nexus M03. CI validates and plans on this MR and applies after merge."])
        try:
            gl.commit_files(branch, g["target_branch"], f"{ch['id']}: {ch['title']}", files)
            mr = gl.open_merge_request(branch, g["target_branch"], f"[{ch['id']}] {ch['title']}", desc,
                                       ["fde-nexus", f"risk::{ch['risk']}", f"tier::{manifest['tier']}"])
        except gitlab_mod.GitLabError as e:
            self._rollback_stack(ch)
            self._set(ch["id"], status="failed", log=str(e))
            self.store.add_audit(None, "m03", "iac_change_publish_failed", target=ch["id"], level="warn", details=str(e)[:200])
            return self.get_change(ch["id"])
        self._set(ch["id"], status="mr_open", mr=json.dumps({**mr, "branch": branch}), log=f"Opened merge request !{mr['iid']}.")
        self.store.add_audit(None, "m03", "iac_mr_opened", target=ch["id"], details=mr.get("web_url"))
        self.store.add_notification(ch["requester_id"], "info", "Merge request opened",
                                    f"{ch['id']}: {mr.get('web_url')}")
        return self.get_change(ch["id"])

    def refresh(self, cid: str) -> dict:
        ch = self.get_change(cid)
        if not ch or ch["status"] not in ("mr_open", "merged") or not ch["mr"]:
            return ch
        gl = self.gitlab_client()
        mr = gl.merge_request(ch["mr"]["iid"])
        info = {**ch["mr"], **mr}
        if mr["state"] == "merged":
            status = "applied" if mr.get("pipeline_status") == "success" else "merged"
            if mr.get("pipeline_status") in ("failed", "canceled"):
                status = "failed"
            self._set(cid, status=status, mr=json.dumps(info), applied_at=self._now() if status == "applied" else None)
            if ch["status"] == "mr_open":
                self.store.add_audit(None, "gitlab", "iac_mr_merged", target=cid, details=f"by {mr.get('merged_by')}")
                self._release_queue(ch["env"])
        elif mr["state"] == "closed":
            self._rollback_stack(ch)
            self._set(cid, status="closed", mr=json.dumps(info), log="Merge request closed without merge; stack restored.")
            self.store.add_audit(None, "gitlab", "iac_mr_closed", target=cid, level="warn")
            self._release_queue(ch["env"])
        else:
            self._set(cid, mr=json.dumps(info))
        return self.get_change(cid)

    def merge(self, cid: str, user: dict) -> dict:
        ch = self._require(cid, ("mr_open",))
        gl = self.gitlab_client()
        gl.merge(ch["mr"]["iid"])
        self.store.add_audit(user["id"], user["username"], "iac_mr_merge_requested", target=cid)
        return self.refresh(cid)

    def _release_queue(self, env):
        nxt = self._q("SELECT id FROM iac_changes WHERE env=? AND status='queued' ORDER BY created_at LIMIT 1", (env,), one=True)
        if nxt:
            self.publish(nxt["id"])

    def _rollback_stack(self, ch):
        stack = self.get_stack(ch["env"])
        row = self._q("SELECT version FROM iac_stack_versions WHERE env=? AND change_id=?", (ch["env"], ch["id"]), one=True)
        if not row or row["version"] != stack["version"]:
            return
        prev = self._q("SELECT components FROM iac_stack_versions WHERE env=? AND version=?", (ch["env"], row["version"] - 1), one=True)
        comps = prev["components"] if prev else "{}"
        self._x("UPDATE iac_stacks SET components=?, version=?, updated_at=? WHERE env=?", (comps, row["version"] - 1, self._now(), ch["env"]))
        self._x("DELETE FROM iac_stack_versions WHERE env=? AND version=?", (ch["env"], row["version"]))

    def _simulate_apply(self, ch, manifest):
        st = self.store
        with st._LOCK, st._connect() as conn:
            for op in manifest["operations"]:
                key = f"{ch['env']}/{op['instance']}"
                conn.execute("DELETE FROM resources WHERE request_id=?", (key,))
                if op["op"] == "apply":
                    conn.execute("INSERT INTO resources (id,name,type,environment,owner_team,region,status,request_id,tags,created_at) "
                                 "VALUES (?,?,?,?,?,?,?,?,?,?)",
                                 ("res-" + secrets.token_hex(3), op["instance"].split("/")[-1], op["component"], ch["env"],
                                  self.get_stack(ch["env"])["meta"].get("team"), self.get_stack(ch["env"])["meta"].get("region"),
                                  "healthy", key, json.dumps({"change": ch["id"], "simulated": True}), self._now()))
            conn.commit()
        self._set(ch["id"], status="applied", applied_at=self._now(),
                  log=(ch.get("log") or "") + "\nSimulation mode: operations recorded, no AWS call made.")
        st.add_audit(None, "m03", "iac_change_applied", target=ch["id"], details="simulated")
        st.add_notification(ch["requester_id"], "success", "Change applied", f"{ch['title']} ({ch['id']}) simulated.")

    # ------------------------------------------------------------------ plan / apply / drift (live)
    def run(self, cid: str, mode: str, user: dict) -> dict:
        """mode = plan | apply. Runs scripts/run_change.py against the committed stack."""
        ch = self._require(cid, ("committed", "applied", "failed") if mode == "apply" else
                           ("pending_approval", "approved", "committed", "applied", "failed", "mr_open", "merged"))
        if self.simulated:
            raise ChangeError("Plan and apply need live mode (M01_DEMO=0) and AWS credentials on the host.")
        if mode == "apply" and not self.settings()["portal_apply"]:
            raise ChangeError("Portal apply is off. Merge the GitLab MR (CI applies) or set M03_PORTAL_APPLY=1.")
        manifest_path = IAC_DIR / "changes" / f"{cid}.json"
        if not manifest_path.exists():
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            stack = self.get_stack(ch["env"])
            manifest_path.write_text(json.dumps(self.change_manifest(ch, stack["meta"], stack["components"]), indent=2))
        r = _run(["python3", str(IAC_DIR / "scripts" / "run_change.py"), str(manifest_path), "--mode", mode],
                 IAC_DIR, timeout=3600)
        self._set(cid, log=r["output"][-20000:], status=("applied" if r["code"] == 0 else "failed") if mode == "apply" else ch["status"],
                  applied_at=self._now() if mode == "apply" and r["code"] == 0 else ch.get("applied_at"))
        self.store.add_audit(user["id"], user["username"], f"iac_{mode}", target=cid, level="info" if r["code"] == 0 else "warn")
        return {"code": r["code"], "output": r["output"][-20000:]}

    def drift(self, env: str, instance: str, user: dict) -> dict:
        stack = self.get_stack(env)
        if not stack or instance not in stack["components"]:
            raise ChangeError("Unknown environment or component", status=404)
        if self.simulated:
            return {"status": "unknown", "output": "Drift detection runs `terraform plan -detailed-exitcode` against AWS. "
                                                   "It needs live mode (M01_DEMO=0) and credentials."}
        r = _run([ATMOS, "terraform", "plan", instance, "-s", env, "--", "-detailed-exitcode", "-lock=false", "-input=false"],
                 IAC_DIR, timeout=1800)
        status = {0: "in_sync", 2: "drifted"}.get(r["code"], "error")
        self.store.add_audit(user["id"], user["username"], "iac_drift_check", target=f"{env}/{instance}", details=status)
        return {"status": status, "output": r["output"][-20000:]}

    def rollback(self, env: str, version: int, user: dict) -> dict:
        stack = self.get_stack(env)
        row = self._q("SELECT components FROM iac_stack_versions WHERE env=? AND version=?", (env, version), one=True)
        if not stack or (not row and version != 0):
            raise ChangeError("Unknown version", status=404)
        target = json.loads(row["components"]) if row else {}
        delta = {}
        for inst in set(stack["components"]) | set(target):
            if inst not in target:
                delta[inst] = None
            elif stack["components"].get(inst) != target[inst]:
                delta[inst] = {"component": target[inst]["component"],
                               "vars": {k: v for k, v in target[inst]["vars"].items() if k not in ENGINE_VARS}}
        if not delta:
            raise ChangeError("The environment already matches that version.")
        return self.propose(env, stack["meta"], delta, "rollback", f"Roll back {env} to version {version}", user)

    # ------------------------------------------------------------------ helpers
    def _require(self, cid, statuses):
        ch = self.get_change(cid)
        if not ch:
            raise ChangeError("Change not found", status=404)
        if ch["status"] not in statuses:
            raise ChangeError(f"Change is {ch['status']}; this action needs {' or '.join(statuses)}.")
        return ch

    def _set(self, cid, **fields):
        fields["updated_at"] = self._now()
        cols = ", ".join(f"{k}=?" for k in fields)
        self._x(f"UPDATE iac_changes SET {cols} WHERE id=?", (*fields.values(), cid))


# ---------------------------------------------------------------------- module-level helpers
def _apply_delta(components: dict, delta: dict) -> dict:
    out = json.loads(json.dumps(components))
    for inst, spec in delta.items():
        if spec is None:
            out.pop(inst, None)
        else:
            out[inst] = spec
    return out


def _run(cmd: list[str], cwd: Path, timeout: int = 120) -> dict:
    env = {**os.environ, "ATMOS_LOGS_LEVEL": "Warning", "TF_IN_AUTOMATION": "1", "NO_COLOR": "1"}
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=env)
        return {"code": p.returncode, "stdout": p.stdout, "output": (p.stdout + "\n" + p.stderr).strip()}
    except subprocess.TimeoutExpired:
        return {"code": 124, "stdout": "", "output": f"Timed out after {timeout}s: {' '.join(cmd[:4])}"}
    except OSError as e:
        return {"code": 127, "stdout": "", "output": str(e)}


def _parse_variables(text: str, shared: bool) -> dict:
    out = {}
    for m in re.finditer(r'^variable\s+"([^"]+)"\s*\{', text, re.M):
        start, depth, i = m.end(), 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[start:i - 1]
        t = re.search(r"^\s*type\s*=\s*(.+)$", body, re.M)
        d = re.search(r'^\s*description\s*=\s*"([^"]*)"', body, re.M)
        dv = re.search(r"^\s*default\s*=\s*(.+)$", body, re.M)
        opts = re.search(r"contains\(\[([^\]]*)\]", body)
        out[m.group(1)] = {
            "type": t.group(1).strip() if t else "any",
            "description": d.group(1) if d else "",
            "required": dv is None,
            "default": _hcl_literal(dv.group(1).strip()) if dv else None,
            "options": [o.strip().strip('"') for o in opts.group(1).split(",")] if opts else None,
            "shared": shared,
        }
    return out


def _hcl_literal(s: str):
    try:
        return json.loads(s)
    except ValueError:
        return s


def _coerce(tf_type: str, val):
    t = tf_type.replace(" ", "")
    try:
        if t == "string":
            return isinstance(val, (str, int, float)) and not isinstance(val, bool), str(val)
        if t == "number":
            if isinstance(val, bool):
                return False, val
            n = float(val)
            return True, int(n) if n.is_integer() else n
        if t == "bool":
            if isinstance(val, bool):
                return True, val
            if str(val).lower() in ("true", "false"):
                return True, str(val).lower() == "true"
            return False, val
        if t.startswith("list("):
            if isinstance(val, str):
                val = [x.strip() for x in val.split(",") if x.strip()]
            if not isinstance(val, list):
                return False, val
            inner = t[5:-1]
            res = [_coerce(inner, x) for x in val]
            return all(r[0] for r in res), [r[1] for r in res]
        if t.startswith("map("):
            return isinstance(val, dict), {str(k): str(v) for k, v in (val or {}).items()} if isinstance(val, dict) else val
    except (TypeError, ValueError):
        return False, val
    return True, val
