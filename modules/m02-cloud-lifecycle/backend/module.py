"""M02 Cloud Account and Infrastructure Lifecycle: environments, resources, accounts, decommissioning.

M02 decides WHAT to build and validates the request. Every change is handed to M03
(ctx.services["iac"]) which renders the Atmos stack, runs policy, cost and Atmos
validation, routes approval and publishes to GitLab. M02 never calls AWS to create things.
"""
from __future__ import annotations

import json
import re

from flask import jsonify, request

import m02_cache
import m02_catalog as cat
import m02_live as live

API = "/api/m02"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS m02_environments (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, region TEXT NOT NULL, tier TEXT NOT NULL,
    team TEXT NOT NULL, description TEXT, cidr TEXT, azs TEXT, create_change TEXT, retire_change TEXT,
    created_by TEXT, created_at TEXT NOT NULL
);
"""


def register(app, ctx):
    store = ctx.store
    auth, role = ctx.auth_required, ctx.role_required
    with store._LOCK, store._connect() as conn:
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(m02_environments)").fetchall()}
        for col, ddl in (("kind", "TEXT NOT NULL DEFAULT 'managed'"), ("vpc_id", "TEXT"), ("subnets", "TEXT"), ("retired_at", "TEXT")):
            if col not in cols:
                conn.execute(f"ALTER TABLE m02_environments ADD COLUMN {col} {ddl}")
        conn.commit()
    VPC_TYPES = {"ec2-instance", "efs", "eks-cluster", "alb"}

    def iac():
        eng = ctx.services.get("iac")
        if not eng:
            raise RuntimeError("M03 (IaC engine) is not loaded.")
        return eng

    def q(sql, args=(), one=False):
        with store._connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
        return (rows[0] if rows else None) if one else rows

    def x(sql, args=()):
        with store._LOCK, store._connect() as conn:
            conn.execute(sql, args)
            conn.commit()

    def can_write(user, tier):
        if user["role"] == "viewer":
            return "Viewers have read-only access."
        if tier == "production" and user["role"] not in ("admin", "operator"):
            return "Only admins and operators can request production changes."
        return None

    def env_status(e):
        eng = iac()
        if e.get("kind") == "existing":
            if e.get("retired_at"):
                return "retired"
            if e.get("retire_change"):
                ch = eng.get_change(e["retire_change"])
                if ch and ch["status"] not in ("applied", "rejected", "cancelled", "blocked", "closed", "failed"):
                    return "decommissioning"
            return "active"
        if e.get("retire_change"):
            ch = eng.get_change(e["retire_change"])
            if ch and ch["status"] == "applied":
                return "retired"
            if ch and ch["status"] not in ("rejected", "cancelled", "blocked", "closed", "failed"):
                return "decommissioning"
        ch = eng.get_change(e["create_change"]) if e.get("create_change") else None
        if not ch:
            return "unknown"
        return {"applied": "active", "rejected": "rejected", "blocked": "blocked", "cancelled": "cancelled",
                "failed": "failed", "closed": "cancelled"}.get(ch["status"], "provisioning")

    def env_view(e, detail=False):
        eng = iac()
        e = dict(e)
        e["azs"] = json.loads(e["azs"] or "[]")
        e["subnets"] = json.loads(e.get("subnets") or "[]")
        e["status"] = env_status(e)
        stack = eng.get_stack(e["id"])
        comps = stack["components"] if stack else {}
        e["component_count"] = len(comps)
        e["monthly"] = round(sum(eng.estimate(c["component"], c["vars"])["monthly"] for c in comps.values()), 2)
        if detail:
            changes = eng.list_changes(env=e["id"])
            last = {}
            for chg in reversed(changes):
                full = eng.get_change(chg["id"])
                for inst in (full["delta"] or {}):
                    last[inst] = {"change": chg["id"], "status": chg["status"]}
            e["components"] = [{"instance": i, "component": c["component"], "vars": c["vars"],
                                "monthly": eng.estimate(c["component"], c["vars"])["monthly"], **last.get(i, {})}
                               for i, c in sorted(comps.items())]
            e["pending"] = [c for c in changes if c["status"] in ("pending_approval", "queued", "mr_open", "blocked", "conflict")]
            e["changes"] = changes[:50]
            e["versions"] = eng.stack_versions(e["id"]) if stack else []
        return e

    def account(acct_id):
        a = store.get_aws_account(str(acct_id))
        if not a:
            raise ValueError("Unknown AWS account. Connect it on the AWS Accounts page first.")
        return a

    def meta_for(e):
        a = account(e["account_id"])
        return {"account_id": a["id"], "region": e["region"], "tier": e["tier"], "team": e["team"],
                "assume_role_arn": a["role_arn"] if a["method"] == "assume-role" else "",
                "external_id": a.get("external_id") or ""}

    def err(msg, details=None, code=400):
        return jsonify({"error": msg, "details": details or []}), code

    def from_engine(fn):
        try:
            return fn()
        except Exception as e:  # map engine errors to HTTP
            if e.__class__.__name__ == "ChangeError":
                return err(str(e), getattr(e, "details", []), getattr(e, "status", 400))
            raise

    # ---------------------------------------------------------------- regions and CIDR
    @app.route(f"{API}/regions")
    @auth
    def regions():
        acct_id = request.args.get("account")
        if acct_id and ctx.config.LIVE_READS:
            try:
                import ec2 as m01_ec2  # M01 helper: session for an account (AssumeRole or instance role)
                sess = m01_ec2._session(account(acct_id))
                names = {c: n for c, (n, _) in cat.REGIONS.items()}
                enabled = [r["RegionName"] for r in sess.client("ec2").describe_regions()["Regions"]]
                out = []
                for code in sorted(enabled):
                    azs = sess.client("ec2", region_name=code).describe_availability_zones(
                        Filters=[{"Name": "zone-type", "Values": ["availability-zone"]}])["AvailabilityZones"]
                    out.append({"code": code, "name": names.get(code, code), "source": "aws",
                                "azs": [{"name": z["ZoneName"], "zone_id": z["ZoneId"]} for z in azs if z["State"] == "available"]})
                return jsonify({"regions": out, "source": "aws"}), 200
            except Exception as e:  # fall back to the built-in list and say why
                return jsonify({"regions": cat.static_regions(), "source": "built-in", "warning": f"AWS lookup failed: {str(e)[:160]}"}), 200
        return jsonify({"regions": cat.static_regions(), "source": "built-in",
                        "warning": "Built-in region list (no account selected or live reads off). AZ letters map to different physical zones per account."}), 200

    @app.route(f"{API}/cidr-plan")
    @auth
    def cidr_plan():
        try:
            plan = cat.plan_cidr(request.args.get("cidr", ""), int(request.args.get("azs", 3)))
        except ValueError as e:
            return err(str(e))
        acct = request.args.get("account")
        conflicts = []
        if acct:
            import ipaddress
            mine = ipaddress.ip_network(plan["cidr"])
            for e in q("SELECT id,cidr FROM m02_environments WHERE account_id=?", (acct,)):
                if e["cidr"] and mine.overlaps(ipaddress.ip_network(e["cidr"])) and env_status(e) != "retired":
                    conflicts.append(f"Overlaps {e['cidr']} ({e['id']}).")
        return jsonify({**plan, "conflicts": conflicts}), 200

    @app.route(f"{API}/cidr-suggest")
    @auth
    def cidr_suggest():
        used = [e["cidr"] for e in q("SELECT cidr FROM m02_environments WHERE account_id=?", (request.args.get("account", ""),)) if e["cidr"]]
        return jsonify({"cidr": cat.suggest_cidr(used)}), 200

    # ---------------------------------------------------------------- central AWS resource cache
    def _sess_factory(a):
        import ec2 as m01_ec2
        return m01_ec2._session(a)
    cache = m02_cache.Cache(ctx, _sess_factory)
    ctx.services["aws_cache"] = cache

    def cache_acct():
        a = store.get_aws_account(request.args.get("account") or (request.get_json(silent=True) or {}).get("account") or "")
        if not a:
            raise ValueError("Pick a connected AWS account.")
        return a

    @app.route(f"{API}/cache/summary")
    @auth
    def cache_summary():
        try:
            a = cache_acct()
        except ValueError as e:
            return err(str(e))
        return jsonify({"account": {"id": a["id"], "alias": a["alias"], "region": a["region"], "status": a["status"]}, **cache.summary(a["id"])}), 200

    @app.route(f"{API}/cache/sync", methods=["POST"])
    @auth
    def cache_sync():
        if request.current_user["role"] == "viewer":
            return err("Viewers can browse the cache but not start a sync.", code=403)
        if not ctx.config.LIVE_READS:
            return err("Live reads are off (M01_LIVE_READS=0).")
        try:
            a = cache_acct()
        except ValueError as e:
            return err(str(e))
        d = request.get_json(silent=True) or {}
        regions = d.get("regions") or "current"
        if isinstance(regions, list) and any(not re.fullmatch(r"[a-z]{2}(-[a-z]+)+-\d", str(r)) for r in regions):
            return err("Invalid region in the list.")
        try:
            job, started = cache.start_sync(a, regions, d.get("services"), request.current_user["username"])
        except ValueError as e:
            return err(str(e))
        if started:
            store.add_audit(request.current_user["id"], request.current_user["username"], "aws_cache_sync_started", target=a["id"],
                            details=f"{job['id']} {len(job['regions'])} regions {len(job['services'])} services")
        return jsonify({"job": job, "started": started}), 202 if started else 200

    @app.route(f"{API}/cache/jobs/<jid>")
    @auth
    def cache_job(jid):
        j = cache.job(jid)
        return (jsonify({"job": j}), 200) if j else err("Unknown job", code=404)

    @app.route(f"{API}/cache/resources")
    @auth
    def cache_resources():
        try:
            a = cache_acct()
        except ValueError as e:
            return err(str(e))
        g = request.args
        return jsonify(cache.resources(a["id"], g.get("service"), g.get("region"), (g.get("q") or "").strip()[:100] or None, g.get("state"),
                                       g.get("tag"), int(g.get("limit", 100)), int(g.get("offset", 0)), g.get("sort", "name"))), 200

    @app.route(f"{API}/cache/resource")
    @auth
    def cache_resource():
        try:
            a = cache_acct()
        except ValueError as e:
            return err(str(e))
        r = cache.resource(a["id"], request.args.get("region", ""), request.args.get("service", ""), request.args.get("id", ""))
        return (jsonify({"resource": r}), 200) if r else err("Not in the cache", code=404)

    @app.route(f"{API}/cache/settings", methods=["PUT"])
    @ctx.admin_required
    def cache_settings():
        d = request.get_json(silent=True) or {}
        if "interval_minutes" in d:
            mins = int(d["interval_minutes"])
            if mins not in (0, 15, 30, 60, 180, 360, 720, 1440):
                return err("Interval must be 0 (off), 15, 30, 60, 180, 360, 720 or 1440 minutes.")
            ctx.set_setting("aws_cache.interval_minutes", mins)
        if "account" in d and "auto_refresh" in d:
            x("UPDATE aws_cache_accounts SET auto_refresh=? WHERE account_id=?", (1 if d["auto_refresh"] else 0, str(d["account"])))
        store.add_audit(request.current_user["id"], request.current_user["username"], "aws_cache_settings", details=json.dumps(d)[:200])
        return jsonify({"interval_minutes": cache.interval_minutes()}), 200

    @app.route(f"{API}/cache", methods=["DELETE"])
    @ctx.admin_required
    def cache_forget():
        try:
            a = cache_acct()
        except ValueError as e:
            return err(str(e))
        cache.forget(a["id"])
        store.add_audit(request.current_user["id"], request.current_user["username"], "aws_cache_cleared", target=a["id"], level="warn")
        return jsonify({"message": "Cached data for this account was removed."}), 200

    # ---------------------------------------------------------------- live account data (read-only)
    def live_session(acct_id, region=None):
        if not ctx.config.LIVE_READS:
            raise ValueError("Live reads are off (M01_LIVE_READS=0).")
        a = account(acct_id)
        import ec2 as m01_ec2
        return m01_ec2._session(a, region or a["region"]), a

    @app.route(f"{API}/live/inventory")
    @auth
    def live_inventory():
        try:
            sess, a = live_session(request.args.get("account"), request.args.get("region"))
        except ValueError as e:
            return err(str(e))
        region = request.args.get("region") or a["region"]
        only = [x for x in (request.args.get("only") or "").split(",") if x] or None
        data = live.inventory(sess, region, only)
        u = request.current_user
        store.add_audit(u["id"], u["username"], "aws_inventory_read", target=a["id"], details=region)
        return jsonify({"account": a["id"], "alias": a["alias"], "region": region, "sections": data,
                        "fetched_at": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}), 200

    @app.route(f"{API}/live/vpcs")
    @auth
    def live_vpcs():
        try:
            sess, a = live_session(request.args.get("account"), request.args.get("region"))
            return jsonify({"vpcs": live.vpcs(sess, request.args.get("region") or a["region"])}), 200
        except ValueError as e:
            return err(str(e))
        except Exception as e:
            return err(live._err(e), code=502)

    @app.route(f"{API}/environments/import", methods=["POST"])
    @auth
    def import_environment():
        """Register an account's EXISTING VPC (or just the account and region) as an environment.
        Nothing is created in AWS; resources launched into it use the real VPC and subnets."""
        d = request.get_json(silent=True) or {}
        user = request.current_user
        eid = str(d.get("name", "")).strip().lower()
        tier, region = d.get("tier"), str(d.get("region", ""))
        errors = []
        if not cat.ENV_RE.match(eid):
            errors.append("Name: 3-32 chars, starts with a letter, lowercase letters, digits and hyphens.")
        elif q("SELECT 1 FROM m02_environments WHERE id=?", (eid,), one=True):
            errors.append(f"Environment {eid} already exists.")
        if tier not in cat.TIERS:
            errors.append("Pick a tier.")
        if not str(d.get("team", "")).strip():
            errors.append("Team is required.")
        msg = can_write(user, tier)
        if msg:
            return err(msg, code=403)
        if errors:
            return err("Validation failed", errors)
        try:
            sess, a = live_session(d.get("account_id"), region)
        except ValueError as e:
            return err(str(e))
        vpc_id, subnets, cidr, azs = d.get("vpc_id") or "", [], None, []
        if vpc_id:
            try:
                found = next((v for v in live.vpcs(sess, region) if v["id"] == vpc_id), None)
            except Exception as e:
                return err(f"Could not read VPCs: {live._err(e)}", code=502)
            if not found:
                return err(f"VPC {vpc_id} was not found in {a['id']} / {region}.")
            subnets = [{"id": x["id"], "az": x["az"], "cidr": x["cidr"], "public": x["public"], "name": x["name"]} for x in found["subnets"]]
            cidr, azs = found["cidr"], found["azs"]
        from datetime import datetime, timezone
        x("INSERT INTO m02_environments (id,account_id,region,tier,team,description,cidr,azs,kind,vpc_id,subnets,created_by,created_at) "
          "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (eid, a["id"], region, tier, d["team"].strip(), str(d.get("description", ""))[:300], cidr, json.dumps(azs), "existing",
           vpc_id or None, json.dumps(subnets), user["username"], datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
        iac().ensure_stack(eid, meta_for({"account_id": a["id"], "region": region, "tier": tier, "team": d["team"].strip()}))
        store.add_audit(user["id"], user["username"], "environment_imported", target=eid, details=f"{a['id']} {region} {vpc_id or 'no VPC'}")
        return jsonify({"environment": env_view(q("SELECT * FROM m02_environments WHERE id=?", (eid,), one=True))}), 201

    @app.route(f"{API}/environments/<eid>", methods=["DELETE"])
    @role("admin", "operator")
    def forget_environment(eid):
        """Remove an imported environment from the portal (nothing in AWS is touched)."""
        e = q("SELECT * FROM m02_environments WHERE id=?", (eid,), one=True)
        if not e:
            return err("Unknown environment", code=404)
        if e.get("kind") != "existing":
            return err("Portal-built environments are removed with Decommission (Terraform destroy).")
        stack = iac().get_stack(eid)
        if stack and stack["components"]:
            return err("Decommission the resources the portal launched here first.")
        from datetime import datetime, timezone
        x("UPDATE m02_environments SET retired_at=? WHERE id=?", (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), eid))
        store.add_audit(request.current_user["id"], request.current_user["username"], "environment_forgotten", target=eid)
        return jsonify({"message": "Removed from the portal. Nothing in AWS was changed."}), 200

    # ---------------------------------------------------------------- catalog
    @app.route(f"{API}/resource-types")
    @auth
    def resource_types():
        return jsonify({"types": [{"id": k, **v} for k, v in cat.RESOURCE_TYPES.items()], "tiers": cat.TIERS}), 200

    # ---------------------------------------------------------------- environments
    @app.route(f"{API}/environments")
    @auth
    def environments():
        return jsonify({"environments": [env_view(e) for e in q("SELECT * FROM m02_environments ORDER BY created_at DESC")]}), 200

    @app.route(f"{API}/environments/<eid>")
    @auth
    def environment(eid):
        e = q("SELECT * FROM m02_environments WHERE id=?", (eid,), one=True)
        if not e:
            return err("Unknown environment", code=404)
        return jsonify({"environment": env_view(e, detail=True)}), 200

    def _env_request(d, user, dry):
        eid = str(d.get("name", "")).strip().lower()
        tier = d.get("tier")
        errors = []
        if not cat.ENV_RE.match(eid):
            errors.append("Name: 3-32 chars, starts with a letter, lowercase letters, digits and hyphens.")
        if tier not in cat.TIERS:
            errors.append("Pick a tier.")
        if not str(d.get("team", "")).strip():
            errors.append("Team is required.")
        region = d.get("region")
        if region not in cat.REGIONS and not re.fullmatch(r"[a-z]{2}(-[a-z]+)+-\d", str(region)):
            errors.append("Pick a region.")
        azs = d.get("azs") or []
        if not isinstance(azs, list) or not 1 <= len(azs) <= 6 or any(not str(a).startswith(str(region)) for a in azs):
            errors.append("Pick 1-6 availability zones in the selected region.")
        if tier == "production" and isinstance(azs, list) and len(azs) < 2:
            errors.append("Production needs at least 2 availability zones.")
        nat = d.get("nat_mode", "single")
        if nat not in ("none", "single", "per-az"):
            errors.append("Invalid NAT mode.")
        try:
            a = account(d.get("account_id"))
            if a["status"] != "connected":
                errors.append("The AWS account is not connected. Test the connection first.")
        except ValueError as e:
            errors.append(str(e))
            a = None
        msg = can_write(user, tier)
        if msg:
            return err(msg, code=403)
        if not dry and q("SELECT 1 FROM m02_environments WHERE id=?", (eid,), one=True):
            errors.append(f"Environment {eid} already exists.")
        plan = None
        if not errors:
            try:
                plan = cat.plan_cidr(d.get("cidr", ""), len(azs))
            except ValueError as e:
                errors.append(f"CIDR: {e}")
        if errors:
            return err("Validation failed", errors)
        first_in_account = not q("SELECT 1 FROM m02_environments WHERE account_id=?", (a["id"],), one=True)
        e = {"account_id": a["id"], "region": region, "tier": tier, "team": d["team"].strip()}
        delta = {
            "vpc": {"component": "vpc", "vars": {
                "cidr": plan["cidr"], "azs": azs, "public_subnets": plan["public"], "private_subnets": plan["private"],
                "nat_mode": nat, "flow_logs": bool(d.get("flow_logs", True))}},
            "account-baseline": {"component": "account-baseline", "vars": {
                "manage_account_wide": first_in_account, "enable_guardduty": bool(d.get("guardduty", False)),
                "enable_access_analyzer": True}},
        }
        title = f"Create environment {eid} ({tier}, {region})"
        res = from_engine(lambda: iac().propose(eid, meta_for(e), delta, "create-environment", title, user, "M02", dry_run=dry))
        if not isinstance(res, dict):
            return res
        if dry:
            return jsonify({"preview": res, "cidr_plan": plan}), 200
        from datetime import datetime, timezone
        x("INSERT INTO m02_environments (id,account_id,region,tier,team,description,cidr,azs,create_change,created_by,created_at) "
          "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
          (eid, a["id"], region, tier, e["team"], str(d.get("description", ""))[:300], plan["cidr"], json.dumps(azs),
           res["id"], user["username"], datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
        return jsonify({"change": res, "environment": eid}), 201

    @app.route(f"{API}/environments", methods=["POST"])
    @auth
    def create_environment():
        return _env_request(request.json or {}, request.current_user, False)

    @app.route(f"{API}/environments/preview", methods=["POST"])
    @auth
    def preview_environment():
        return _env_request(request.json or {}, request.current_user, True)

    # ---------------------------------------------------------------- resources in an environment
    def _resource_request(d, user, dry):
        rtype = d.get("type")
        if rtype not in cat.RESOURCE_TYPES:
            return err("Unknown resource type")
        e = q("SELECT * FROM m02_environments WHERE id=?", (str(d.get("environment", "")),), one=True)
        if not e:
            return err("Pick an environment. Create one first if the list is empty.")
        st = env_status(e)
        if st not in ("active", "provisioning"):
            return err(f"Environment {e['id']} is {st}.")
        msg = can_write(user, e["tier"])
        if msg:
            return err(msg, code=403)
        values = d.get("values") or {}
        v, errors = cat.build_vars(rtype, values)
        if e.get("kind") == "existing" and not errors:
            net = d.get("network") or {}
            needs_vpc = rtype in VPC_TYPES or (rtype == "route53-zone" and v.get("private_zone"))
            if needs_vpc:
                vpc_id = net.get("vpc_id") or e.get("vpc_id") or ""
                sub_ids = [str(s) for s in (net.get("subnet_ids") or [])]
                if not vpc_id:
                    errors.append("Pick the VPC this resource goes into.")
                elif rtype != "route53-zone" and not sub_ids:
                    errors.append("Pick at least one subnet.")
                else:
                    known = {s["id"]: s for s in json.loads(e.get("subnets") or "[]")} if vpc_id == e.get("vpc_id") else {}
                    if not known:
                        try:
                            sess, _a = live_session(e["account_id"], e["region"])
                            vv = next((x for x in live.vpcs(sess, e["region"]) if x["id"] == vpc_id), None)
                        except Exception as ex:
                            vv, errors = None, errors + [f"Could not verify the VPC: {str(ex)[:160]}"]
                        if vv is None and not errors:
                            errors.append(f"VPC {vpc_id} not found in the account.")
                        known = {s["id"]: s for s in (vv or {}).get("subnets", [])}
                    bad = [s for s in sub_ids if s not in known]
                    if bad and not errors:
                        errors.append(f"Subnets not in {vpc_id}: {', '.join(bad)}")
                    if not errors:
                        v["vpc_id"] = vpc_id
                        if rtype != "route53-zone":
                            v["subnet_ids"] = sub_ids
                        if rtype == "ec2-instance":
                            v["subnet_tier"] = "public" if known[sub_ids[0]].get("public") else "private"
                        if rtype == "eks-cluster" and len({known[s]["az"] for s in sub_ids}) < 2:
                            errors.append("EKS needs subnets in at least two availability zones.")
        inst = cat.instance_name(rtype, values)
        stack = iac().get_stack(e["id"]) or {"components": {}}
        if not dry and inst in stack["components"] and not d.get("update"):
            errors.append(f"{inst} already exists in {e['id']}. Choose another name.")
        if errors:
            return err("Validation failed", errors)
        label = cat.RESOURCE_TYPES[rtype]["label"]
        verb = "Update" if inst in stack["components"] else "Create"
        title = f"{verb} {label} {inst.split('/')[-1]} in {e['id']}"
        res = from_engine(lambda: iac().propose(e["id"], meta_for(e), {inst: {"component": rtype, "vars": v}},
                                                "update" if verb == "Update" else "create", title, user, "M02", dry_run=dry))
        if not isinstance(res, dict):
            return res
        return (jsonify({"preview": res, "instance": inst}), 200) if dry else (jsonify({"change": res, "instance": inst}), 201)

    @app.route(f"{API}/resources", methods=["POST"])
    @auth
    def create_resource():
        return _resource_request(request.json or {}, request.current_user, False)

    @app.route(f"{API}/resources/preview", methods=["POST"])
    @auth
    def preview_resource():
        return _resource_request(request.json or {}, request.current_user, True)

    # ---------------------------------------------------------------- decommissioning
    @app.route(f"{API}/environments/<eid>/decommission", methods=["POST"])
    @role("admin", "operator")
    def decommission(eid):
        e = q("SELECT * FROM m02_environments WHERE id=?", (eid,), one=True)
        if not e:
            return err("Unknown environment", code=404)
        d = request.json or {}
        inst = d.get("instance")
        stack = iac().get_stack(eid)
        if not stack or not stack["components"]:
            return err("Nothing is deployed in this environment.")
        if inst:
            if inst not in stack["components"]:
                return err(f"{inst} is not in {eid}.")
            if e.get("kind") != "existing" and stack["components"][inst]["component"] in ("vpc", "account-baseline") and len(stack["components"]) > 2:
                return err("Remove the workloads first; the VPC and baseline go last (decommission the whole environment).")
            delta, title = {inst: None}, f"Decommission {inst} in {eid}"
        else:
            if str(d.get("confirm", "")) != eid:
                return err(f"Type the environment name ({eid}) to confirm.")
            delta, title = {i: None for i in stack["components"]}, f"Decommission environment {eid}"
        res = from_engine(lambda: iac().propose(eid, meta_for(e), delta, "destroy", title, request.current_user, "M02"))
        if not isinstance(res, dict):
            return res
        if not inst:
            x("UPDATE m02_environments SET retire_change=? WHERE id=?", (res["id"], eid))
        return jsonify({"change": res}), 201

    # ---------------------------------------------------------------- account provisioning (AWS Organizations)
    @app.route(f"{API}/accounts/provision", methods=["POST"])
    @ctx.admin_required
    def provision_account():
        d = request.json or {}
        errors = []
        name = str(d.get("account_name", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9 ._-]{3,50}", name):
            errors.append("Account name: 3-50 characters.")
        if not EMAIL_RE.match(str(d.get("account_email", ""))):
            errors.append("A unique root email address is required.")
        if not re.fullmatch(r"(r-[0-9a-z]{4,32}|ou-[0-9a-z]{4,32}-[0-9a-z]{8,32})", str(d.get("parent_id", ""))):
            errors.append("Parent must be an OU id (ou-xxxx-xxxxxxxx) or root id (r-xxxx).")
        try:
            mgmt = account(d.get("management_account_id"))
        except ValueError as e:
            errors.append(str(e))
            mgmt = None
        if errors:
            return err("Validation failed", errors)
        slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:40]
        meta = {"account_id": mgmt["id"], "region": mgmt["region"], "tier": "management", "team": "platform",
                "assume_role_arn": mgmt["role_arn"] if mgmt["method"] == "assume-role" else "",
                "external_id": mgmt.get("external_id") or ""}
        delta = {f"aws-account/{slug}": {"component": "aws-account", "vars": {
            "account_name": name, "account_email": d["account_email"], "parent_id": d["parent_id"],
            "close_on_deletion": bool(d.get("close_on_deletion", False))}}}
        res = from_engine(lambda: iac().propose("org-management", meta, delta, "create", f"Provision AWS account {name}",
                                                request.current_user, "M02"))
        if not isinstance(res, dict):
            return res
        return jsonify({"change": res, "next": "After apply, register the new account on the AWS Accounts page using "
                                               "role OrganizationAccountAccessRole (or your landing-zone role)."}), 201
