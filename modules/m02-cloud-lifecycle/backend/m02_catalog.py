"""M02 static knowledge: regions, CIDR planning and the GUI schema for each resource type.

The schema drives the launch wizard in the browser. Every field maps 1:1 to a Terraform
variable of the component in M03's registry, so what the user picks is exactly what the
Atmos stack contains.
"""
from __future__ import annotations

import ipaddress
import math
import re

# Region display names and AZ suffixes. In live mode the portal reads real AZs per account
# (describe_availability_zones): AZ letters map to different physical zones per account,
# so the zone ID (e.g. use1-az1) is what to compare across accounts.
REGIONS = {
    "us-east-1": ("US East (N. Virginia)", "abcdef"),
    "us-east-2": ("US East (Ohio)", "abc"),
    "us-west-1": ("US West (N. California)", "ac"),
    "us-west-2": ("US West (Oregon)", "abcd"),
    "ca-central-1": ("Canada (Central)", "abd"),
    "eu-west-1": ("Europe (Ireland)", "abc"),
    "eu-west-2": ("Europe (London)", "abc"),
    "eu-central-1": ("Europe (Frankfurt)", "abc"),
    "eu-north-1": ("Europe (Stockholm)", "abc"),
    "ap-south-1": ("Asia Pacific (Mumbai)", "abc"),
    "ap-southeast-1": ("Asia Pacific (Singapore)", "abc"),
    "ap-southeast-2": ("Asia Pacific (Sydney)", "abc"),
    "ap-northeast-1": ("Asia Pacific (Tokyo)", "acd"),
    "sa-east-1": ("South America (Sao Paulo)", "abc"),
}
TIERS = ["sandbox", "development", "staging", "production"]
ENV_RE = re.compile(r"^[a-z][a-z0-9-]{2,31}$")


def static_regions() -> list[dict]:
    return [{"code": c, "name": n, "azs": [{"name": c + s, "zone_id": None} for s in sfx], "source": "built-in"}
            for c, (n, sfx) in REGIONS.items()]


def plan_cidr(cidr: str, az_count: int) -> dict:
    """Public subnets from the first quarter of the VPC, private subnets from the second half."""
    net = ipaddress.ip_network(cidr, strict=True)
    if net.version != 4 or not 16 <= net.prefixlen <= 24:
        raise ValueError("Use an IPv4 CIDR between /16 and /24.")
    if not net.is_private:
        raise ValueError("Use a private (RFC 1918) range.")
    if not 1 <= az_count <= 6:
        raise ValueError("Pick 1 to 6 availability zones.")
    bits = max(1, math.ceil(math.log2(az_count))) if az_count > 1 else 0
    public_block = list(net.subnets(prefixlen_diff=2))[0]
    private_block = list(net.subnets(prefixlen_diff=1))[1]
    pub = list(public_block.subnets(prefixlen_diff=bits))[:az_count] if bits else [public_block]
    pri = list(private_block.subnets(prefixlen_diff=bits))[:az_count] if bits else [private_block]
    return {"cidr": str(net), "public": [str(s) for s in pub], "private": [str(s) for s in pri],
            "public_hosts": pub[0].num_addresses - 5, "private_hosts": pri[0].num_addresses - 5,
            "reserved_for_growth": str(list(net.subnets(prefixlen_diff=2))[1])}


def suggest_cidr(used: list[str]) -> str:
    nets = []
    for u in used:
        try:
            nets.append(ipaddress.ip_network(u))
        except ValueError:
            pass
    for i in range(10, 256, 10):
        cand = ipaddress.ip_network(f"10.{i}.0.0/16")
        if not any(cand.overlaps(n) for n in nets):
            return str(cand)
    return "10.200.0.0/16"


def _ch(value, label, desc="", badge=""):
    return {"value": value, "label": label, "desc": desc, "badge": badge}


