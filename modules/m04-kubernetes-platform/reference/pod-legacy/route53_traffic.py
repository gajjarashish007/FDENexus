"""Route53 traffic migration lookup for pod dashboard."""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

_POD_DIR = os.path.dirname(os.path.abspath(__file__))
_HOSTS_FILE = os.path.join(_POD_DIR, "data", "traffic_migration_hosts.json")

_DEFAULT_HOSTS = [
    {
        "id": "advisor",
        "hostname": "advisor.comcast.arlocloud.com",
        "label": "Advisor (Comcast)",
    },
]


def _normalize_hostname(hostname: str) -> str:
    return (hostname or "").strip().rstrip(".").lower()


def load_traffic_hosts() -> list[dict[str, str]]:
    if os.path.isfile(_HOSTS_FILE):
        try:
            with open(_HOSTS_FILE, encoding="utf-8") as fh:
                data = json.load(fh)
            hosts = data.get("hosts") if isinstance(data, dict) else data
            if isinstance(hosts, list) and hosts:
                return [
                    {
                        "id": str(h.get("id") or _normalize_hostname(h.get("hostname", ""))),
                        "hostname": _normalize_hostname(h.get("hostname", "")),
                        "label": str(h.get("label") or h.get("hostname") or ""),
                    }
                    for h in hosts
                    if h.get("hostname")
                ]
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return list(_DEFAULT_HOSTS)


def _route53_record_target(rr: dict[str, Any]) -> str:
    alias = rr.get("AliasTarget") or {}
    if alias:
        return (alias.get("DNSName") or "").rstrip(".")
    values = [str(r.get("Value") or "") for r in (rr.get("ResourceRecords") or [])]
    return ", ".join(v.rstrip(".") for v in values if v) or "—"


def _route53_routing_meta(rr: dict[str, Any]) -> dict[str, Any]:
    weight = rr.get("Weight")
    region = rr.get("Region") or ""
    failover = rr.get("Failover") or ""
    geo = rr.get("GeoLocation") or {}
    geo_parts = [geo.get("ContinentCode"), geo.get("CountryCode"), geo.get("SubdivisionCode")]
    geo_label = "/".join(p for p in geo_parts if p) or ""

    if weight is not None:
        policy = "weighted"
    elif region:
        policy = "latency"
    elif geo_label:
        policy = "geolocation"
    elif failover:
        policy = "failover"
    elif rr.get("MultiValueAnswer"):
        policy = "multivalue"
    else:
        policy = "simple"

    return {
        "weight": int(weight) if weight is not None else None,
        "setIdentifier": rr.get("SetIdentifier") or "—",
        "routingPolicy": policy,
        "region": region or "—",
        "failover": failover or "—",
        "geoLocation": geo_label or "—",
    }


