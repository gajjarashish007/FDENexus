"""EC2 instance launch and lifecycle for the self-service portal.

Two modes, chosen by config.DEMO_MODE:
  * simulated (M01_DEMO=1): instances live in the local SQLite table ec2_instances.
    No AWS call is made.
  * live (M01_DEMO=0): boto3 against the selected AWS account (AssumeRole or
    instance role). Only instances tagged ManagedBy=fde-nexus can be changed.
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
from datetime import datetime, timezone

import config
import store

MANAGED_TAG = ("ManagedBy", "fde-nexus")

INSTANCE_TYPES = [
    {"type": "t3.micro",  "vcpus": 2, "memoryGb": 1,  "category": "free-tier", "priceHour": 0.0104, "desc": "Burstable, low-traffic apps and labs"},
    {"type": "t3.small",  "vcpus": 2, "memoryGb": 2,  "category": "general",   "priceHour": 0.0208, "desc": "Small web servers and dev environments"},
    {"type": "t3.medium", "vcpus": 2, "memoryGb": 4,  "category": "general",   "priceHour": 0.0416, "desc": "Popular choice for web applications"},
    {"type": "t3.large",  "vcpus": 2, "memoryGb": 8,  "category": "general",   "priceHour": 0.0832, "desc": "More memory for app servers"},
    {"type": "m5.large",  "vcpus": 2, "memoryGb": 8,  "category": "general",   "priceHour": 0.096,  "desc": "General purpose, steady performance"},
    {"type": "c5.large",  "vcpus": 2, "memoryGb": 4,  "category": "compute",   "priceHour": 0.085,  "desc": "CPU-heavy workloads"},
    {"type": "c5.xlarge", "vcpus": 4, "memoryGb": 8,  "category": "compute",   "priceHour": 0.17,   "desc": "High-performance compute"},
    {"type": "r5.large",  "vcpus": 2, "memoryGb": 16, "category": "memory",    "priceHour": 0.126,  "desc": "Databases and caching"},
    {"type": "r5.xlarge", "vcpus": 4, "memoryGb": 32, "category": "memory",    "priceHour": 0.252,  "desc": "Large in-memory workloads"},
]
_TYPE_NAMES = {t["type"] for t in INSTANCE_TYPES}

# OS images are resolved per region at launch through public SSM parameters.
OS_IMAGES = [
    {"os": "amazon-linux", "name": "Amazon Linux 2023", "ssm": "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64", "user": "ec2-user", "desc": "Recommended for most workloads"},
    {"os": "ubuntu", "name": "Ubuntu Server 22.04 LTS", "ssm": "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id", "user": "ubuntu", "desc": "Popular open-source OS"},
    {"os": "windows", "name": "Windows Server 2022", "ssm": "/aws/service/ami-windows-latest/Windows_Server-2022-English-Full-Base", "user": "Administrator", "desc": ".NET and IIS workloads"},
]
_OS_BY_ID = {o["os"]: o for o in OS_IMAGES}

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,62}$")
KEY_RE = re.compile(r"^[A-Za-z0-9 ._@:/=+-]{1,255}$")
SUBNET_RE = re.compile(r"^subnet-[0-9a-f]{8,17}$")
SG_RE = re.compile(r"^sg-[0-9a-f]{8,17}$")


def catalog() -> dict:
    types = []
    for t in INSTANCE_TYPES:
        types.append({**t, "priceMonth": round(t["priceHour"] * 730, 2), "freeTier": t["category"] == "free-tier"})
    return {"instanceTypes": types, "images": [{k: v for k, v in o.items() if k != "ssm"} for o in OS_IMAGES]}


def validate(inputs: dict, account: dict | None) -> list[str]:
    errs = []
    if not account:
        errs.append("Select a connected AWS account.")
    elif account["status"] != "connected":
        errs.append("The selected AWS account is not connected.")
    if inputs.get("os") not in _OS_BY_ID:
        errs.append("Choose an operating system image.")
    if inputs.get("instance_type") not in _TYPE_NAMES:
        errs.append("Choose a supported instance type.")
    if not NAME_RE.match(str(inputs.get("instance_name", ""))):
        errs.append("Instance name must be 1-63 characters: letters, digits, space, . _ -")
    vol = inputs.get("volume_gb", 20)
    if not isinstance(vol, (int, float)) or not 8 <= vol <= 1000:
        errs.append("Root volume must be between 8 and 1000 GB.")
    if inputs.get("key_name") and not KEY_RE.match(str(inputs["key_name"])):
        errs.append("Key pair name has invalid characters.")
    if inputs.get("subnet_id") and not SUBNET_RE.match(str(inputs["subnet_id"])):
        errs.append("Subnet ID must look like subnet-0123abcd.")
    for sg in filter(None, str(inputs.get("security_group_ids", "")).split(",")):
        if not SG_RE.match(sg.strip()):
            errs.append(f"Invalid security group ID: {sg.strip()}")
    if len(str(inputs.get("user_data", ""))) > 16000:
        errs.append("User data is limited to 16 KB.")
    return errs


# ----------------------------------------------------------------- simulated store
SIM_SCHEMA = """
CREATE TABLE IF NOT EXISTS ec2_instances (
    instance_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, name TEXT, os TEXT, instance_type TEXT,
    state TEXT NOT NULL, public_ip TEXT, private_ip TEXT, key_name TEXT, subnet_id TEXT,
    volume_gb INTEGER, environment TEXT, region TEXT, request_id TEXT, owner TEXT, launched_at TEXT NOT NULL
);
"""


def init() -> None:
    with store._LOCK, store._connect() as conn:
        conn.executescript(SIM_SCHEMA)
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _sim_list(account_id: str) -> list[dict]:
    with store._connect() as conn:
        rows = conn.execute("SELECT * FROM ec2_instances WHERE account_id=? ORDER BY launched_at DESC", (account_id,)).fetchall()
    return [{"instanceId": r["instance_id"], "name": r["name"], "os": r["os"], "instanceType": r["instance_type"],
             "state": r["state"], "publicIp": r["public_ip"], "privateIp": r["private_ip"], "keyName": r["key_name"],
             "region": r["region"], "environment": r["environment"], "owner": r["owner"], "requestId": r["request_id"],
             "launchTime": r["launched_at"], "managed": True, "simulated": True} for r in rows]


def _sim_launch(account: dict, p: dict) -> str:
    iid = "i-" + secrets.token_hex(8)
    pub = ".".join(str(secrets.randbelow(200) + 20) for _ in range(4))
    priv = f"10.0.{secrets.randbelow(250)}.{secrets.randbelow(250) + 2}"
    with store._LOCK, store._connect() as conn:
        conn.execute("INSERT INTO ec2_instances VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (iid, account["id"], p["instance_name"], p["os"], p["instance_type"], "running", pub, priv,
                      p.get("key_name") or "", p.get("subnet_id") or "", int(p.get("volume_gb", 20)),
                      p.get("environment") or "non-production", p.get("region") or account["region"],
                      p.get("request_id"), p.get("owner"), _now()))
        conn.commit()
    return iid


def _sim_action(account_id: str, iid: str, action: str) -> str:
    new = {"start": "running", "stop": "stopped", "reboot": "running", "terminate": "terminated"}[action]
    with store._LOCK, store._connect() as conn:
        cur = conn.execute("SELECT state FROM ec2_instances WHERE instance_id=? AND account_id=?", (iid, account_id)).fetchone()
        if not cur:
            raise LookupError("Instance not found")
        if cur["state"] == "terminated":
            raise ValueError("Instance is terminated")
        conn.execute("UPDATE ec2_instances SET state=? WHERE instance_id=?", (new, iid))
        conn.commit()
    return new


# ----------------------------------------------------------------- live (boto3)
def _session(account: dict, region: str | None = None):
    """boto3 session for a connected account.
    instance-role: the portal host's default credential chain (instance profile, env, AWS_PROFILE)
    profile:       a named profile from ~/.aws/config on the host (SSO, credential_process, keys)
    assume-role:   sts:AssumeRole from the host credentials into the account's role (+ external ID)"""
    import boto3
    region = region or account["region"]
    if account["method"] == "profile":
        return boto3.Session(profile_name=account.get("profile") or None, region_name=region)
    base = boto3.Session(region_name=region)
    if account["method"] == "instance-role":
        return base
    kw = {"RoleArn": account["role_arn"], "RoleSessionName": "fde-nexus-ec2", "DurationSeconds": 3600}
    if account.get("external_id"):
        kw["ExternalId"] = account["external_id"]
    c = base.client("sts").assume_role(**kw)["Credentials"]
    return boto3.Session(aws_access_key_id=c["AccessKeyId"], aws_secret_access_key=c["SecretAccessKey"],
                         aws_session_token=c["SessionToken"], region_name=region)


