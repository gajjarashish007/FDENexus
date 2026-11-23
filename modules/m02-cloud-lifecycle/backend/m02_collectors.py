"""Read-only collectors: one function per AWS service, returning normalized rows.

Every row: {"id", "name", "state", "summary": {...small fields for tables...}, "tags": {...}, "detail": {...}}
`detail` is the API object with secret-bearing fields removed (e.g. Lambda environment variables).
Nothing here creates, changes or deletes anything in AWS.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

MAX = 5000  # per service per region


def tags_of(lst) -> dict:
    if isinstance(lst, dict):
        return {str(k): str(v) for k, v in lst.items()}
    return {t.get("Key") or t.get("key"): t.get("Value") or t.get("value") for t in (lst or []) if (t.get("Key") or t.get("key"))}


def clean(o, depth=0):
    """JSON-safe copy; datetimes to ISO strings; drop known secret-bearing keys."""
    if depth > 8:
        return None
    if isinstance(o, dict):
        return {k: clean(v, depth + 1) for k, v in o.items()
                if k not in ("Environment", "Variables", "UserData", "MasterUserPassword", "AuthToken", "Policy", "ResponseMetadata")}
    if isinstance(o, list):
        return [clean(v, depth + 1) for v in o[:200]]
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, bytes):
        return None
    return o


def row(id_, name="", state="", summary=None, tags=None, detail=None):
    return {"id": str(id_), "name": name or "", "state": state or "", "summary": clean(summary or {}),
            "tags": tags or {}, "detail": clean(detail or {})}


def _pages(client, op, key, **kw):
    out = []
    if client.can_paginate(op):
        for p in client.get_paginator(op).paginate(**kw):
            out += p.get(key, [])
            if len(out) >= MAX:
                break
    else:
        out = getattr(client, op)(**kw).get(key, [])
    return out[:MAX]


# ---------------------------------------------------------------- compute & network
def ec2_instances(s, r):
    c, out = s.client("ec2", region_name=r), []
    for res in _pages(c, "describe_instances", "Reservations"):
        for i in res["Instances"]:
            t = tags_of(i.get("Tags"))
            out.append(row(i["InstanceId"], t.get("Name", ""), i["State"]["Name"], {
                "type": i["InstanceType"], "az": i.get("Placement", {}).get("AvailabilityZone"), "private_ip": i.get("PrivateIpAddress"),
                "public_ip": i.get("PublicIpAddress"), "vpc": i.get("VpcId"), "subnet": i.get("SubnetId"), "platform": i.get("PlatformDetails"),
                "launched": i.get("LaunchTime"), "iam_profile": (i.get("IamInstanceProfile") or {}).get("Arn", "").split("/")[-1],
                "imdsv2": (i.get("MetadataOptions") or {}).get("HttpTokens") == "required"}, t, i))
    return out


def vpcs(s, r):
    c = s.client("ec2", region_name=r)
    subs = _pages(c, "describe_subnets", "Subnets")
    out = []
    for v in _pages(c, "describe_vpcs", "Vpcs"):
        t = tags_of(v.get("Tags"))
        mine = [x for x in subs if x["VpcId"] == v["VpcId"]]
        out.append(row(v["VpcId"], t.get("Name", ""), v.get("State"), {"cidr": v["CidrBlock"], "default": v.get("IsDefault"),
                       "subnets": len(mine), "azs": len({x["AvailabilityZone"] for x in mine})}, t, v))
    return out


def subnets(s, r):
    c = s.client("ec2", region_name=r)
    return [row(x["SubnetId"], tags_of(x.get("Tags")).get("Name", ""), x.get("State"), {
        "vpc": x["VpcId"], "az": x["AvailabilityZone"], "cidr": x["CidrBlock"], "free_ips": x.get("AvailableIpAddressCount"),
        "auto_public_ip": x.get("MapPublicIpOnLaunch")}, tags_of(x.get("Tags")), x) for x in _pages(c, "describe_subnets", "Subnets")]


def security_groups(s, r):
    c = s.client("ec2", region_name=r)
    out = []
    for g in _pages(c, "describe_security_groups", "SecurityGroups"):
        open_world = sorted({str(p.get("FromPort", "all")) for p in g.get("IpPermissions", [])
                             if any(x.get("CidrIp") == "0.0.0.0/0" for x in p.get("IpRanges", [])) or any(x.get("CidrIpv6") == "::/0" for x in p.get("Ipv6Ranges", []))})
        out.append(row(g["GroupId"], g["GroupName"], "open-to-internet" if open_world else "", {
            "vpc": g.get("VpcId"), "inbound_rules": len(g.get("IpPermissions", [])), "open_ports": ", ".join(open_world),
            "description": g.get("Description", "")[:120]}, tags_of(g.get("Tags")), g))
    return out


def ebs_volumes(s, r):
    c = s.client("ec2", region_name=r)
    return [row(v["VolumeId"], tags_of(v.get("Tags")).get("Name", ""), v["State"], {
        "size_gb": v["Size"], "type": v["VolumeType"], "encrypted": v.get("Encrypted"), "az": v["AvailabilityZone"],
        "attached_to": ", ".join(a["InstanceId"] for a in v.get("Attachments", [])), "created": v.get("CreateTime")},
        tags_of(v.get("Tags")), v) for v in _pages(c, "describe_volumes", "Volumes")]


def autoscaling_groups(s, r):
    c = s.client("autoscaling", region_name=r)
    return [row(g["AutoScalingGroupName"], g["AutoScalingGroupName"], g.get("Status", "active"), {
        "min": g["MinSize"], "desired": g["DesiredCapacity"], "max": g["MaxSize"], "instances": len(g.get("Instances", [])),
        "launch": (g.get("LaunchTemplate") or (g.get("MixedInstancesPolicy") or {}).get("LaunchTemplate", {}).get("LaunchTemplateSpecification") or {}).get("LaunchTemplateName", g.get("LaunchConfigurationName", ""))},
        tags_of(g.get("Tags")), g) for g in _pages(c, "describe_auto_scaling_groups", "AutoScalingGroups")]


def load_balancers(s, r):
    c = s.client("elbv2", region_name=r)
    return [row(lb["LoadBalancerArn"], lb["LoadBalancerName"], lb["State"]["Code"], {
        "type": lb["Type"], "scheme": lb["Scheme"], "dns": lb["DNSName"], "vpc": lb.get("VpcId"), "azs": len(lb.get("AvailabilityZones", []))},
        {}, lb) for lb in _pages(c, "describe_load_balancers", "LoadBalancers")]


# ---------------------------------------------------------------- containers & serverless
def eks_clusters(s, r):
    c, out = s.client("eks", region_name=r), []
    for n in _pages(c, "list_clusters", "clusters"):
        try:
            d = c.describe_cluster(name=n)["cluster"]
            ngs = c.list_nodegroups(clusterName=n).get("nodegroups", [])
        except Exception as e:  # keep the name even if describe is denied
            out.append(row(n, n, "unknown", {"error": str(e)[:120]}))
            continue
        vpc = d.get("resourcesVpcConfig", {})
        out.append(row(n, n, d.get("status"), {"version": d.get("version"), "platform": d.get("platformVersion"), "nodegroups": len(ngs),
                       "public_api": vpc.get("endpointPublicAccess"), "vpc": vpc.get("vpcId"), "created": d.get("createdAt")}, d.get("tags"), d))
    return out


def ecr_repositories(s, r):
    c = s.client("ecr", region_name=r)
    return [row(x["repositoryName"], x["repositoryName"], "", {"uri": x["repositoryUri"], "scan_on_push": (x.get("imageScanningConfiguration") or {}).get("scanOnPush"),
                "tag_mutability": x.get("imageTagMutability"), "created": x.get("createdAt")}, {}, x)
            for x in _pages(c, "describe_repositories", "repositories")]


def lambda_functions(s, r):
    c = s.client("lambda", region_name=r)
    return [row(f["FunctionName"], f["FunctionName"], f.get("State", "Active"), {"runtime": f.get("Runtime") or f.get("PackageType"),
                "memory_mb": f.get("MemorySize"), "timeout_s": f.get("Timeout"), "modified": f.get("LastModified"), "arch": ",".join(f.get("Architectures", []))},
                {}, f) for f in _pages(c, "list_functions", "Functions")]


def sqs_queues(s, r):
    c = s.client("sqs", region_name=r)
    return [row(u, u.rsplit("/", 1)[-1], "", {"url": u, "fifo": u.endswith(".fifo")}) for u in _pages(c, "list_queues", "QueueUrls")]


def sns_topics(s, r):
    c = s.client("sns", region_name=r)
    return [row(t["TopicArn"], t["TopicArn"].rsplit(":", 1)[-1], "", {"arn": t["TopicArn"]}) for t in _pages(c, "list_topics", "Topics")]


# ---------------------------------------------------------------- data
def rds_instances(s, r):
    c = s.client("rds", region_name=r)
    return [row(d["DBInstanceIdentifier"], d["DBInstanceIdentifier"], d["DBInstanceStatus"], {
        "engine": f"{d['Engine']} {d.get('EngineVersion', '')}", "class": d["DBInstanceClass"], "multi_az": d.get("MultiAZ"),
        "storage_gb": d.get("AllocatedStorage"), "encrypted": d.get("StorageEncrypted"), "public": d.get("PubliclyAccessible"),
        "backup_days": d.get("BackupRetentionPeriod"), "cluster": d.get("DBClusterIdentifier")}, tags_of(d.get("TagList")), d)
        for d in _pages(c, "describe_db_instances", "DBInstances")]


def rds_clusters(s, r):
    c = s.client("rds", region_name=r)
    return [row(d["DBClusterIdentifier"], d["DBClusterIdentifier"], d["Status"], {
        "engine": f"{d['Engine']} {d.get('EngineVersion', '')}", "members": len(d.get("DBClusterMembers", [])), "multi_az": d.get("MultiAZ"),
        "encrypted": d.get("StorageEncrypted"), "backup_days": d.get("BackupRetentionPeriod")}, tags_of(d.get("TagList")), d)
        for d in _pages(c, "describe_db_clusters", "DBClusters")]


def dynamodb_tables(s, r):
    c = s.client("dynamodb", region_name=r)
    names = _pages(c, "list_tables", "TableNames")

    def one(n):
        try:
            t = c.describe_table(TableName=n)["Table"]
        except Exception as e:
            return row(n, n, "unknown", {"error": str(e)[:120]})
        return row(n, n, t["TableStatus"], {"items": t.get("ItemCount"), "size_mb": round(t.get("TableSizeBytes", 0) / 1048576, 1),
                   "billing": (t.get("BillingModeSummary") or {}).get("BillingMode", "PROVISIONED"),
                   "keys": ", ".join(f"{k['AttributeName']}({k['KeyType'][0]})" for k in t["KeySchema"]), "gsi": len(t.get("GlobalSecondaryIndexes", []))}, {}, t)
    with ThreadPoolExecutor(6) as pool:
        return list(pool.map(one, names[:1000]))


def elasticache(s, r):
    c = s.client("elasticache", region_name=r)
    return [row(x["CacheClusterId"], x["CacheClusterId"], x["CacheClusterStatus"], {"engine": f"{x['Engine']} {x.get('EngineVersion', '')}",
                "node_type": x.get("CacheNodeType"), "nodes": x.get("NumCacheNodes"), "group": x.get("ReplicationGroupId"),
                "encrypted": x.get("AtRestEncryptionEnabled")}, {}, x) for x in _pages(c, "describe_cache_clusters", "CacheClusters")]


def acm_certificates(s, r):
    c = s.client("acm", region_name=r)
    return [row(x["CertificateArn"], x.get("DomainName", ""), x.get("Status"), {"type": x.get("Type"), "in_use": x.get("InUse"),
                "expires": x.get("NotAfter"), "renewal": x.get("RenewalEligibility")}, {}, x)
            for x in _pages(c, "list_certificates", "CertificateSummaryList")]


def kms_keys(s, r):
    c = s.client("kms", region_name=r)
    aliases = {a.get("TargetKeyId"): a["AliasName"] for a in _pages(c, "list_aliases", "Aliases") if a.get("TargetKeyId")}
    return [row(k["KeyId"], aliases.get(k["KeyId"], ""), "", {"arn": k["KeyArn"], "aws_managed": aliases.get(k["KeyId"], "").startswith("alias/aws/")})
            for k in _pages(c, "list_keys", "Keys")]


# ---------------------------------------------------------------- global services
def s3_buckets(s, r):
    c = s.client("s3", region_name="us-east-1")
    buckets = c.list_buckets().get("Buckets", [])[:MAX]

    def one(b):
        try:
            reg = c.get_bucket_location(Bucket=b["Name"]).get("LocationConstraint") or "us-east-1"
        except Exception:
            reg = "unknown"
        return row(b["Name"], b["Name"], "", {"bucket_region": reg, "created": b.get("CreationDate")}, {}, b)
    with ThreadPoolExecutor(8) as pool:
        return list(pool.map(one, buckets))


def iam_roles(s, r):
    c = s.client("iam")
    roles = list(_pages(c, "list_roles", "Roles"))

    def last_used(x):
        # list_roles never includes RoleLastUsed; only get_role does.
        try:
            lu = c.get_role(RoleName=x["RoleName"])["Role"].get("RoleLastUsed") or {}
            return True, lu.get("LastUsedDate"), lu.get("Region")
        except Exception:
            return False, None, None
    with ThreadPoolExecutor(8) as pool:
        used = list(pool.map(last_used, roles))
    return [row(x["Arn"], x["RoleName"], "", {"path": x.get("Path"), "created": x.get("CreateDate"), "last_used": u[1], "last_used_region": u[2],
                "last_used_checked": u[0], "description": (x.get("Description") or "")[:120]}, {}, x)
            for x, u in zip(roles, used)]


def route53_zones(s, r):
    c = s.client("route53")
    return [row(z["Id"].split("/")[-1], z["Name"].rstrip("."), "private" if z.get("Config", {}).get("PrivateZone") else "public",
                {"records": z.get("ResourceRecordSetCount"), "comment": (z.get("Config") or {}).get("Comment", "")}, {}, z)
            for z in _pages(c, "list_hosted_zones", "HostedZones")]


def cloudfront_distributions(s, r):
    c = s.client("cloudfront")
    out = []
    for p in c.get_paginator("list_distributions").paginate():
        for d in (p.get("DistributionList") or {}).get("Items", []) or []:
            out.append(row(d["Id"], d.get("Comment") or d["DomainName"], d.get("Status"), {"domain": d["DomainName"],
                           "aliases": ", ".join((d.get("Aliases") or {}).get("Items", []) or []), "enabled": d.get("Enabled"),
                           "price_class": d.get("PriceClass")}, {}, d))
    return out


# service id -> (label, category, collector, scope)
SERVICES = {
    "ec2": ("EC2 instances", "Compute", ec2_instances, "regional"),
    "asg": ("Auto Scaling groups", "Compute", autoscaling_groups, "regional"),
    "ebs": ("EBS volumes", "Storage", ebs_volumes, "regional"),
    "lambda": ("Lambda functions", "Compute", lambda_functions, "regional"),
    "eks": ("EKS clusters", "Containers", eks_clusters, "regional"),
    "ecr": ("ECR repositories", "Containers", ecr_repositories, "regional"),
    "vpc": ("VPCs", "Networking", vpcs, "regional"),
    "subnet": ("Subnets", "Networking", subnets, "regional"),
    "sg": ("Security groups", "Networking", security_groups, "regional"),
    "elb": ("Load balancers", "Networking", load_balancers, "regional"),
    "rds": ("RDS instances", "Databases", rds_instances, "regional"),
    "rds_cluster": ("Aurora / RDS clusters", "Databases", rds_clusters, "regional"),
    "dynamodb": ("DynamoDB tables", "Databases", dynamodb_tables, "regional"),
    "elasticache": ("ElastiCache clusters", "Databases", elasticache, "regional"),
    "sqs": ("SQS queues", "Integration", sqs_queues, "regional"),
    "sns": ("SNS topics", "Integration", sns_topics, "regional"),
    "acm": ("ACM certificates", "Security", acm_certificates, "regional"),
    "kms": ("KMS keys", "Security", kms_keys, "regional"),
    "s3": ("S3 buckets", "Storage", s3_buckets, "global"),
    "iam_role": ("IAM roles", "Security", iam_roles, "global"),
    "route53": ("Route 53 zones", "Networking", route53_zones, "global"),
    "cloudfront": ("CloudFront distributions", "Networking", cloudfront_distributions, "global"),
}
