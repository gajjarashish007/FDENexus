"""Monthly cost estimate for a component from its variables.

On-demand list prices for us-east-1 (Linux), 730 hours/month. Usage-based items
(requests, data transfer, storage that grows) are listed as notes, not guessed.
If `infracost` is installed and an Infracost API key is set, its result can be
attached later; this estimator always works offline.
"""
from __future__ import annotations

HOURS = 730
EC2_HOURLY = {
    "t3.nano": 0.0052, "t3.micro": 0.0104, "t3.small": 0.0208, "t3.medium": 0.0416, "t3.large": 0.0832,
    "t3a.micro": 0.0094, "t3a.small": 0.0188, "t3a.medium": 0.0376,
    "t4g.micro": 0.0084, "t4g.small": 0.0168, "t4g.medium": 0.0336,
    "m6i.large": 0.096, "m6i.xlarge": 0.192, "m7i.large": 0.1008, "m7g.large": 0.0816,
    "c6i.large": 0.085, "c7i.large": 0.0893, "r6i.large": 0.126, "r7i.large": 0.1323,
}
GP3_GB = 0.08
NAT_HOURLY = 0.045
EKS_HOURLY = 0.10
ALB_HOURLY = 0.0225
RCU_HOURLY = 0.00013
WCU_HOURLY = 0.00065
ZONE_MONTHLY = 0.50
SPOT_DISCOUNT = 0.35  # rough average price as a share of on-demand


def _item(name, monthly):
    return {"item": name, "monthly": round(monthly, 2)}


def estimate(component: str, v: dict) -> dict:
    items, notes = [], []
    if component == "ec2-instance":
        t = v.get("instance_type", "")
        h = EC2_HOURLY.get(t)
        if h is None:
            notes.append(f"No list price stored for {t}.")
        else:
            items.append(_item(f"EC2 {t}", h * HOURS))
        items.append(_item(f"gp3 root {v.get('volume_gb', 20)} GB", GP3_GB * float(v.get("volume_gb", 20))))
        if v.get("os") == "windows":
            notes.append("Windows license adds roughly 40-90% to the instance price.")
    elif component == "vpc":
        nat = {"none": 0, "single": 1}.get(v.get("nat_mode", "single"), len(v.get("azs", [])))
        if nat:
            items.append(_item(f"{nat} NAT gateway(s)", nat * NAT_HOURLY * HOURS))
            notes.append("NAT data processing: $0.045 per GB.")
        if v.get("flow_logs", True):
            notes.append("Flow logs: CloudWatch ingestion $0.50 per GB.")
    elif component == "eks-cluster":
        items.append(_item("EKS control plane", EKS_HOURLY * HOURS))
        types = v.get("node_instance_types") or ["m6i.large"]
        h = EC2_HOURLY.get(types[0])
        n = int(v.get("node_desired", 2))
        if h:
            mult = SPOT_DISCOUNT if v.get("capacity_type") == "SPOT" else 1
            items.append(_item(f"{n} x {types[0]} nodes{' (spot, approx.)' if mult < 1 else ''}", h * HOURS * n * mult))
        items.append(_item(f"{n} x {v.get('node_disk_gb', 50)} GB node disks", n * GP3_GB * float(v.get("node_disk_gb", 50))))
        items.append(_item("KMS key", 1.0))
    elif component == "alb":
        items.append(_item("Application Load Balancer", ALB_HOURLY * HOURS))
        notes.append("LCU usage: $0.008 per LCU-hour.")
    elif component == "dynamodb-table":
        if v.get("billing_mode") == "PROVISIONED":
            items.append(_item(f"{v.get('read_capacity', 5)} RCU", RCU_HOURLY * HOURS * int(v.get("read_capacity", 5))))
            items.append(_item(f"{v.get('write_capacity', 5)} WCU", WCU_HOURLY * HOURS * int(v.get("write_capacity", 5))))
        else:
            notes.append("On-demand: $1.25 per million writes, $0.25 per million reads.")
        notes.append("Storage $0.25 per GB-month; PITR $0.20 per GB-month.")
    elif component == "s3-bucket":
        notes.append("Standard storage $0.023 per GB-month plus requests.")
    elif component == "s3-static-website":
        notes.append("S3 storage $0.023 per GB-month.")
        if v.get("hosting", "cloudfront") == "cloudfront":
            notes.append("CloudFront: first 1 TB per month of transfer is free, then $0.085 per GB.")
    elif component == "efs":
        notes.append("EFS Standard $0.30 per GB-month, Infrequent Access $0.016 per GB-month.")
    elif component == "route53-zone":
        items.append(_item("Hosted zone", ZONE_MONTHLY))
        notes.append("Queries: $0.40 per million.")
    elif component == "acm-certificate":
        notes.append("Public ACM certificates are free.")
    elif component == "account-baseline":
        notes.append("Access Analyzer (external access) is free. GuardDuty, if enabled, is usage-based.")
    elif component == "aws-account":
        notes.append("No charge for the account itself.")
    total = round(sum(i["monthly"] for i in items), 2)
    return {"monthly": total, "items": items, "notes": notes, "currency": "USD",
            "basis": "us-east-1 on-demand list prices, 730 h/month"}