def _tags(inst: dict) -> dict:
    return {t["Key"]: t["Value"] for t in inst.get("Tags", [])}


def options(account: dict) -> dict:
    """Key pairs, subnets and security groups to populate the launch form."""
    if not config.LIVE_READS:
        return {"simulated": True, "keyPairs": [], "subnets": [], "securityGroups": [],
                "message": "Live reads are off (M01_LIVE_READS=0). Values you type are stored as given."}
    ec2 = _session(account).client("ec2")
    out = {"simulated": config.DEMO_MODE}
    out["keyPairs"] = [k["KeyName"] for k in ec2.describe_key_pairs()["KeyPairs"]]
    out["subnets"] = [{"id": s["SubnetId"], "az": s["AvailabilityZone"], "cidr": s["CidrBlock"], "vpc": s["VpcId"],
                      "name": _tags(s).get("Name", "")} for s in ec2.describe_subnets()["Subnets"]]
    out["securityGroups"] = [{"id": g["GroupId"], "name": g["GroupName"], "vpc": g["VpcId"]}
                             for g in ec2.describe_security_groups()["SecurityGroups"]]
    return out


def launch(account: dict, p: dict) -> str:
    """p: validated inputs plus request_id and owner. Returns the instance id."""
    if config.DEMO_MODE:
        return _sim_launch(account, p)
    sess = _session(account)
    ami = sess.client("ssm").get_parameter(Name=_OS_BY_ID[p["os"]]["ssm"])["Parameter"]["Value"]
    params = {
        "ImageId": ami, "InstanceType": p["instance_type"], "MinCount": 1, "MaxCount": 1,
        "BlockDeviceMappings": [{"DeviceName": "/dev/xvda" if p["os"] == "amazon-linux" else
                                 ("/dev/sda1" if p["os"] == "ubuntu" else "/dev/sda1"),
                                 "Ebs": {"VolumeSize": int(p.get("volume_gb", 20)), "VolumeType": "gp3", "Encrypted": True}}],
        "MetadataOptions": {"HttpTokens": "required"},
        "TagSpecifications": [{"ResourceType": "instance", "Tags": [
            {"Key": "Name", "Value": p["instance_name"]}, {"Key": MANAGED_TAG[0], "Value": MANAGED_TAG[1]},
            {"Key": "Environment", "Value": p.get("environment") or "non-production"},
            {"Key": "RequestId", "Value": str(p.get("request_id") or "")}, {"Key": "Owner", "Value": str(p.get("owner") or "")}]}],
    }
    if p.get("key_name"):
        params["KeyName"] = p["key_name"]
    if p.get("subnet_id"):
        params["SubnetId"] = p["subnet_id"]
    sgs = [s.strip() for s in str(p.get("security_group_ids", "")).split(",") if s.strip()]
    if sgs:
        params["SecurityGroupIds"] = sgs
    if p.get("user_data"):
        params["UserData"] = p["user_data"]
    return sess.client("ec2").run_instances(**params)["Instances"][0]["InstanceId"]


