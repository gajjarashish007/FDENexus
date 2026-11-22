"""Policy-as-code for infrastructure changes.

Each rule is a plain function over (component, vars, ctx) returning a list of findings.
A "deny" finding blocks the change. A "warn" finding forces human approval.
Rules are evaluated before approval, so nobody (including AI agents) can merge a
change that violates a deny rule.
"""
from __future__ import annotations

import ipaddress
import re

RULES: list[dict] = []

SUPPORTED_EKS = ["1.35", "1.36", "1.37"]
SANDBOX_TYPES = re.compile(r"^(t3|t3a|t4g)\.(nano|micro|small|medium)$")
BUCKET_RE = re.compile(r"^(?!xn--)(?!.*\.\.)[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


def rule(rid: str, severity: str, title: str, frameworks: list[str]):
    def deco(fn):
        RULES.append({"id": rid, "severity": severity, "title": title, "frameworks": frameworks, "fn": fn})
        return fn
    return deco


def _f(r, msg):
    return {"rule": r, "message": msg}


@rule("FDE-001", "deny", "Owning team is required on every resource", ["SOC 2 CC6.1", "ISO 27001 A.5.9"])
def _team(component, v, ctx):
    return [] if str(ctx.get("team", "")).strip() else [_f("FDE-001", "Set the owning team.")]


@rule("FDE-002", "deny", "No SSH or RDP open to the internet", ["CIS AWS 5.2", "NIST CSF PR.AA"])
def _ssh(component, v, ctx):
    if component != "ec2-instance":
        return []
    ports = {int(p) for p in v.get("allowed_ports", [])}
    cidr = v.get("allowed_cidr") or ""
    if ports & {22, 3389} and cidr in ("0.0.0.0/0", "::/0"):
        return [_f("FDE-002", "Ports 22/3389 must not be open to 0.0.0.0/0. Use Session Manager (already enabled).")]
    return []


@rule("FDE-003", "warn", "Production instances should not sit in public subnets", ["CIS AWS 5.x"])
def _ec2_public(component, v, ctx):
    if component == "ec2-instance" and ctx["tier"] == "production" and v.get("subnet_tier") == "public":
        return [_f("FDE-003", "Production instance in a public subnet. Prefer a private subnet behind a load balancer.")]
    return []


@rule("FDE-004", "deny", "Public S3 website endpoints are not allowed in production", ["CIS AWS 2.1.4", "SOC 2 CC6.6"])
def _s3_public_prod(component, v, ctx):
    if component == "s3-static-website" and v.get("hosting") == "s3-website":
        if ctx["tier"] == "production":
            return [_f("FDE-004", "Use CloudFront hosting in production (bucket stays private, HTTPS).")]
    return []


@rule("FDE-005", "warn", "Public S3 website endpoint (HTTP only, public bucket)", ["CIS AWS 2.1.4"])
def _s3_public(component, v, ctx):
    if component == "s3-static-website" and v.get("hosting") == "s3-website" and ctx["tier"] != "production":
        return [_f("FDE-005", "The bucket becomes publicly readable and the site is HTTP only.")]
    return []


@rule("FDE-006", "deny", "EKS public endpoint must be restricted to known CIDRs", ["CIS EKS 5.4.1"])
def _eks_endpoint(component, v, ctx):
    if component == "eks-cluster" and v.get("endpoint_public_access"):
        cidrs = v.get("public_access_cidrs") or []
        if not cidrs or any(c in ("0.0.0.0/0", "::/0") for c in cidrs):
            return [_f("FDE-006", "Public API endpoint needs an allowlist of office/VPN CIDRs (not 0.0.0.0/0).")]
    return []


@rule("FDE-007", "deny", "Production EKS needs at least 2 nodes", ["Reliability"])
def _eks_nodes(component, v, ctx):
    if component == "eks-cluster" and ctx["tier"] == "production" and int(v.get("node_min", 0)) < 2:
        return [_f("FDE-007", "Set node_min to 2 or more in production.")]
    return []


@rule("FDE-008", "warn", "EKS version should be a currently supported release", ["Patch management"])
def _eks_version(component, v, ctx):
    if component == "eks-cluster" and str(v.get("cluster_version")) not in SUPPORTED_EKS:
        return [_f("FDE-008", f"Use one of {', '.join(SUPPORTED_EKS)}.")]
    return []


@rule("FDE-009", "deny", "Production DynamoDB tables need point-in-time recovery", ["SOC 2 A1.2", "ISO 27001 A.8.13"])
def _ddb_pitr(component, v, ctx):
    if component == "dynamodb-table" and ctx["tier"] == "production" and not v.get("point_in_time_recovery", True):
        return [_f("FDE-009", "Turn on point-in-time recovery.")]
    return []


@rule("FDE-010", "deny", "Sandbox environments are limited to small burstable instances", ["FinOps"])
def _sandbox_size(component, v, ctx):
    if ctx["tier"] != "sandbox":
        return []
    types = []
    if component == "ec2-instance":
        types = [v.get("instance_type", "")]
    elif component == "eks-cluster":
        types = v.get("node_instance_types", [])
    bad = [t for t in types if not SANDBOX_TYPES.match(str(t))]
    return [_f("FDE-010", f"{', '.join(bad)} not allowed in sandbox. Use t3/t3a/t4g up to medium.")] if bad else []


@rule("FDE-011", "deny", "VPC CIDRs must not overlap in the same account", ["Network design"])
def _cidr_overlap(component, v, ctx):
    if component != "vpc" or not v.get("cidr"):
        return []
    try:
        mine = ipaddress.ip_network(v["cidr"])
    except ValueError:
        return [_f("FDE-011", f"{v['cidr']} is not a valid CIDR.")]
    out = []
    for env, other in ctx.get("account_cidrs", {}).items():
        try:
            if mine.overlaps(ipaddress.ip_network(other)):
                out.append(_f("FDE-011", f"{v['cidr']} overlaps {other} used by environment {env}."))
        except ValueError:
            continue
    return out


@rule("FDE-012", "warn", "Production NAT should be one per AZ", ["Reliability"])
def _nat(component, v, ctx):
    if component == "vpc" and ctx["tier"] == "production" and v.get("nat_mode") != "per-az":
        return [_f("FDE-012", "A single NAT gateway is a single-AZ dependency for all private subnets.")]
    return []


@rule("FDE-013", "warn", "Internet-facing load balancers should use HTTPS", ["SOC 2 CC6.7"])
def _alb_https(component, v, ctx):
    if component == "alb" and v.get("scheme") == "internet-facing" and not v.get("certificate_domain"):
        return [_f("FDE-013", "No certificate set: the load balancer serves plain HTTP.")]
    return []


@rule("FDE-014", "deny", "S3 bucket names must be DNS compliant", ["AWS naming"])
def _bucket(component, v, ctx):
    if component in ("s3-bucket", "s3-static-website") and not BUCKET_RE.match(str(v.get("bucket_name", ""))):
        return [_f("FDE-014", "3-63 chars, lowercase letters, digits, dots and hyphens.")]
    return []


@rule("FDE-015", "warn", "Closing an AWS account on delete is irreversible for 90 days", ["Change safety"])
def _close(component, v, ctx):
    if component == "aws-account" and v.get("close_on_deletion"):
        return [_f("FDE-015", "close_on_deletion=true closes the account when the change is destroyed.")]
    return []


@rule("FDE-016", "deny", "Flow logs are required outside sandbox", ["CIS AWS 3.7", "NIST CSF DE.CM"])
def _flow(component, v, ctx):
    if component == "vpc" and ctx["tier"] in ("staging", "production") and not v.get("flow_logs", True):
        return [_f("FDE-016", "Enable VPC flow logs.")]
    return []


def evaluate(component: str, v: dict, ctx: dict) -> dict:
    findings = []
    for r in RULES:
        for f in r["fn"](component, v, ctx):
            findings.append({**f, "severity": r["severity"], "title": r["title"], "frameworks": r["frameworks"]})
    return {
        "passed": not any(f["severity"] == "deny" for f in findings),
        "warnings": sum(1 for f in findings if f["severity"] == "warn"),
        "denies": sum(1 for f in findings if f["severity"] == "deny"),
        "findings": findings,
        "rules_evaluated": len(RULES),
    }


def catalog() -> list[dict]:
    return [{k: v for k, v in r.items() if k != "fn"} for r in RULES]
