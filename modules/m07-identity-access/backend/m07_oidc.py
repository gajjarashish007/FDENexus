"""OpenID Connect sign-in (authorization code + PKCE). Works with Okta, Entra ID, Google, Keycloak,
AWS IAM Identity Center applications, Auth0 and any standards-compliant IdP.

The client secret is read ONLY from the environment (M07_OIDC_CLIENT_SECRET), never stored."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import urllib.request

import jwt


class OIDCError(Exception):
    pass


_cache: dict[str, tuple[float, dict]] = {}


def _get_json(url: str, timeout: int = 10) -> dict:
    if not (url.startswith("https://") or url.startswith("http://localhost") or url.startswith("http://127.0.0.1")):
        raise OIDCError("The IdP must use https.")
    hit = _cache.get(url)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=timeout) as r:
            data = json.loads(r.read())
    except Exception as e:
        raise OIDCError(f"Could not read {url}: {str(e)[:160]}") from None
    _cache[url] = (time.time() + 600, data)
    return data


def discovery(issuer: str) -> dict:
    d = _get_json(issuer.rstrip("/") + "/.well-known/openid-configuration")
    for k in ("authorization_endpoint", "token_endpoint", "jwks_uri", "issuer"):
        if k not in d:
            raise OIDCError(f"IdP discovery document has no {k}.")
    return d


def client_secret() -> str:
    return os.environ.get("M07_OIDC_CLIENT_SECRET", "")


def start(cfg: dict) -> tuple[str, dict]:
    d = discovery(cfg["issuer"])
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    q = {"response_type": "code", "client_id": cfg["client_id"], "redirect_uri": cfg["redirect_uri"],
         "scope": cfg.get("scopes") or "openid email profile", "state": state, "nonce": nonce,
         "code_challenge": challenge, "code_challenge_method": "S256"}
    return d["authorization_endpoint"] + ("&" if "?" in d["authorization_endpoint"] else "?") + urllib.parse.urlencode(q), \
        {"state": state, "nonce": nonce, "verifier": verifier}


def finish(cfg: dict, code: str, saved: dict) -> dict:
    d = discovery(cfg["issuer"])
    body = {"grant_type": "authorization_code", "code": code, "redirect_uri": cfg["redirect_uri"],
            "client_id": cfg["client_id"], "code_verifier": saved["verifier"]}
    if client_secret():
        body["client_secret"] = client_secret()
    req = urllib.request.Request(d["token_endpoint"], data=urllib.parse.urlencode(body).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            tok = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise OIDCError(f"Token exchange failed ({e.code}): {e.read().decode(errors='replace')[:200]}") from None
    except Exception as e:
        raise OIDCError(f"Token exchange failed: {str(e)[:160]}") from None
    idt = tok.get("id_token")
    if not idt:
        raise OIDCError("The IdP returned no id_token.")
    try:
        key = jwt.PyJWKClient(d["jwks_uri"]).get_signing_key_from_jwt(idt).key
        claims = jwt.decode(idt, key, algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "PS256"],
                            audience=cfg["client_id"], issuer=d["issuer"], leeway=60)
    except jwt.PyJWTError as e:
        raise OIDCError(f"ID token rejected: {e}") from None
    if claims.get("nonce") != saved["nonce"]:
        raise OIDCError("ID token nonce mismatch.")
    return claims