def _apply_traffic_pct(records: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rec in records:
        if rec.get("weight") is not None:
            groups.setdefault((rec["name"], rec["type"]), []).append(rec)
    for group in groups.values():
        total = sum(int(r["weight"]) for r in group if r.get("weight") is not None)
        for rec in group:
            w = rec.get("weight")
            rec["trafficPct"] = round(100 * int(w) / total, 1) if total > 0 and w is not None else None


def _target_kind(target: str, alias: bool) -> str:
    t = (target or "").lower()
    if "cloudfront.net" in t:
        return "CloudFront"
    if "elb.amazonaws.com" in t or "awsglobalaccelerator.com" in t:
        return "Load Balancer"
    if alias:
        return "Alias"
    if t and t != "—":
        return "CNAME" if not alias else "Alias"
    return "—"


def _aws_session(profile: str, region: str):
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for Route53 traffic lookup") from exc

    if profile:
        return boto3.Session(profile_name=profile, region_name=region)
    return boto3.Session(region_name=region)


def _find_hosted_zones(r53: Any, hostname: str) -> list[dict[str, Any]]:
    """All hosted zones that could contain records for this hostname."""
    hostname = _normalize_hostname(hostname)
    matches: list[dict[str, Any]] = []

    for z in r53.list_hosted_zones().get("HostedZones") or []:
        zone_name = (z.get("Name") or "").rstrip(".").lower()
        if not zone_name:
            continue
        if hostname == zone_name or hostname.endswith("." + zone_name):
            matches.append({
                "name": zone_name,
                "id": (z.get("Id") or "").replace("/hostedzone/", ""),
                "private": bool((z.get("Config") or {}).get("PrivateZone", False)),
                "comment": (z.get("Config") or {}).get("Comment") or "",
                "recordCount": int(z.get("ResourceRecordSetCount") or 0),
            })

    # Prefer public zones, then longest zone name (most specific).
    matches.sort(key=lambda z: (z["private"], -len(z["name"])))
    return matches


def _find_hosted_zone(r53: Any, hostname: str) -> dict[str, Any] | None:
    zones = _find_hosted_zones(r53, hostname)
    return zones[0] if zones else None


def _fetch_zone_record_sets_for_hostname(
    r53: Any,
    zone_id: str,
    hostname: str,
) -> list[dict[str, Any]]:
    """Fetch record sets for an exact hostname using targeted Route53 queries."""
    hostname = _normalize_hostname(hostname)
    fqdn = f"{hostname}."
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def _collect(page_records: list[dict[str, Any]]) -> None:
        for rr in page_records:
            name = (rr.get("Name") or "").rstrip(".").lower()
            if name != hostname:
                continue
            rtype = rr.get("Type") or ""
            set_id = rr.get("SetIdentifier") or ""
            key = (name, rtype, set_id)
            if key in seen:
                continue
            seen.add(key)
            found.append(rr)

    # Targeted lookup — much faster than scanning an entire large zone.
    for start_type in ("CNAME", "A", "AAAA"):
        resp = r53.list_resource_record_sets(
            HostedZoneId=zone_id,
            StartRecordName=fqdn,
            StartRecordType=start_type,
            MaxItems="100",
        )
        _collect(resp.get("ResourceRecordSets") or [])

    if found:
        return found

    # Broader scan from hostname prefix (catches any record type at this name).
    resp = r53.list_resource_record_sets(
        HostedZoneId=zone_id,
        StartRecordName=fqdn,
        MaxItems="100",
    )
    for rr in resp.get("ResourceRecordSets") or []:
        name = (rr.get("Name") or "").rstrip(".").lower()
        if name != hostname:
            break
        rtype = rr.get("Type") or ""
        set_id = rr.get("SetIdentifier") or ""
        key = (name, rtype, set_id)
        if key not in seen:
            seen.add(key)
            found.append(rr)

    return found


def _cloudfront_for_hostname(
    cf_map: dict[str, dict[str, Any]],
    hostname: str,
) -> dict[str, Any] | None:
    hostname = _normalize_hostname(hostname)
    for dist in cf_map.values():
        aliases = dist.get("aliases") or []
        if hostname in aliases:
            return dist
    return None


def _cloudfront_by_domain(session: Any) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    try:
        cf = session.client("cloudfront")
        marker = ""
        while True:
            kwargs: dict[str, Any] = {}
            if marker:
                kwargs["Marker"] = marker
            resp = cf.list_distributions(**kwargs)
            dlist = resp.get("DistributionList") or {}
            for d in dlist.get("Items") or []:
                domain = (d.get("DomainName") or "").rstrip(".").lower()
                if domain:
                    mapping[domain] = {
                        "id": d.get("Id") or "—",
                        "domain": domain,
                        "status": d.get("Status") or "—",
                        "enabled": bool(d.get("Enabled", False)),
                        "aliases": [
                            (a or "").rstrip(".").lower()
                            for a in (d.get("Aliases", {}).get("Items") or [])
                        ],
                    }
            if not dlist.get("IsTruncated"):
                break
            marker = dlist.get("NextMarker") or ""
            if not marker:
                break
    except Exception:
        pass
    return mapping


def _enrich_distribution(rec: dict[str, Any], cf_map: dict[str, dict[str, Any]]) -> None:
    target = (rec.get("target") or "").rstrip(".").lower()
    if not target or target == "—":
        rec["distribution"] = None
        return
    dist = cf_map.get(target)
    if dist:
        rec["distribution"] = dist
        rec["loadBalancer"] = f"CloudFront {dist['id']}"
        return
    rec["distribution"] = None
    kind = rec.get("targetKind") or ""
    if kind == "Load Balancer":
        rec["loadBalancer"] = target
    elif kind == "CNAME":
        rec["cname"] = target
    else:
        rec["loadBalancer"] = target if kind in ("CloudFront", "Alias", "Load Balancer") else "—"


def _record_from_rr(rr: dict[str, Any], zone: dict[str, Any], hostname: str) -> dict[str, Any] | None:
    name = (rr.get("Name") or "").rstrip(".").lower()
    if name != hostname:
        return None
    routing = _route53_routing_meta(rr)
    target = _route53_record_target(rr)
    alias = bool(rr.get("AliasTarget"))
    rtype = rr.get("Type") or "—"
    is_cname = rtype == "CNAME"
    rec = {
        "name": name,
        "type": rtype,
        "ttl": rr.get("TTL") if rr.get("TTL") is not None else "—",
        "target": target,
        "cname": target if (is_cname or (alias and target != "—")) else "—",
        "alias": alias,
        "targetKind": _target_kind(target, alias),
        "weight": routing["weight"],
        "setIdentifier": routing["setIdentifier"],
        "routingPolicy": routing["routingPolicy"],
        "region": routing["region"],
        "failover": routing["failover"],
        "geoLocation": routing["geoLocation"],
        "trafficPct": None,
        "zoneName": zone.get("name") or "—",
        "zoneId": zone.get("id") or "—",
        "zonePrivate": bool(zone.get("private")),
        "loadBalancer": "—",
        "distribution": None,
    }
    return rec


def fetch_hostname_traffic(
    hostname: str,
    *,
    profile: str = "",
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Look up Route53 records and traffic split for a single hostname."""
    hostname = _normalize_hostname(hostname)
    if not hostname:
        return {"hostname": "", "error": "hostname is required", "records": []}

    profile = (profile or os.environ.get("POD_AWS_PROFILE", "")).strip()
    region = (region or os.environ.get("POD_AWS_REGION", "us-east-1")).strip()

    try:
        session = _aws_session(profile, region)
        r53 = session.client("route53")
        zones = _find_hosted_zones(r53, hostname)
        if not zones:
            return {
                "hostname": hostname,
                "error": f"No hosted zone found for {hostname}",
                "records": [],
                "zone": None,
            }

        cf_map = _cloudfront_by_domain(session)
        records: list[dict[str, Any]] = []
        zone_used: dict[str, Any] | None = None

        for zone in zones:
            raw_sets = _fetch_zone_record_sets_for_hostname(r53, zone["id"], hostname)
            if not raw_sets:
                continue
            zone_used = zone
            for rr in raw_sets:
                rec = _record_from_rr(rr, zone, hostname)
                if rec:
                    records.append(rec)
            if records:
                break

        # If no records in matched zones, try CloudFront alternate domain (CNAME on CF).
        if not records:
            zone_used = zones[0]
            cf_dist = _cloudfront_for_hostname(cf_map, hostname)
            if cf_dist:
                records.append({
                    "name": hostname,
                    "type": "CNAME",
                    "ttl": "—",
                    "target": cf_dist.get("domain") or "—",
                    "cname": cf_dist.get("domain") or "—",
                    "alias": False,
                    "targetKind": "CloudFront",
                    "weight": None,
                    "setIdentifier": "—",
                    "routingPolicy": "cloudfront-alias",
                    "region": "—",
                    "failover": "—",
                    "geoLocation": "—",
                    "trafficPct": None,
                    "zoneName": zone_used.get("name") or "—",
                    "zoneId": zone_used.get("id") or "—",
                    "zonePrivate": bool(zone_used.get("private")),
                    "loadBalancer": f"CloudFront {cf_dist.get('id') or '—'}",
                    "distribution": cf_dist,
                    "source": "cloudfront",
                })

        _apply_traffic_pct(records)
        for rec in records:
            if not rec.get("distribution"):
                _enrich_distribution(rec, cf_map)

        weighted = [r for r in records if r.get("weight") is not None]
        cluster_deploy = _classify_cluster_deployment(records)
        return {
            "hostname": hostname,
            "zone": zone_used,
            "zonesSearched": len(zones),
            "records": records,
            "clusterDeploy": cluster_deploy,
            "summary": {
                "recordCount": len(records),
                "weightedRecords": len(weighted),
                "routingPolicy": records[0]["routingPolicy"] if len(records) == 1 else (
                    "weighted" if weighted else (records[0]["routingPolicy"] if records else "—")
                ),
                "hasTrafficSplit": len(weighted) > 1,
                "cname": next(
                    (r.get("cname") for r in records if r.get("cname") and r.get("cname") != "—"),
                    records[0]["target"] if records else "—",
                ),
                **cluster_deploy,
            },
            "clusterDeploy": cluster_deploy,
            "error": None if records else f"No Route53 record sets found for {hostname} in {len(zones)} matching zone(s)",
        }
    except Exception as exc:
        return {
            "hostname": hostname,
            "error": str(exc),
            "records": [],
            "zone": None,
        }


def _expected_cluster_count() -> int:
    try:
        return max(1, int(os.environ.get("POD_TRAFFIC_EXPECTED_CLUSTERS", "3")))
    except ValueError:
        return 3


def _classify_cluster_deployment(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify whether a hostname has weighted records in all expected clusters."""
    expected = _expected_cluster_count()
    weighted = [r for r in records if r.get("weight") is not None]
    cluster_ids = [
        str(r.get("setIdentifier") or "").strip()
        for r in weighted
        if str(r.get("setIdentifier") or "").strip() not in ("", "—")
    ]
    count = len(weighted)
    if count >= expected:
        status = "full"
    elif count > 0:
        status = "partial"
    elif records:
        status = "simple"
    else:
        status = "missing"
    return {
        "weightedClusterCount": count,
        "expectedClusters": expected,
        "clusterSetIds": cluster_ids,
        "deploymentStatus": status,
        "isFullClusterDeploy": count >= expected,
    }


def _audit_summary_from_hosts(hosts: list[dict[str, Any]]) -> dict[str, Any]:
    expected = _expected_cluster_count()
    full = partial = simple = missing = errors = 0
    for host in hosts:
        deploy = host.get("clusterDeploy") or {}
        status = deploy.get("deploymentStatus") or "missing"
        if host.get("error") and not host.get("records"):
            errors += 1
        if status == "full":
            full += 1
        elif status == "partial":
            partial += 1
        elif status == "simple":
            simple += 1
        else:
            missing += 1
    total = len(hosts)
    return {
        "total": total,
        "expectedClusters": expected,
        "fullClusterDeploy": full,
        "partialClusterDeploy": partial,
        "simpleRouting": simple,
        "missingRecords": missing,
        "notInThreeClusters": total - full,
        "errors": errors,
        "auditedCount": total,
        "notAudited": 0,
        "validated": True,
    }


def fetch_traffic_audit(
    *,
    profile: str = "",
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Scan all configured hostnames for 3-cluster weighted Route53 deployment."""
    hosts_cfg = load_traffic_hosts()
    profile = (profile or os.environ.get("POD_AWS_PROFILE", "")).strip()
    region = (region or os.environ.get("POD_AWS_REGION", "us-east-1")).strip()

    def _scan(entry: dict[str, str]) -> dict[str, Any]:
        result = fetch_hostname_traffic(entry["hostname"], profile=profile, region=region)
        deploy = _classify_cluster_deployment(result.get("records") or [])
        summary = result.get("summary") or {}
        return {
            "id": entry.get("id") or entry["hostname"],
            "hostname": entry["hostname"],
            "label": entry.get("label") or entry["hostname"],
            "error": result.get("error"),
            "recordCount": summary.get("recordCount", len(result.get("records") or [])),
            "weightedRecords": summary.get("weightedRecords", deploy["weightedClusterCount"]),
            "hasTrafficSplit": bool(summary.get("hasTrafficSplit")),
            "routingPolicy": summary.get("routingPolicy") or "—",
            "clusterDeploy": deploy,
        }

    hosts_out: list[dict[str, Any]] = []
    max_workers = min(10, max(1, len(hosts_cfg)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_scan, entry): entry for entry in hosts_cfg}
        for future in as_completed(futures):
            try:
                hosts_out.append(future.result())
            except Exception as exc:
                entry = futures[future]
                hosts_out.append({
                    "id": entry.get("id") or entry["hostname"],
                    "hostname": entry["hostname"],
                    "label": entry.get("label") or entry["hostname"],
                    "error": str(exc),
                    "recordCount": 0,
                    "weightedRecords": 0,
                    "hasTrafficSplit": False,
                    "routingPolicy": "—",
                    "clusterDeploy": _classify_cluster_deployment([]),
                })

    hosts_out.sort(key=lambda h: (h.get("label") or h.get("hostname") or "").lower())
    audit = _audit_summary_from_hosts(hosts_out)
    audit["catalogCount"] = len(hosts_cfg)
    if audit["total"] != len(hosts_cfg):
        audit["validated"] = False
        audit["notAudited"] = max(0, len(hosts_cfg) - audit["total"])
    return {"hosts": hosts_out, "count": len(hosts_out), "audit": audit}


def fetch_traffic_migration(
    hostname: str = "",
    *,
    profile: str = "",
    region: str = "us-east-1",
    list_only: bool = False,
    audit: bool = False,
) -> dict[str, Any]:
    """Fetch traffic migration data for one hostname or all configured hosts."""
    hosts_cfg = load_traffic_hosts()
    if list_only:
        return {"hosts": hosts_cfg, "count": len(hosts_cfg)}
    if audit:
        return fetch_traffic_audit(profile=profile, region=region)

    profile = (profile or os.environ.get("POD_AWS_PROFILE", "")).strip()
    region = (region or os.environ.get("POD_AWS_REGION", "us-east-1")).strip()

    if hostname:
        host_entry = next(
            (h for h in hosts_cfg if _normalize_hostname(h["hostname"]) == _normalize_hostname(hostname)),
            {"id": _normalize_hostname(hostname), "hostname": _normalize_hostname(hostname), "label": hostname},
        )
        result = fetch_hostname_traffic(host_entry["hostname"], profile=profile, region=region)
        return {
            "hosts": [{
                **host_entry,
                **result,
            }],
            "count": 1,
        }

    hosts_out: list[dict[str, Any]] = []
    for entry in hosts_cfg:
        result = fetch_hostname_traffic(entry["hostname"], profile=profile, region=region)
        hosts_out.append({**entry, **result})

    return {"hosts": hosts_out, "count": len(hosts_out)}