EC2_TYPES = [
    _ch("t3.micro", "t3.micro", "2 vCPU · 1 GiB", "$7.59/mo"), _ch("t3.small", "t3.small", "2 vCPU · 2 GiB", "$15.18/mo"),
    _ch("t3.medium", "t3.medium", "2 vCPU · 4 GiB", "$30.37/mo"), _ch("t4g.small", "t4g.small", "2 vCPU · 2 GiB · Graviton", "$12.26/mo"),
    _ch("m7i.large", "m7i.large", "2 vCPU · 8 GiB · general", "$73.58/mo"), _ch("c7i.large", "c7i.large", "2 vCPU · 4 GiB · compute", "$65.19/mo"),
    _ch("r7i.large", "r7i.large", "2 vCPU · 16 GiB · memory", "$96.58/mo"),
]
NODE_TYPES = [
    _ch("t3.medium", "t3.medium", "2 vCPU · 4 GiB (sandbox)", "$30.37/mo"), _ch("m6i.large", "m6i.large", "2 vCPU · 8 GiB", "$70.08/mo"),
    _ch("m7g.large", "m7g.large", "2 vCPU · 8 GiB · Graviton", "$59.57/mo"), _ch("m6i.xlarge", "m6i.xlarge", "4 vCPU · 16 GiB", "$140.16/mo"),
]


def F(name, label, ftype="text", **kw):
    return {"name": name, "label": label, "type": ftype, **kw}


