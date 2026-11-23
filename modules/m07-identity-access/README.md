# M07 Identity & Access Management
SSO, MFA, least privilege, just-in-time access and access reviews for people and workloads.

Owner: Identity & Access · Phase: P2 · UI: `identity.html` (sidebar → Security → Identity & access)

## Capabilities
| Capability | Status | Notes |
|---|---|---|
| SSO | live | OIDC single sign-on (authorization code + PKCE, ID token signature checked against the IdP JWKS). Configure on the Identity page. |
| MFA | live | TOTP (RFC 6238) enrolment, two-step login, admin reset, required per role (default admin). |
| SAML and OIDC | partial | OIDC is live. SAML 2.0 is not supported; use an OIDC app in your IdP (Entra ID, Okta, Google, Keycloak all offer one). |
| SCIM provisioning | live | SCIM 2.0 /scim/v2/Users (list, filter, create, replace, patch, delete=disable) with a bearer token. Never modifies admins. |
| RBAC | live | Six portal roles enforced on every API call; temporary role elevation via JIT. (with M01) |
| ABAC | live | Attribute rules: team must own the resource, production changes need an MFA or SSO session. Checked by M02 before changes. |
| IAM role management | live | IAM roles from the account data cache with trust analysis (anyone, cross-account, missing external ID, unused 90+ days) and live policy view. |
| Just-in-time access | live | Request a higher role for 1-N hours with a reason; another approver or admin approves; no self-approval. |
| Privileged access management | live | Admin and operator access only through time-boxed JIT elevation, MFA enforcement, session marked elevated and audited. |
| Temporary permissions | live | JIT grants end automatically at expiry; service tokens always expire (1-365 days). |
| Access expiration | live | Per-user access end date; the account is disabled and its sessions revoked when it passes. |
| Access reviews | live | Review campaigns over all users: keep or revoke each, revocations applied on close. |
| Approval workflows | live | Requests, infrastructure changes and JIT elevation need a different approver. (with M01/M03/M07) |
| Automatic revocation | live | Background sweep every 60 s ends expired JIT grants, user access and service tokens; idle sessions sign out. |
| Service identities | live | Named service tokens (fdx_...), stored hashed, roles viewer/developer/operator only, expire in 1-365 days, revocable, last-used tracked. |
| Workload identity | live | Per EKS cluster: OIDC issuer, Pod Identity associations and IRSA roles, read live. |
| Session auditing | live | Every sign-in recorded with method, IP, client, last activity; users and admins can revoke sessions. |

## How it plugs into the portal
- `register(app, ctx)` in `backend/module.py` adds hooks to M01 (`ctx.identity`):
  `on_login` (MFA step), `on_token` (session record), `on_auth` (revoked/idle sessions, access expiry, JIT elevation), `resolve_token` (`fdx_` service tokens).
- `ctx.services["abac"]` is called by M02 before infrastructure changes.
- A background thread sweeps every 60 s: expired JIT grants, user access end dates, service tokens.

## API
`/api/m07/...`: overview, settings, sessions, mfa/{enroll,verify,disable,login}, jit, users/<id>/expiry, reviews, tokens, sso, sso/start, sso/callback, scim/token, iam/roles, workload.
SCIM 2.0: `/scim/v2/ServiceProviderConfig`, `/scim/v2/Users`, `/scim/v2/Users/<id>` (bearer token from the Identity page).

## SSO setup (OIDC)
1. Create an OIDC web app in your IdP with redirect URI `http://<portal-host>:8077/api/m07/sso/callback`.
2. Set the client secret in env `M07_OIDC_CLIENT_SECRET` before `./start-portal.sh` (it is never stored in the database).
3. On Identity → SSO, enter issuer, client ID, redirect URI, and optionally a group → role map (groups claim, default `groups`).
4. Existing users are matched by IdP subject, then by email. New users are created with the mapped role or the default role (never admin by default) when auto-provision is on.

## Not supported
- SAML 2.0 (use OIDC).
- Hardware keys / WebAuthn (TOTP only).
