"""M09 AI Engineering & Multi-Agent Platform.

Model gateway (Anthropic Claude, OpenAI ChatGPT, any OpenAI-compatible server, AWS Bedrock),
custom agents with a tool allow-list, teams where a lead delegates to members, and a run trace
with token counts and cost. Tools are read-only (AWS data cache, module catalog, clock).
"""
from __future__ import annotations

import glob
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from flask import jsonify, request

import ec2
import m09_agents as A
import m09_providers as P

API = "/api/m09"
SCHEMA = """
CREATE TABLE IF NOT EXISTS m09_providers (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, base_url TEXT, default_model TEXT,
    api_key_env TEXT, api_key_enc TEXT, aws_account TEXT, region TEXT, price_in REAL, price_out REAL,
    enabled INTEGER NOT NULL DEFAULT 1, last_test TEXT, last_test_ok INTEGER, created_at TEXT NOT NULL, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS m09_agents (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT, provider_id TEXT NOT NULL, model TEXT NOT NULL,
    system_prompt TEXT NOT NULL, tools TEXT NOT NULL DEFAULT '[]', max_steps INTEGER NOT NULL DEFAULT 6,
    max_tokens INTEGER NOT NULL DEFAULT 1024, temperature REAL, owner TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS m09_teams (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT, lead_id TEXT NOT NULL, members TEXT NOT NULL,
    owner TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS m09_runs (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, target_id TEXT NOT NULL, target_name TEXT, username TEXT NOT NULL,
    task TEXT NOT NULL, status TEXT NOT NULL, output TEXT, error TEXT, steps TEXT, tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0, cost REAL, provider_id TEXT, started_at TEXT NOT NULL, finished_at TEXT, duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_m09_runs_started ON m09_runs(started_at DESC);
"""
MODEL_RX = re.compile(r"[A-Za-z0-9._:/\-]{1,200}")
ENV_RX = re.compile(r"[A-Z_][A-Z0-9_]{1,80}")
NAME_RX = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.\-]{1,59}")
ACCOUNT_RX = re.compile(r"\d{12}")
REGION_RX = re.compile(r"[a-z]{2}(-[a-z]+)+-\d")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def register(app, ctx):
    store, cfg = ctx.store, ctx.config
    auth = ctx.auth_required
    role = ctx.role_required
    with store._LOCK, store._connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()

    def q(sql, args=(), one=False):
        with store._connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
        return (rows[0] if rows else None) if one else rows

    def x(sql, args=()):
        with store._LOCK, store._connect() as conn:
            conn.execute(sql, args)
            conn.commit()

    def err(msg, code=400):
        return jsonify({"error": msg}), code

    def body():
        return request.get_json(silent=True) or {}

    def me():
        return request.current_user

    def audit(action, target="", details=""):
        u = me()
        store.add_audit(u.get("id"), u.get("username", "system"), action, target=target, details=str(details)[:500])

    def rank(user):
        return A.RANK.get(user.get("role"), 0)

    # ------------------------------------------------------------ environment for the runtime
    def cache():
        c = ctx.services.get("aws_cache")
        if not c:
            raise RuntimeError("The AWS cache (M02) is not loaded.")
        return c

    def modules():
        out = []
        for path in sorted(glob.glob(os.path.join(ctx.modules_dir, "m*", "manifest.json"))):
            with open(path, encoding="utf-8") as f:
                m = json.load(f)
            caps = m.get("capabilities", [])
            live = sum(1 for c in caps if c["status"] == "live")
            partial = sum(1 for c in caps if c["status"] == "partial")
            maturity = "live" if caps and live == len(caps) else "partial" if live or partial else "planned"
            out.append({"id": m["id"], "name": m["name"], "maturity": maturity, "live": live, "total": len(caps)})
        return out

    def bedrock_client(p):
        acct = store.get_aws_account(p["aws_account"]) if p.get("aws_account") else None
        if not acct:
            raise P.ProviderError("Pick a connected AWS account for this Bedrock provider.")
        if not p.get("region"):
            raise P.ProviderError("Bedrock providers need a region.")
        return ec2._session(acct, p["region"]).client("bedrock-runtime", region_name=p["region"])

    def load_provider(pid):
        p = q("SELECT * FROM m09_providers WHERE id=?", (pid,), one=True)
        if not p:
            raise P.ProviderError("Provider not found.")
        if not p["enabled"]:
            raise P.ProviderError(f"Provider {p['name']} is disabled.")
        return p, P.resolve_api_key(p, cfg.JWT_SECRET)

    def run_member(member, user, task, budget, tools, started):
        agent = load_agent(member["id"])
        prov, key = load_provider(agent["provider_id"])
        return A.run_agent(env, agent, prov, key, user, task, budget, tools, team=None, depth=1, started=started)

    def account_exists(acct):
        return bool(acct) and bool(store.get_aws_account(acct))

    class Env:
        pass
    env = Env()
    env.cache, env.modules, env.bedrock_client = cache, modules, bedrock_client
    env.account_exists, env.run_member = account_exists, run_member
    TOOLS = A.build_tools(env)

    # ------------------------------------------------------------ records
    def load_agent(aid):
        a = q("SELECT * FROM m09_agents WHERE id=?", (aid,), one=True)
        if not a:
            raise P.ProviderError("Agent not found.")
        return agent_out(a, full=True)

    def agent_out(a, full=False):
        out = dict(a)
        out["tools"] = json.loads(a["tools"] or "[]")
        if not full:
            out.pop("system_prompt", None)
        return out

    def provider_out(p):
        out = {k: v for k, v in p.items() if k not in ("api_key_enc",)}
        out["key_status"] = ("env var set" if os.environ.get(p["api_key_env"] or "__none__") else "env var missing") if p.get("api_key_env") \
            else ("stored" if p.get("api_key_enc") else ("not needed" if not P.KINDS[p["kind"]]["needs_key"] else "missing"))
        out["enabled"] = bool(p["enabled"])
        out["last_test_ok"] = None if p["last_test_ok"] is None else bool(p["last_test_ok"])
        return out

    def cost_of(p, tin, tout):
        if p is None or p["price_in"] is None or p["price_out"] is None:
            return None
        return round(tin / 1e6 * p["price_in"] + tout / 1e6 * p["price_out"], 6)

    # ------------------------------------------------------------ overview & catalog
    @app.route(f"{API}/overview")
    @auth
    def overview():
        runs = q("SELECT status, tokens_in, tokens_out, cost FROM m09_runs WHERE started_at>=?",
                 ((datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),))
        by = {}
        for r in runs:
            by[r["status"]] = by.get(r["status"], 0) + 1
        cost = [r["cost"] for r in runs if r["cost"] is not None]
        return jsonify({
            "providers": q("SELECT COUNT(*) n FROM m09_providers", one=True)["n"],
            "agents": q("SELECT COUNT(*) n FROM m09_agents", one=True)["n"],
            "teams": q("SELECT COUNT(*) n FROM m09_teams", one=True)["n"],
            "tools": len(TOOLS),
            "runs_7d": len(runs), "runs_by_status": by,
            "tokens_7d": sum(r["tokens_in"] or 0 for r in runs) + sum(r["tokens_out"] or 0 for r in runs),
            "cost_7d": round(sum(cost), 4) if cost else None,
            "is_admin": me().get("role") == "admin",
        }), 200

    @app.route(f"{API}/kinds")
    @auth
    def kinds():
        return jsonify({"kinds": [{"id": k, **v} for k, v in P.KINDS.items()]}), 200

    @app.route(f"{API}/tools")
    @auth
    def tools_list():
        return jsonify({"tools": [{"name": t.name, "description": t.description, "min_role": t.min_role,
                                   "parameters": t.parameters} for t in TOOLS.values()]}), 200

    # ------------------------------------------------------------ providers (admin)
    @app.route(f"{API}/providers")
    @auth
    def list_providers():
        return jsonify({"providers": [provider_out(p) for p in q("SELECT * FROM m09_providers ORDER BY name")]}), 200

    def provider_fields(d, current=None):
        kind = d.get("kind", current["kind"] if current else "")
        if kind not in P.KINDS:
            raise ValueError("Kind must be one of: " + ", ".join(P.KINDS))
        out = {"kind": kind}
        name = str(d.get("name", (current or {}).get("name", ""))).strip()
        if not NAME_RX.fullmatch(name):
            raise ValueError("Name: 2-60 letters, digits, spaces, dots, dashes or underscores.")
        out["name"] = name
        out["base_url"] = P.valid_base_url(str(d.get("base_url", "")).strip()) if "base_url" in d else (current or {}).get("base_url", "")
        if kind == "openai_compatible" and not out["base_url"]:
            raise ValueError("OpenAI-compatible providers need a base URL, for example https://api.groq.com/openai/v1 or http://localhost:11434/v1 for Ollama.")
        if kind == "bedrock":
            acct = str(d.get("aws_account", (current or {}).get("aws_account") or "")).strip()
            region = str(d.get("region", (current or {}).get("region") or "")).strip()
            if not ACCOUNT_RX.fullmatch(acct) or not store.get_aws_account(acct):
                raise ValueError("Bedrock needs a connected AWS account (pick one from the AWS accounts list).")
            if not REGION_RX.fullmatch(region):
                raise ValueError("Bedrock needs a region, for example eu-west-1.")
            out.update(aws_account=acct, region=region, api_key_env=None, api_key_enc=None)
        else:
            out.update(aws_account=None, region=None)
            env_name = str(d.get("api_key_env", "")).strip() if "api_key_env" in d else (current or {}).get("api_key_env") or ""
            if env_name and not ENV_RX.fullmatch(env_name):
                raise ValueError("Environment variable name: UPPER_CASE letters, digits and underscores.")
            if "api_key" in d and d["api_key"]:
                out.update(api_key_enc=P.encrypt_secret(cfg.JWT_SECRET, str(d["api_key"]).strip()), api_key_env=None)
            elif d.get("clear_key"):
                out.update(api_key_enc=None, api_key_env=None)
            else:
                out.update(api_key_env=env_name or None, api_key_enc=(current or {}).get("api_key_enc"))
                if env_name:
                    out["api_key_enc"] = None
            if not out["api_key_env"] and not out["api_key_enc"] and P.KINDS[kind]["needs_key"]:
                out["api_key_env"] = P.KINDS[kind]["key_env"]
        out["default_model"] = str(d.get("default_model", (current or {}).get("default_model") or "")).strip()[:200] or None
        for field in ("price_in", "price_out"):
            val = d.get(field, (current or {}).get(field))
            out[field] = None if val in (None, "") else float(val)
        out["enabled"] = 1 if d.get("enabled", (current or {}).get("enabled", 1)) else 0
        return out

    @app.route(f"{API}/providers", methods=["POST"])
    @role("admin")
    def create_provider():
        try:
            f = provider_fields(body())
        except (ValueError, TypeError) as e:
            return err(str(e))
        if q("SELECT 1 FROM m09_providers WHERE name=?", (f["name"],), one=True):
            return err("A provider with this name already exists.")
        pid = "PRV-" + secrets.token_hex(3)
        now = _now()
        cols = ["id", "created_at", "updated_at"] + list(f.keys())
        x(f"INSERT INTO m09_providers ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
          [pid, now, now] + list(f.values()))
        audit("ai_provider_created", pid, f"{f['name']} {f['kind']}")
        return jsonify({"provider": provider_out(q("SELECT * FROM m09_providers WHERE id=?", (pid,), one=True))}), 201

    @app.route(f"{API}/providers/<pid>", methods=["PUT"])
    @role("admin")
    def update_provider(pid):
        cur = q("SELECT * FROM m09_providers WHERE id=?", (pid,), one=True)
        if not cur:
            return err("Not found.", 404)
        try:
            f = provider_fields(body(), current=cur)
        except (ValueError, TypeError) as e:
            return err(str(e))
        dup = q("SELECT id FROM m09_providers WHERE name=? AND id<>?", (f["name"], pid), one=True)
        if dup:
            return err("Another provider has this name.")
        sets = ", ".join(f"{k}=?" for k in f)
        x(f"UPDATE m09_providers SET {sets}, updated_at=? WHERE id=?", list(f.values()) + [_now(), pid])
        audit("ai_provider_updated", pid)
        return jsonify({"provider": provider_out(q("SELECT * FROM m09_providers WHERE id=?", (pid,), one=True))}), 200

    @app.route(f"{API}/providers/<pid>", methods=["DELETE"])
    @role("admin")
    def delete_provider(pid):
        used = q("SELECT COUNT(*) n FROM m09_agents WHERE provider_id=?", (pid,), one=True)["n"]
        if used:
            return err(f"{used} agent(s) use this provider. Move them first or disable the provider.")
        x("DELETE FROM m09_providers WHERE id=?", (pid,))
        audit("ai_provider_deleted", pid)
        return jsonify({"deleted": pid}), 200

    @app.route(f"{API}/providers/<pid>/test", methods=["POST"])
    @role("admin")
    def test_provider(pid):
        p = q("SELECT * FROM m09_providers WHERE id=?", (pid,), one=True)
        if not p:
            return err("Not found.", 404)
        model = str(body().get("model") or p["default_model"] or "").strip()
        if not model:
            return err("Enter a model name to test with (for example a Claude, GPT or Bedrock model id you have access to).")
        t0 = _now()
        try:
            key = P.resolve_api_key(p, cfg.JWT_SECRET)
            r = P.chat(p, key, model, "Reply with exactly: OK", [{"role": "user", "content": [{"type": "text", "text": "Ping"}]}],
                       [], 16, None, bedrock_client=bedrock_client(p) if p["kind"] == "bedrock" else None)
            ok, msg = True, A.redact(r["text"])[:200] or "(empty reply)"
        except P.ProviderError as e:
            ok, msg = False, str(e)[:400]
        x("UPDATE m09_providers SET last_test=?, last_test_ok=? WHERE id=?", (t0, 1 if ok else 0, pid))
        audit("ai_provider_tested", pid, f"{model} ok={ok}")
        return jsonify({"ok": ok, "message": msg, "model": model}), 200 if ok else 502

    # ------------------------------------------------------------ agents
    def agent_fields(d, current=None):
        name = str(d.get("name", (current or {}).get("name", ""))).strip()
        if not NAME_RX.fullmatch(name):
            raise ValueError("Agent name: 2-60 letters, digits, spaces, dots, dashes or underscores.")
        pid = str(d.get("provider_id", (current or {}).get("provider_id", ""))).strip()
        if not q("SELECT 1 FROM m09_providers WHERE id=? AND enabled=1", (pid,), one=True):
            raise ValueError("Pick an enabled provider.")
        model = str(d.get("model", (current or {}).get("model", ""))).strip()
        if not MODEL_RX.fullmatch(model):
            raise ValueError("Model name is required (letters, digits and . _ : / -).")
        prompt = str(d.get("system_prompt", (current or {}).get("system_prompt", ""))).strip()
        if not 10 <= len(prompt) <= 8000:
            raise ValueError("System prompt: 10 to 8000 characters. Say what the agent is for and what it must not do.")
        tools = d.get("tools", json.loads((current or {}).get("tools") or "[]"))
        if not isinstance(tools, list) or any(t not in TOOLS for t in tools):
            raise ValueError("Tools must come from the tool catalog: " + ", ".join(TOOLS))
        steps = int(d.get("max_steps", (current or {}).get("max_steps", 6)))
        if not 1 <= steps <= A.MAX_STEPS:
            raise ValueError(f"Max steps: 1 to {A.MAX_STEPS}.")
        mtok = int(d.get("max_tokens", (current or {}).get("max_tokens", 1024)))
        if not 64 <= mtok <= 8192:
            raise ValueError("Max output tokens: 64 to 8192.")
        temp = d.get("temperature", (current or {}).get("temperature"))
        if temp in ("", None):
            temp = None
        else:
            temp = float(temp)
            if not 0 <= temp <= 2:
                raise ValueError("Temperature: 0 to 2, or empty to use the model default.")
        return {"name": name, "description": str(d.get("description", "") or "")[:300], "provider_id": pid, "model": model,
                "system_prompt": prompt, "tools": json.dumps(sorted(set(tools))), "max_steps": steps,
                "max_tokens": mtok, "temperature": temp}

    @app.route(f"{API}/agents")
    @auth
    def list_agents():
        return jsonify({"agents": [{k: v for k, v in agent_out(a).items()} for a in q("SELECT * FROM m09_agents ORDER BY name")]}), 200

    @app.route(f"{API}/agents", methods=["POST"])
    @role("developer", "approver", "operator", "security")
    def create_agent():
        try:
            f = agent_fields(body())
        except (ValueError, TypeError) as e:
            return err(str(e))
        if q("SELECT 1 FROM m09_agents WHERE name=?", (f["name"],), one=True):
            return err("An agent with this name already exists.")
        aid = "AGT-" + secrets.token_hex(3)
        now = _now()
        cols = list(f.keys())
        x(f"INSERT INTO m09_agents (id,{','.join(cols)},owner,created_at,updated_at) VALUES (?,{','.join('?' * len(cols))},?,?,?)",
          [aid] + list(f.values()) + [me()["username"], now, now])
        audit("ai_agent_created", aid, f["name"])
        return jsonify({"agent": agent_out(q("SELECT * FROM m09_agents WHERE id=?", (aid,), one=True))}), 201

    @app.route(f"{API}/agents/<aid>", methods=["PUT"])
    @role("developer", "approver", "operator", "security")
    def update_agent(aid):
        cur = q("SELECT * FROM m09_agents WHERE id=?", (aid,), one=True)
        if not cur:
            return err("Not found.", 404)
        if cur["owner"] != me()["username"] and rank(me()) < 9:
            return err("Only the owner or an admin can edit this agent.", 403)
        try:
            f = agent_fields(body(), current=cur)
        except (ValueError, TypeError) as e:
            return err(str(e))
        if q("SELECT id FROM m09_agents WHERE name=? AND id<>?", (f["name"], aid), one=True):
            return err("Another agent has this name.")
        sets = ", ".join(f"{k}=?" for k in f)
        x(f"UPDATE m09_agents SET {sets}, updated_at=? WHERE id=?", list(f.values()) + [_now(), aid])
        audit("ai_agent_updated", aid)
        return jsonify({"agent": agent_out(q("SELECT * FROM m09_agents WHERE id=?", (aid,), one=True))}), 200

    @app.route(f"{API}/agents/<aid>", methods=["DELETE"])
    @role("developer", "approver", "operator", "security")
    def delete_agent(aid):
        cur = q("SELECT * FROM m09_agents WHERE id=?", (aid,), one=True)
        if not cur:
            return err("Not found.", 404)
        if cur["owner"] != me()["username"] and rank(me()) < 9:
            return err("Only the owner or an admin can delete this agent.", 403)
        in_team = [t["name"] for t in q("SELECT name, lead_id, members FROM m09_teams") if aid == t["lead_id"] or aid in json.loads(t["members"])]
        if in_team:
            return err("Remove this agent from these teams first: " + ", ".join(in_team))
        x("DELETE FROM m09_agents WHERE id=?", (aid,))
        audit("ai_agent_deleted", aid)
        return jsonify({"deleted": aid}), 200

    # ------------------------------------------------------------ teams
    def team_fields(d, current=None):
        name = str(d.get("name", (current or {}).get("name", ""))).strip()
        if not NAME_RX.fullmatch(name):
            raise ValueError("Team name: 2-60 letters, digits, spaces, dots, dashes or underscores.")
        lead = str(d.get("lead_id", (current or {}).get("lead_id", ""))).strip()
        members = d.get("members", json.loads((current or {}).get("members") or "[]"))
        if not q("SELECT 1 FROM m09_agents WHERE id=?", (lead,), one=True):
            raise ValueError("Pick a lead agent.")
        if not isinstance(members, list) or not 1 <= len(members) <= 8:
            raise ValueError("A team needs 1 to 8 member agents.")
        if lead in members or len(set(members)) != len(members):
            raise ValueError("Members must be distinct agents other than the lead.")
        for mid in members:
            if not q("SELECT 1 FROM m09_agents WHERE id=?", (mid,), one=True):
                raise ValueError(f"Unknown member agent: {mid}")
        return {"name": name, "description": str(d.get("description", "") or "")[:300], "lead_id": lead, "members": json.dumps(members)}

    def team_out(t):
        out = dict(t)
        out["members"] = json.loads(t["members"] or "[]")
        lead = q("SELECT name FROM m09_agents WHERE id=?", (t["lead_id"],), one=True)
        out["lead_name"] = lead["name"] if lead else "(deleted)"
        out["member_names"] = [r["name"] for mid in out["members"] for r in q("SELECT name FROM m09_agents WHERE id=?", (mid,))]
        return out

    @app.route(f"{API}/teams")
    @auth
    def list_teams():
        return jsonify({"teams": [team_out(t) for t in q("SELECT * FROM m09_teams ORDER BY name")]}), 200

    @app.route(f"{API}/teams", methods=["POST"])
    @role("developer", "approver", "operator", "security")
    def create_team():
        try:
            f = team_fields(body())
        except (ValueError, TypeError) as e:
            return err(str(e))
        if q("SELECT 1 FROM m09_teams WHERE name=?", (f["name"],), one=True):
            return err("A team with this name already exists.")
        tid = "TEM-" + secrets.token_hex(3)
        now = _now()
        x("INSERT INTO m09_teams (id,name,description,lead_id,members,owner,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
          (tid, f["name"], f["description"], f["lead_id"], f["members"], me()["username"], now, now))
        audit("ai_team_created", tid, f["name"])
        return jsonify({"team": team_out(q("SELECT * FROM m09_teams WHERE id=?", (tid,), one=True))}), 201

    @app.route(f"{API}/teams/<tid>", methods=["PUT"])
    @role("developer", "approver", "operator", "security")
    def update_team(tid):
        cur = q("SELECT * FROM m09_teams WHERE id=?", (tid,), one=True)
        if not cur:
            return err("Not found.", 404)
        if cur["owner"] != me()["username"] and rank(me()) < 9:
            return err("Only the owner or an admin can edit this team.", 403)
        try:
            f = team_fields(body(), current=cur)
        except (ValueError, TypeError) as e:
            return err(str(e))
        sets = ", ".join(f"{k}=?" for k in f)
        x(f"UPDATE m09_teams SET {sets}, updated_at=? WHERE id=?", list(f.values()) + [_now(), tid])
        audit("ai_team_updated", tid)
        return jsonify({"team": team_out(q("SELECT * FROM m09_teams WHERE id=?", (tid,), one=True))}), 200

    @app.route(f"{API}/teams/<tid>", methods=["DELETE"])
    @role("developer", "approver", "operator", "security")
    def delete_team(tid):
        cur = q("SELECT * FROM m09_teams WHERE id=?", (tid,), one=True)
        if not cur:
            return err("Not found.", 404)
        if cur["owner"] != me()["username"] and rank(me()) < 9:
            return err("Only the owner or an admin can delete this team.", 403)
        x("DELETE FROM m09_teams WHERE id=?", (tid,))
        audit("ai_team_deleted", tid)
        return jsonify({"deleted": tid}), 200

    # ------------------------------------------------------------ runs
    def execute(kind, target, user, task, token_budget):
        is_team = kind == "team"
        if is_team:
            lead = load_agent(target["lead_id"])
            agent = lead
            members = [{"id": mid, "name": q("SELECT name FROM m09_agents WHERE id=?", (mid,), one=True)["name"]} for mid in target["members"]]
            team = {"members": members}
        else:
            agent, team = agent_out(target, full=True), None
        prov, key = load_provider(agent["provider_id"])
        rid = "RUN-" + secrets.token_hex(5)
        started = _now()
        x("INSERT INTO m09_runs (id,kind,target_id,target_name,username,task,status,started_at,provider_id) VALUES (?,?,?,?,?,?,?,?,?)",
          (rid, kind, target["id"], target["name"], user["username"], task, "running", started, agent["provider_id"]))
        budget = {"tokens": token_budget, "delegations": 3}
        t0 = time.time()
        result = A.run_agent(env, agent, prov, key, user, task, budget, TOOLS, team=team, depth=0, started=t0)
        finished = _now()
        cost = cost_of(prov, result["tokens_in"], result["tokens_out"])
        x("""UPDATE m09_runs SET status=?, output=?, error=?, steps=?, tokens_in=?, tokens_out=?, cost=?, finished_at=?, duration_ms=? WHERE id=?""",
          (result["status"], redact_out(result["output"]), result["error"], json.dumps(result["steps"]),
           result["tokens_in"], result["tokens_out"], cost, finished, int((time.time() - t0) * 1000), rid))
        audit("ai_run", rid, f"{kind} {target['name']} {result['status']}")
        return q("SELECT * FROM m09_runs WHERE id=?", (rid,), one=True)

    def redact_out(text):
        return A.redact(text or "")[:20000]

    def run_view(r):
        r = dict(r)
        r["steps"] = json.loads(r["steps"] or "[]")
        return r

    def parse_run(d):
        task = str(d.get("task", "")).strip()
        if not 1 <= len(task) <= 8000:
            return None, "Task: 1 to 8000 characters."
        budget = int(d.get("token_budget", A.DEFAULT_TOKEN_BUDGET))
        if not 1000 <= budget <= A.MAX_TOKEN_BUDGET:
            return None, f"Token budget: 1000 to {A.MAX_TOKEN_BUDGET}."
        return (task, budget), None

    @app.route(f"{API}/agents/<aid>/run", methods=["POST"])
    @role("developer", "approver", "operator", "security")
    def run_agent_route(aid):
        target = q("SELECT * FROM m09_agents WHERE id=?", (aid,), one=True)
        if not target:
            return err("Not found.", 404)
        parsed, msg = parse_run(body())
        if msg:
            return err(msg)
        try:
            r = execute("agent", target, me(), parsed[0], parsed[1])
        except P.ProviderError as e:
            return err(str(e), 400)
        return jsonify({"run": run_view(r)}), 200

    @app.route(f"{API}/teams/<tid>/run", methods=["POST"])
    @role("developer", "approver", "operator", "security")
    def run_team_route(tid):
        target = q("SELECT * FROM m09_teams WHERE id=?", (tid,), one=True)
        if not target:
            return err("Not found.", 404)
        target["members"] = json.loads(target["members"])
        parsed, msg = parse_run(body())
        if msg:
            return err(msg)
        try:
            r = execute("team", target, me(), parsed[0], parsed[1])
        except P.ProviderError as e:
            return err(str(e), 400)
        return jsonify({"run": run_view(r)}), 200

    @app.route(f"{API}/runs")
    @auth
    def list_runs():
        limit = min(200, int(request.args.get("limit", 50)))
        if rank(me()) < 3:  # viewers and developers see their own runs only
            rows = q("SELECT id,kind,target_name,username,task,status,tokens_in,tokens_out,cost,started_at,duration_ms FROM m09_runs WHERE username=? ORDER BY started_at DESC LIMIT ?", (me()["username"], limit))
        else:
            rows = q("SELECT id,kind,target_name,username,task,status,tokens_in,tokens_out,cost,started_at,duration_ms FROM m09_runs ORDER BY started_at DESC LIMIT ?", (limit,))
        return jsonify({"runs": rows}), 200

    @app.route(f"{API}/runs/<rid>")
    @auth
    def get_run(rid):
        r = q("SELECT * FROM m09_runs WHERE id=?", (rid,), one=True)
        if not r or (rank(me()) < 3 and r["username"] != me()["username"]):
            return err("Not found.", 404)
        return jsonify({"run": run_view(r)}), 200