RESOURCE_TYPES = {
    "ec2-instance": {
        "label": "EC2 instance", "icon": "bi-server", "category": "Compute", "name_field": "instance_name",
        "description": "A virtual server in the environment VPC. Session Manager access, IMDSv2, encrypted disk.",
        "fields": [
            F("instance_name", "Instance name", required=True, placeholder="web-01", pattern="^[a-z0-9][a-z0-9-]{0,39}$"),
            F("os", "Operating system", "choice", default="amazon-linux", options=[
                _ch("amazon-linux", "Amazon Linux 2023", "Recommended, patched by AWS"), _ch("ubuntu", "Ubuntu 22.04 LTS", "Canonical"),
                _ch("windows", "Windows Server 2022", "License included")]),
            F("instance_type", "Size", "choice", default="t3.micro", options=EC2_TYPES),
            F("volume_gb", "Root volume (GB)", "number", default=20, min=8, max=1000),
            F("subnet_tier", "Subnet", "choice", default="private", options=[
                _ch("private", "Private", "No public IP; reach it through a load balancer or Session Manager"),
                _ch("public", "Public", "Gets a public IP")]),
            F("allowed_ports", "Open inbound ports", "multi", default=[], options=[
                _ch(80, "80 HTTP"), _ch(443, "443 HTTPS"), _ch(8080, "8080 App"), _ch(22, "22 SSH"), _ch(3389, "3389 RDP")]),
            F("allowed_cidr", "Allowed source CIDR", placeholder="empty = VPC only", help="Leave empty to allow only the VPC."),
            F("key_name", "Key pair (optional)", placeholder="Session Manager works without a key"),
            F("user_data", "User data script (optional)", "textarea", placeholder="#!/bin/bash"),
        ]},
    "dynamodb-table": {
        "label": "DynamoDB table", "icon": "bi-table", "category": "Database", "name_field": "table_name",
        "description": "Serverless key-value table. Encrypted, point-in-time recovery, deletion protection in production.",
        "fields": [
            F("table_name", "Table name", required=True, placeholder="orders", pattern="^[A-Za-z0-9_.-]{3,255}$"),
            F("hash_key", "Partition key", required=True, placeholder="pk"),
            F("hash_key_type", "Partition key type", "choice", default="S", options=[
                _ch("S", "String"), _ch("N", "Number"), _ch("B", "Binary")]),
            F("range_key", "Sort key (optional)", placeholder="sk"),
            F("range_key_type", "Sort key type", "choice", default="S", show_if={"range_key": "*"},
              options=[_ch("S", "String"), _ch("N", "Number"), _ch("B", "Binary")]),
            F("billing_mode", "Capacity", "choice", default="PAY_PER_REQUEST", options=[
                _ch("PAY_PER_REQUEST", "On-demand", "Pay per request, scales to zero"),
                _ch("PROVISIONED", "Provisioned", "Fixed read/write units, cheaper at steady load")]),
            F("read_capacity", "Read capacity units", "number", default=5, min=1, max=40000, show_if={"billing_mode": "PROVISIONED"}),
            F("write_capacity", "Write capacity units", "number", default=5, min=1, max=40000, show_if={"billing_mode": "PROVISIONED"}),
            F("ttl_attribute", "TTL attribute (optional)", placeholder="expires_at"),
            F("point_in_time_recovery", "Point-in-time recovery", "bool", default=True),
            F("stream_enabled", "DynamoDB Streams", "bool", default=False),
        ]},
    "s3-static-website": {
        "label": "S3 static website", "icon": "bi-globe", "category": "Storage", "name_field": "bucket_name",
        "description": "Host a static site. CloudFront keeps the bucket private and serves HTTPS.",
        "fields": [
            F("bucket_name", "Bucket name", required=True, placeholder="acme-marketing-site"),
            F("hosting", "Hosting", "choice", default="cloudfront", options=[
                _ch("cloudfront", "CloudFront + private bucket", "HTTPS, security headers, global cache", "recommended"),
                _ch("s3-website", "S3 website endpoint", "Public bucket, HTTP only, not allowed in production")]),
            F("index_document", "Index document", default="index.html"),
            F("error_document", "Error document", default="error.html"),
            F("price_class", "CloudFront coverage", "choice", default="PriceClass_100", show_if={"hosting": "cloudfront"}, options=[
                _ch("PriceClass_100", "North America and Europe", "Lowest cost"),
                _ch("PriceClass_200", "+ Asia, Middle East, Africa"), _ch("PriceClass_All", "All edge locations")]),
        ]},
    "s3-bucket": {
        "label": "S3 bucket", "icon": "bi-bucket", "category": "Storage", "name_field": "bucket_name",
        "description": "Private object storage: TLS only, encrypted, versioned, lifecycle rules.",
        "fields": [
            F("bucket_name", "Bucket name", required=True, placeholder="acme-payments-data"),
            F("versioning", "Versioning", "bool", default=True),
            F("encryption", "Encryption", "choice", default="SSE-S3", options=[
                _ch("SSE-S3", "SSE-S3", "AWS managed AES-256"), _ch("SSE-KMS", "SSE-KMS", "aws/s3 KMS key, CloudTrail visibility")]),
            F("noncurrent_days", "Delete old versions after (days)", "number", default=30, min=1, max=3650, show_if={"versioning": True}),
        ]},
    "efs": {
        "label": "EFS file system", "icon": "bi-hdd-stack", "category": "Storage", "name_field": "fs_name",
        "description": "Shared NFS storage with mount targets in every private subnet.",
        "fields": [
            F("fs_name", "Name", required=True, placeholder="shared"),
            F("performance_mode", "Performance", "choice", default="generalPurpose", options=[
                _ch("generalPurpose", "General purpose", "Lowest latency"), _ch("maxIO", "Max I/O", "Highly parallel workloads")]),
            F("throughput_mode", "Throughput", "choice", default="elastic", options=[
                _ch("elastic", "Elastic", "Scales with demand"), _ch("bursting", "Bursting", "Scales with stored size")]),
            F("transition_to_ia", "Move to Infrequent Access", "choice", default="AFTER_30_DAYS", options=[
                _ch("AFTER_7_DAYS", "After 7 days"), _ch("AFTER_30_DAYS", "After 30 days"), _ch("AFTER_90_DAYS", "After 90 days")]),
            F("backup", "AWS Backup", "bool", default=True),
        ]},
    "eks-cluster": {
        "label": "EKS cluster", "icon": "bi-boxes", "category": "Kubernetes", "name_field": "cluster_name",
        "description": "Managed Kubernetes: private API by default, KMS secrets, audit logs, managed nodes.",
        "fields": [
            F("cluster_name", "Cluster name", required=True, placeholder="apps"),
            F("cluster_version", "Kubernetes version", "choice", default="1.37", options=[
                _ch("1.37", "1.37", "Latest"), _ch("1.36", "1.36"), _ch("1.35", "1.35")]),
            F("endpoint_public_access", "Public API endpoint", "bool", default=False),
            F("public_access_cidrs", "Allowed CIDRs for the public API", "list", default=[], show_if={"endpoint_public_access": True},
              placeholder="203.0.113.0/24, 198.51.100.10/32"),
            F("node_instance_types", "Node size", "choice", default="m6i.large", options=NODE_TYPES, as_list=True),
            F("capacity_type", "Capacity", "choice", default="ON_DEMAND", options=[
                _ch("ON_DEMAND", "On-demand"), _ch("SPOT", "Spot", "Up to ~65% cheaper, can be interrupted")]),
            F("node_min", "Min nodes", "number", default=2, min=1, max=100),
            F("node_desired", "Desired nodes", "number", default=2, min=1, max=100),
            F("node_max", "Max nodes", "number", default=4, min=1, max=200),
            F("node_disk_gb", "Node disk (GB)", "number", default=50, min=20, max=1000),
        ]},
    "alb": {
        "label": "Application load balancer", "icon": "bi-diagram-3", "category": "Networking", "name_field": "lb_name",
        "description": "Layer 7 load balancer with HTTPS and an IP target group.",
        "fields": [
            F("lb_name", "Name", required=True, placeholder="web"),
            F("scheme", "Scheme", "choice", default="internet-facing", options=[
                _ch("internet-facing", "Internet-facing", "Public subnets"), _ch("internal", "Internal", "Private subnets, VPC only")]),
            F("certificate_domain", "Certificate domain (optional)", placeholder="app.example.com",
              help="An ISSUED ACM certificate in this region. Empty = HTTP only."),
            F("target_port", "Target port", "number", default=80, min=1, max=65535),
            F("health_check_path", "Health check path", default="/"),
            F("idle_timeout", "Idle timeout (s)", "number", default=60, min=1, max=4000),
        ]},
    "route53-zone": {
        "label": "DNS hosted zone", "icon": "bi-signpost-2", "category": "DNS", "name_field": "domain_name",
        "description": "Public or private Route 53 zone.",
        "fields": [
            F("domain_name", "Domain", required=True, placeholder="payments.example.com"),
            F("private_zone", "Private zone (this VPC only)", "bool", default=False),
        ]},
    "acm-certificate": {
        "label": "TLS certificate", "icon": "bi-shield-lock", "category": "DNS", "name_field": "domain_name",
        "description": "Free public ACM certificate with DNS validation.",
        "fields": [
            F("domain_name", "Domain", required=True, placeholder="app.example.com"),
            F("subject_alternative_names", "Extra names (optional)", "list", default=[], placeholder="www.example.com"),
            F("validation", "Validation", "choice", default="route53", options=[
                _ch("route53", "Automatic (Route 53)", "Zone must be in this account"), _ch("manual", "Manual DNS records")]),
            F("zone_domain", "Hosted zone", show_if={"validation": "route53"}, placeholder="example.com"),
        ]},
}


