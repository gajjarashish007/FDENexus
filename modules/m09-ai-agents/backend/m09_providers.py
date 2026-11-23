"""Model providers for M09.

Every adapter converts the canonical message format into one vendor API and converts the reply back.
Canonical message: {"role": "user" | "assistant", "content": [block, ...]}
Canonical blocks (same shape as the Anthropic Messages API):
  {"type": "text", "text": "..."}
  {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
  {"type": "tool_result", "tool_use_id": "...", "content": "...", "is_error": bool}

chat() returns: {"text", "tool_calls": [{"id", "name", "input"}], "stop": "end"|"tool"|"length", "usage": {"in", "out"}}

Kinds:
  anthropic          Claude via api.anthropic.com (or a gateway that speaks the same API)
  openai             ChatGPT models via api.openai.com
  openai_compatible  any server with the OpenAI Chat Completions API: Azure OpenAI, Ollama, LM Studio,
                     vLLM, Groq, OpenRouter, Together, Mistral, and others
  bedrock            AWS Bedrock Converse API, authenticated with a connected AWS account
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from cryptography.fernet import Fernet

TIMEOUT = 90
KINDS = {
    "anthropic": {"label": "Anthropic Claude", "base_url": "https://api.anthropic.com", "key_env": "ANTHROPIC_API_KEY", "needs_key": True},
    "openai": {"label": "OpenAI ChatGPT", "base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY", "needs_key": True},
    "openai_compatible": {"label": "OpenAI-compatible (Azure OpenAI, Ollama, Groq, OpenRouter, vLLM...)", "base_url": "", "key_env": "", "needs_key": False},
    "bedrock": {"label": "AWS Bedrock", "base_url": "", "key_env": "", "needs_key": False},
}


class ProviderError(Exception):
    pass


# ----------------------------------------------------------------- secrets at rest
def encrypt_secret(master: str, text: str) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(("m09:" + master).encode()).digest())
    return Fernet(key).encrypt(text.encode()).decode()


def decrypt_secret(master: str, token: str) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(("m09:" + master).encode()).digest())
    return Fernet(key).decrypt(token.encode()).decode()


def valid_base_url(url: str) -> str:
    """https everywhere; plain http only for localhost (local model servers)."""
    if not url:
        return ""
    u = urllib.parse.urlparse(url.strip())
    if u.scheme == "https" and u.hostname:
        return url.strip().rstrip("/")
    if u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1"):
        return url.strip().rstrip("/")
    raise ValueError("Base URL must be https://, or http:// for localhost only.")


def resolve_api_key(provider: dict, master: str) -> str:
    if provider.get("api_key_env"):
        val = os.environ.get(provider["api_key_env"], "")
        if not val:
            raise ProviderError(f"Environment variable {provider['api_key_env']} is not set on the portal host.")
        return val
    if provider.get("api_key_enc"):
        return decrypt_secret(master, provider["api_key_enc"])
    return ""


# ----------------------------------------------------------------- HTTP
def _post_json(url: str, headers: dict, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise ProviderError(f"Provider returned HTTP {e.code}: {e.read(400).decode('utf-8', 'replace')}") from None
    except urllib.error.URLError as e:
        raise ProviderError(f"Cannot reach the provider: {e.reason}") from None
    except (TimeoutError, json.JSONDecodeError) as e:
        raise ProviderError(f"Provider call failed: {e}") from None


def _text_of(blocks: list) -> str:
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


# ----------------------------------------------------------------- adapters
def _anthropic(p, key, model, system, messages, tools, max_tokens, temperature):
    if not key:
        raise ProviderError("Anthropic needs an API key.")
    base = p.get("base_url") or KINDS["anthropic"]["base_url"]
    payload = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if tools:
        payload["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]
    r = _post_json(f"{base}/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"}, payload)
    calls = [{"id": b["id"], "name": b["name"], "input": b.get("input") or {}} for b in r.get("content", []) if b.get("type") == "tool_use"]
    stop = {"tool_use": "tool", "max_tokens": "length"}.get(r.get("stop_reason"), "end")
    u = r.get("usage", {})
    return {"text": _text_of(r.get("content", [])), "tool_calls": calls, "stop": stop,
            "usage": {"in": u.get("input_tokens", 0), "out": u.get("output_tokens", 0)}}


def _openai(p, key, model, system, messages, tools, max_tokens, temperature, compatible: bool):
    base = p.get("base_url") or KINDS["openai"]["base_url"]
    if not compatible and not key:
        raise ProviderError("OpenAI needs an API key.")
    msgs = [{"role": "system", "content": system}]
    for m in messages:
        if m["role"] == "assistant":
            item = {"role": "assistant", "content": _text_of(m["content"]) or None}
            calls = [{"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b["input"])}}
                     for b in m["content"] if b.get("type") == "tool_use"]
            if calls:
                item["tool_calls"] = calls
            msgs.append(item)
        else:
            text = _text_of(m["content"])
            if text:
                msgs.append({"role": "user", "content": text})
            for b in m["content"]:
                if b.get("type") == "tool_result":
                    msgs.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
    payload = {"model": model, "messages": msgs}
    # Newer OpenAI models reject max_tokens and non-default temperature; compatible servers still expect max_tokens.
    if compatible:
        payload["max_tokens"] = max_tokens
    else:
        payload["max_completion_tokens"] = max_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    if tools:
        payload["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}} for t in tools]
    headers = {"authorization": f"Bearer {key}"} if key else {}
    r = _post_json(f"{base}/chat/completions", headers, payload)
    choice = (r.get("choices") or [{}])[0]
    msg = choice.get("message", {})
    calls = []
    for tc in msg.get("tool_calls") or []:
        try:
            args = json.loads(tc.get("function", {}).get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append({"id": tc.get("id", ""), "name": tc.get("function", {}).get("name", ""), "input": args if isinstance(args, dict) else {}})
    stop = {"tool_calls": "tool", "function_call": "tool", "length": "length"}.get(choice.get("finish_reason"), "end")
    u = r.get("usage", {})
    return {"text": msg.get("content") or "", "tool_calls": calls, "stop": stop,
            "usage": {"in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0)}}


def _bedrock(client, model, system, messages, tools, max_tokens, temperature):
    msgs = []
    for m in messages:
        blocks = []
        for b in m["content"]:
            if b["type"] == "text":
                blocks.append({"text": b["text"]})
            elif b["type"] == "tool_use":
                blocks.append({"toolUse": {"toolUseId": b["id"], "name": b["name"], "input": b["input"]}})
            elif b["type"] == "tool_result":
                blocks.append({"toolResult": {"toolUseId": b["tool_use_id"], "content": [{"text": b["content"] or "(empty)"}],
                                              "status": "error" if b.get("is_error") else "success"}})
        msgs.append({"role": m["role"], "content": blocks})
    kwargs = {"modelId": model, "messages": msgs, "system": [{"text": system}],
              "inferenceConfig": {"maxTokens": max_tokens}}
    if temperature is not None:
        kwargs["inferenceConfig"]["temperature"] = temperature
    if tools:
        kwargs["toolConfig"] = {"tools": [{"toolSpec": {"name": t["name"], "description": t["description"],
                                                       "inputSchema": {"json": t["parameters"]}}} for t in tools]}
    try:
        r = client.converse(**kwargs)
    except Exception as e:  # botocore errors carry the AWS message
        raise ProviderError(f"Bedrock call failed: {str(e)[:400]}") from None
    out = r.get("output", {}).get("message", {}).get("content", [])
    calls = [{"id": b["toolUse"]["toolUseId"], "name": b["toolUse"]["name"], "input": b["toolUse"].get("input") or {}} for b in out if "toolUse" in b]
    text = "".join(b.get("text", "") for b in out if "text" in b)
    stop = {"tool_use": "tool", "max_tokens": "length"}.get(r.get("stopReason"), "end")
    u = r.get("usage", {})
    return {"text": text, "tool_calls": calls, "stop": stop,
            "usage": {"in": u.get("inputTokens", 0), "out": u.get("outputTokens", 0)}}


# ----------------------------------------------------------------- dispatch
def chat(provider: dict, api_key: str, model: str, system: str, messages: list, tools: list,
         max_tokens: int, temperature, bedrock_client=None) -> dict:
    kind = provider["kind"]
    if kind == "anthropic":
        return _anthropic(provider, api_key, model, system, messages, tools, max_tokens, temperature)
    if kind == "openai":
        return _openai(provider, api_key, model, system, messages, tools, max_tokens, temperature, compatible=False)
    if kind == "openai_compatible":
        if not provider.get("base_url"):
            raise ProviderError("OpenAI-compatible providers need a base URL, for example https://api.groq.com/openai/v1")
        return _openai(provider, api_key, model, system, messages, tools, max_tokens, temperature, compatible=True)
    if kind == "bedrock":
        if bedrock_client is None:
            raise ProviderError("Bedrock needs a connected AWS account.")
        return _bedrock(bedrock_client, model, system, messages, tools, max_tokens, temperature)
    raise ProviderError(f"Unknown provider kind: {kind}")
