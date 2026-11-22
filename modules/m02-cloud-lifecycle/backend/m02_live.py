"""Read-only, live views of a connected AWS account (boto3). Nothing here changes AWS.

Every section is collected independently: an AccessDenied on one service is reported for that
section and the others still load.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

MAX_ITEMS = 500


def _tags(lst) -> dict:
    return {t["Key"]: t["Value"] for t in (lst or [])}


def _err(e: Exception) -> str:
    code = getattr(e, "response", {}).get("Error", {}).get("Code") if hasattr(e, "response") else None
    msg = str(e)
    if code in ("AccessDenied", "AccessDeniedException", "UnauthorizedOperation"):
        return f"{code}: the account's credentials are not allowed to read this."
    if "Token has expired" in msg or "sso" in msg.lower():
        return "Credentials expired. For SSO run: aws sso login --profile <name>."
    return msg[:240]


def _ts(v):
    return v.strftime("%Y-%m-%d %H:%M") if hasattr(v, "strftime") else (v or "")


# ---------------------------------------------------------------- networks (used by launch + import)
def vpcs(sess, region: str) -> list[dict]:
    ec2 = sess.client("ec2", region_name=region)
    vpc_list = ec2.describe_vpcs()["Vpcs"]
    subnets = ec2.describe_subnets()["Subnets"]
    rts = ec2.describe_route_tables()["RouteTables"]
    igw_rt, main_rt = set(), {}
    sub_rt = {}
    for rt in rts:
        has_igw = any(str(r.get("GatewayId", "")).startswith("igw-") for r in rt.get("Routes", []))
        for a in rt.get("Associations", []):
            if a.get("Main"):
                main_rt[rt["VpcId"]] = has_igw
            elif a.get("SubnetId"):
                sub_rt[a["SubnetId"]] = has_igw
        if has_igw:
            igw_rt.add(rt["RouteTableId"])
    out = []
    for v in vpc_list:
        t = _tags(v.get("Tags"))
        subs = []
        for s in subnets:
            if s["VpcId"] != v["VpcId"]:
                continue
            st = _tags(s.get("Tags"))
            public = sub_rt.get(s["SubnetId"], main_rt.get(v["VpcId"], False))
            subs.append({"id": s["SubnetId"], "name": st.get("Name", ""), "az": s["AvailabilityZone"], "az_id": s.get("AvailabilityZoneId", ""),
                         "cidr": s["CidrBlock"], "free_ips": s.get("AvailableIpAddressCount", 0), "public": bool(public),
                         "auto_public_ip": s.get("MapPublicIpOnLaunch", False)})
        subs.sort(key=lambda x: (not x["public"], x["az"]))
        out.append({"id": v["VpcId"], "name": t.get("Name", ""), "cidr": v["CidrBlock"], "default": v.get("IsDefault", False),
                    "state": v.get("State"), "managed_by_fde": t.get("ManagedBy") == "fde-nexus", "environment": t.get("fde:environment", ""),
                    "subnets": subs, "azs": sorted({s["az"] for s in subs})})
    out.sort(key=lambda x: (x["default"], x["name"] or x["id"]))
    return out


# ---------------------------------------------------------------- inventory
def _ec2(sess, region):
    c = sess.client("ec2", region_name=region)
    rows = []
    for page in c.get_paginator("describe_instances").paginate():
        for r in page["Reservations"]:
            for i in r["Instances"]:
                t = _tags(i.get("Tags"))
                rows.append({"id": i["InstanceId"], "name": t.get("Name", ""), "type": i["InstanceType"], "state": i["State"]["Name"],
                             "az": i.get("Placement", {}).get("AvailabilityZone", ""), "private_ip": i.get("PrivateIpAddress", ""),
                             "public_ip": i.get("PublicIpAddress", ""), "vpc": i.get("VpcId", ""), "launched": _ts(i.get("LaunchTime")),
                             "platform": i.get("PlatformDetails", ""), "managed": t.get("ManagedBy") == "fde-nexus"})
    return sorted(rows, key=lambda x: x["launched"], reverse=True)[:MAX_ITEMS]


def _vpcs(sess, region):
    return [{"id": v["id"], "name": v["name"], "cidr": v["cidr"], "default": v["default"], "subnets": len(v["subnets"]),
             "public_subnets": sum(1 for s in v["subnets"] if s["public"]), "azs": len(v["azs"]), "managed": v["managed_by_fde"]}
            for v in vpcs(sess, region)]


def _s3(sess, region):
    c = sess.client("s3", region_name=region)
    buckets = c.list_buckets().get("Buckets", [])[:MAX_ITEMS]

    def loc(b):
        try:
            r = c.get_bucket_location(Bucket=b["Name"]).get("LocationConstraint") or "us-east-1"
        except Exception:
            r = "?"
        return {"name": b["Name"], "region": r, "created": _ts(b.get("CreationDate"))}
    with ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(loc, buckets))
    return rows  # S3 is global: all buckets, with their region


def _dynamodb(sess, region):
    c = sess.client("dynamodb", region_name=region)
    names = []
    for page in c.get_paginator("list_tables").paginate():
        names += page["TableNames"]
    rows = []
    for n in names[:100]:
        try:
            t = c.describe_table(TableName=n)["Table"]
            rows.append({"name": n, "status": t["TableStatus"], "items": t.get("ItemCount", 0),
                         "size_mb": round(t.get("TableSizeBytes", 0) / 1048576, 1),
                         "billing": (t.get("BillingModeSummary") or {}).get("BillingMode", "PROVISIONED"),
                         "keys": ", ".join(f"{k['AttributeName']} ({k['KeyType']})" for k in t["KeySchema"])})
        except Exception as e:
            rows.append({"name": n, "status": "?", "error": _err(e)})
    return rows


def _eks(sess, region):
    c = sess.client("eks", region_name=region)
    rows = []
    for n in c.list_clusters().get("clusters", []):
        try:
            d = c.describe_cluster(name=n)["cluster"]
            ngs = c.list_nodegroups(clusterName=n).get("nodegroups", [])
            rows.append({"name": n, "version": d.get("version"), "status": d.get("status"), "endpoint_public": d.get("resourcesVpcConfig", {}).get("endpointPublicAccess"),
                         "vpc": d.get("resourcesVpcConfig", {}).get("vpcId"), "nodegroups": len(ngs), "created": _ts(d.get("createdAt"))})
        except Exception as e:
            rows.append({"name": n, "status": "?", "error": _err(e)})
    return rows


def _elb(sess, region):
    c = sess.client("elbv2", region_name=region)
    return [{"name": lb["LoadBalancerName"], "type": lb["Type"], "scheme": lb["Scheme"], "state": lb["State"]["Code"],
             "dns": lb["DNSName"], "vpc": lb.get("VpcId", "")} for lb in c.describe_load_balancers().get("LoadBalancers", [])]


def _rds(sess, region):
    c = sess.client("rds", region_name=region)
    return [{"id": d["DBInstanceIdentifier"], "engine": f"{d['Engine']} {d.get('EngineVersion', '')}", "class": d["DBInstanceClass"],
             "status": d["DBInstanceStatus"], "multi_az": d.get("MultiAZ"), "storage_gb": d.get("AllocatedStorage"),
             "encrypted": d.get("StorageEncrypted"), "public": d.get("PubliclyAccessible")} for d in c.describe_db_instances().get("DBInstances", [])]


def _lambda(sess, region):
    c = sess.client("lambda", region_name=region)
    rows = []
    for page in c.get_paginator("list_functions").paginate():
        rows += [{"name": f["FunctionName"], "runtime": f.get("Runtime", "image"), "memory": f.get("MemorySize"), "modified": f.get("LastModified", "")[:16]}
                 for f in page["Functions"]]
    return rows[:MAX_ITEMS]


SECTIONS = {"ec2": _ec2, "vpcs": _vpcs, "s3": _s3, "dynamodb": _dynamodb, "eks": _eks, "load_balancers": _elb, "rds": _rds, "lambda": _lambda}


def inventory(sess, region: str, only: list[str] | None = None) -> dict:
    names = [n for n in SECTIONS if not only or n in only]

    def run(n):
        try:
            return n, {"items": SECTIONS[n](sess, region), "error": None}
        except Exception as e:  # botocore ClientError/NoCredentials etc.
            return n, {"items": [], "error": _err(e)}
    with ThreadPoolExecutor(len(names)) as pool:
        return dict(pool.map(run, names))