def instance_name(rtype: str, values: dict) -> str:
    raw = str(values.get(RESOURCE_TYPES[rtype]["name_field"], "")).lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")[:40]
    return f"{rtype}/{slug}"


def build_vars(rtype: str, values: dict) -> tuple[dict, list[str]]:
    """Map wizard values to component variables, honoring show_if and required."""
    spec = RESOURCE_TYPES[rtype]
    out, errs = {}, []
    for f in spec["fields"]:
        cond = f.get("show_if")
        if cond:
            k, want = next(iter(cond.items()))
            have = values.get(k, next((x.get("default") for x in spec["fields"] if x["name"] == k), None))
            if (want == "*" and not have) or (want != "*" and have != want):
                continue
        val = values.get(f["name"], f.get("default"))
        if val in (None, "", []) :
            if f.get("required"):
                errs.append(f"{f['label']} is required.")
            continue
        if f["type"] == "number":
            try:
                val = float(val)
                val = int(val) if val.is_integer() else val
            except (TypeError, ValueError):
                errs.append(f"{f['label']} must be a number.")
                continue
            if ("min" in f and val < f["min"]) or ("max" in f and val > f["max"]):
                errs.append(f"{f['label']} must be between {f.get('min')} and {f.get('max')}.")
                continue
        elif f["type"] == "bool":
            val = val is True or str(val).lower() == "true"
        elif f["type"] == "choice":
            allowed = [o["value"] for o in f["options"]]
            if val not in allowed:
                errs.append(f"{f['label']}: pick one of {', '.join(map(str, allowed))}.")
                continue
            if f.get("as_list"):
                val = [val]
        elif f["type"] == "multi":
            allowed = {o["value"] for o in f["options"]}
            val = [int(x) if str(x).isdigit() else x for x in (val if isinstance(val, list) else [val])]
            if any(x not in allowed for x in val):
                errs.append(f"{f['label']}: unsupported option.")
                continue
        elif f["type"] == "list":
            val = val if isinstance(val, list) else [x.strip() for x in str(val).split(",") if x.strip()]
        else:
            val = str(val).strip()
            if f.get("pattern") and not re.fullmatch(f["pattern"], val):
                errs.append(f"{f['label']} has an invalid format.")
                continue
            if len(val) > 16000:
                errs.append(f"{f['label']} is too long.")
                continue
        out[f["name"]] = val
    if rtype == "eks-cluster" and not errs and not out.get("node_min", 0) <= out.get("node_desired", 0) <= out.get("node_max", 0):
        errs.append("Nodes must satisfy min <= desired <= max.")
    return out, errs