def list_instances(account: dict) -> list[dict]:
    """Live instances from AWS (when live reads are on) plus any simulated ones recorded in demo mode."""
    out = _sim_list(account["id"]) if config.DEMO_MODE else []
    if not config.LIVE_READS:
        return out
    pages = _session(account).client("ec2").get_paginator("describe_instances")
    for page in pages.paginate():
        for r in page["Reservations"]:
            for i in r["Instances"]:
                t = _tags(i)
                out.append({"instanceId": i["InstanceId"], "name": t.get("Name", ""), "os": i.get("PlatformDetails", ""),
                            "instanceType": i["InstanceType"], "state": i["State"]["Name"],
                            "publicIp": i.get("PublicIpAddress", ""), "privateIp": i.get("PrivateIpAddress", ""),
                            "keyName": i.get("KeyName", ""), "region": account["region"], "environment": t.get("Environment", ""),
                            "owner": t.get("Owner", ""), "requestId": t.get("RequestId", ""),
                            "launchTime": i["LaunchTime"].strftime("%Y-%m-%d %H:%M:%S"),
                            "managed": t.get(MANAGED_TAG[0]) == MANAGED_TAG[1], "simulated": False})
    out.sort(key=lambda x: x["launchTime"], reverse=True)
    return out


def act(account: dict, iid: str, action: str) -> str:
    if action not in ("start", "stop", "reboot", "terminate"):
        raise ValueError("Unknown action")
    if not re.fullmatch(r"i-[0-9a-f]{8,17}", iid):
        raise ValueError("Invalid instance id")
    with store._connect() as conn:
        simulated = conn.execute("SELECT 1 FROM ec2_instances WHERE instance_id=? AND account_id=?", (iid, account["id"])).fetchone()
    if simulated:
        return _sim_action(account["id"], iid, action)
    if config.DEMO_MODE:
        raise PermissionError("Simulation mode (M01_DEMO=1): real instances are read-only. Start with ./start-portal.sh --prod to change them.")
    ec2 = _session(account).client("ec2")
    res = ec2.describe_instances(InstanceIds=[iid])["Reservations"]
    if not res or _tags(res[0]["Instances"][0]).get(MANAGED_TAG[0]) != MANAGED_TAG[1]:
        raise PermissionError("Only instances launched by FDE Nexus can be changed here.")
    {"start": ec2.start_instances, "stop": ec2.stop_instances, "reboot": ec2.reboot_instances,
     "terminate": ec2.terminate_instances}[action](InstanceIds=[iid])
    return {"start": "pending", "stop": "stopping", "reboot": "running", "terminate": "shutting-down"}[action]
