"""Pure functions that turn kubectl JSON into UI rows. Ported from pod/pod-server.py
(status rules match `kubectl get pods`), plus pod diagnosis and generic kind summaries.
No I/O here, so everything is unit-testable with fixture JSON."""
from __future__ import annotations

from datetime import datetime, timezone

SYSTEM_NAMESPACES = {"kube-system", "kube-public", "kube-node-lease"}

WAITING_REASONS = frozenset({
    "CrashLoopBackOff", "ImagePullBackOff", "ContainerCreating", "ErrImagePull", "PodInitializing",
    "CreateContainerConfigError", "CreateContainerError",
})
ERROR_STATUSES = frozenset({
    "CrashLoopBackOff", "ImagePullBackOff", "Error", "Failed", "Terminated", "ErrImagePull", "Evicted",
    "OOMKilled", "CreateContainerConfigError", "CreateContainerError",
})
# pods.sh cleanup targets
BAD_POD_STATUSES = frozenset({"Error", "ErrImagePull", "Evicted", "CrashLoopBackOff", "ImagePullBackOff", "Failed", "Unknown"})


def age(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return ts
    s = int((datetime.now(timezone.utc) - t).total_seconds())
    if s < 0:
        return "0s"
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= n:
            return f"{s // n}{unit}"
    return f"{s}s"


# ---------------------------------------------------------------- pods
def _statuses(pod):
    st = pod.get("status", {}) or {}
    return st.get("containerStatuses", []) or [], st.get("initContainerStatuses", []) or []


def pod_display_status(pod: dict) -> str:
    phase = (pod.get("status") or {}).get("phase", "Unknown")
    if (pod.get("metadata") or {}).get("deletionTimestamp"):
        return "Terminating"
    if (pod.get("status") or {}).get("reason") == "Evicted":
        return "Evicted"
    if phase == "Succeeded":
        return "Completed"
    cs, init = _statuses(pod)
    for c in cs:
        state = c.get("state") or {}
        if "waiting" in state and state["waiting"].get("reason") in WAITING_REASONS:
            return state["waiting"]["reason"]
        if "terminated" in state and phase not in ("Succeeded", "Failed"):
            r = state["terminated"].get("reason", "")
            if r in ("CrashLoopBackOff", "Error", "OOMKilled", "Evicted"):
                return r
            if r == "Completed" and phase != "Running":
                return "Completed"
    if phase == "Pending":
        for c in init:
            w = (c.get("state") or {}).get("waiting") or {}
            if w.get("reason"):
                return "Init:" + w["reason"]
    return phase


def pod_ready(pod: dict) -> tuple[int, int]:
    cs, _ = _statuses(pod)
    total = max(len(cs), len((pod.get("spec") or {}).get("containers", []) or []))
    if (pod.get("status") or {}).get("phase") in ("Succeeded", "Failed"):
        return 0, total
    return sum(1 for c in cs if c.get("ready") and "running" in (c.get("state") or {})), total


def pod_status_class(status: str, ready: int, total: int, phase: str) -> str:
    if status == "Running" and total and ready == total:
        return "running"
    if status in ERROR_STATUSES:
        return "error"
    if status == "Completed" or phase == "Succeeded":
        return "completed"
    if phase == "Pending" or status in WAITING_REASONS or status.startswith("Init:") or status == "Terminating":
        return "pending"
    if phase == "Running" and total and ready < total:
        return "pending"
    return "other"


def pod_summary(pod: dict) -> dict:
    meta, spec, st = pod.get("metadata") or {}, pod.get("spec") or {}, pod.get("status") or {}
    ready, total = pod_ready(pod)
    status = pod_display_status(pod)
    cls = pod_status_class(status, ready, total, st.get("phase", ""))
    cs, init = _statuses(pod)
    last = ""
    for c in cs:
        t = (c.get("lastState") or {}).get("terminated") or {}
        if t.get("reason"):
            last = t["reason"]
    owner = (meta.get("ownerReferences") or [{}])[0]
    return {
        "name": meta.get("name", ""), "namespace": meta.get("namespace", "default"),
        "ready": f"{ready}/{total}", "status": "Pending" if cls == "pending" and status == "Running" else status,
        "statusClass": cls, "restarts": sum(c.get("restartCount", 0) for c in cs + init),
        "lastTermination": last, "age": age(meta.get("creationTimestamp")), "created": meta.get("creationTimestamp"),
        "ip": st.get("podIP", ""), "node": spec.get("nodeName", ""), "qos": st.get("qosClass", ""),
        "containers": [c.get("name", "") for c in spec.get("containers", []) or []],
        "owner": f"{owner.get('kind', '')}/{owner.get('name', '')}" if owner.get("kind") else "",
        "system": meta.get("namespace") in SYSTEM_NAMESPACES,
    }


def pod_stats(rows: list[dict]) -> dict:
    out = {"total": len(rows), "running": 0, "pending": 0, "error": 0, "completed": 0, "other": 0, "restarts": 0}
    for r in rows:
        out[r["statusClass"]] = out.get(r["statusClass"], 0) + 1
        out["restarts"] += r["restarts"]
    return out


def bad_pods(rows: list[dict], include_system: bool = False) -> list[dict]:
    return [r for r in rows if r["status"] in BAD_POD_STATUSES and (include_system or not r["system"])]


# ---------------------------------------------------------------- diagnosis (pod health + scheduling analysis)
def diagnose(pod: dict, events: list[dict]) -> list[dict]:
    """Rule-based hints for one pod from its status and warning events."""
    hints = []
    st = pod.get("status") or {}
    spec = pod.get("spec") or {}
    for c in st.get("containerStatuses", []) or []:
        name = c.get("name")
        w = (c.get("state") or {}).get("waiting") or {}
        last = (c.get("lastState") or {}).get("terminated") or {}
        limits = next(((x.get("resources") or {}).get("limits") or {} for x in spec.get("containers", []) if x.get("name") == name), {})
        if last.get("reason") == "OOMKilled" or (c.get("state") or {}).get("terminated", {}).get("reason") == "OOMKilled":
            hints.append({"severity": "error", "title": f"{name}: killed for running out of memory (OOMKilled)",
                          "detail": f"Memory limit is {limits.get('memory', 'not set')}. Raise the limit or fix the leak; check `logs --previous`."})
        if w.get("reason") == "CrashLoopBackOff":
            hints.append({"severity": "error", "title": f"{name}: crash loop ({c.get('restartCount', 0)} restarts)",
                          "detail": f"Last exit: {last.get('reason', '?')} code {last.get('exitCode', '?')}. Open the previous container logs to see why it exits."})
        if w.get("reason") in ("ImagePullBackOff", "ErrImagePull"):
            hints.append({"severity": "error", "title": f"{name}: image cannot be pulled",
                          "detail": f"Image {c.get('image')}: check the tag exists, the registry is reachable and imagePullSecrets/IRSA allow the pull. {w.get('message', '')[:200]}"})
        if w.get("reason") in ("CreateContainerConfigError", "CreateContainerError"):
            hints.append({"severity": "error", "title": f"{name}: container config error",
                          "detail": (w.get("message") or "A referenced ConfigMap or Secret key is probably missing.")[:300]})
        if c.get("ready") is False and "running" in (c.get("state") or {}):
            hints.append({"severity": "warning", "title": f"{name}: running but not ready",
                          "detail": "The readiness probe is failing. Check the probe path/port and the app startup time."})
    if st.get("phase") == "Pending":
        sched = [e for e in events if e.get("reason") == "FailedScheduling"]
        if sched:
            msg = sched[-1].get("message", "")
            tip = ("Not enough CPU or memory on any node: lower requests or add capacity (node group max / Karpenter)."
                   if "Insufficient" in msg else
                   "No node matches the pod's taints, affinity or node selector." if ("taint" in msg or "affinity" in msg or "selector" in msg) else
                   "A PersistentVolumeClaim is not bound yet." if "persistentvolumeclaim" in msg.lower() else
                   "See the scheduler message.")
            hints.append({"severity": "error", "title": "Pod cannot be scheduled", "detail": f"{tip} Scheduler: {msg[:300]}"})
        elif not spec.get("nodeName"):
            hints.append({"severity": "warning", "title": "Waiting for scheduling", "detail": "No scheduling event yet."})
    if st.get("reason") == "Evicted":
        hints.append({"severity": "warning", "title": "Evicted", "detail": (st.get("message") or "Node pressure (memory/disk).")[:300]})
    for e in events:
        if e.get("type") == "Warning" and e.get("reason") in ("Unhealthy", "BackOff", "FailedMount", "FailedAttachVolume"):
            if not any(e.get("reason") in h["title"] for h in hints):
                hints.append({"severity": "warning", "title": e["reason"], "detail": (e.get("message") or "")[:300]})
    if not hints:
        hints.append({"severity": "ok", "title": "No problems detected", "detail": "Status, restarts and recent events look normal."})
    return hints


# ---------------------------------------------------------------- nodes / workloads
def node_summary(n: dict) -> dict:
    meta, spec, st = n.get("metadata") or {}, n.get("spec") or {}, n.get("status") or {}
    ready = next((c.get("status") for c in st.get("conditions", []) or [] if c.get("type") == "Ready"), "Unknown")
    status = "SchedulingDisabled" if spec.get("unschedulable") else ("Ready" if ready == "True" else "NotReady")
    pressure = [c["type"] for c in st.get("conditions", []) or [] if c.get("type") != "Ready" and c.get("status") == "True"]
    labels = meta.get("labels") or {}
    info = st.get("nodeInfo") or {}
    addr = {a.get("type"): a.get("address") for a in st.get("addresses", []) or []}
    alloc = st.get("allocatable") or {}
    return {
        "name": meta.get("name", ""), "status": status, "pressure": pressure,
        "roles": ",".join(k.split("/", 1)[1] for k in labels if k.startswith("node-role.kubernetes.io/")) or "worker",
        "version": info.get("kubeletVersion", ""), "os": info.get("osImage", ""), "runtime": info.get("containerRuntimeVersion", ""),
        "internalIp": addr.get("InternalIP", ""), "instanceType": labels.get("node.kubernetes.io/instance-type", ""),
        "zone": labels.get("topology.kubernetes.io/zone", ""), "nodegroup": labels.get("eks.amazonaws.com/nodegroup") or labels.get("karpenter.sh/nodepool", ""),
        "capacityType": labels.get("eks.amazonaws.com/capacityType") or labels.get("karpenter.sh/capacity-type", ""),
        "cpu": alloc.get("cpu", ""), "memory": alloc.get("memory", ""), "pods": alloc.get("pods", ""),
        "taints": [f"{t.get('key')}={t.get('value', '')}:{t.get('effect')}" for t in spec.get("taints", []) or []],
        "age": age(meta.get("creationTimestamp")),
    }


def workload_summary(item: dict, kind: str) -> dict:
    meta, spec, st = item.get("metadata") or {}, item.get("spec") or {}, item.get("status") or {}
    base = {"name": meta.get("name", ""), "namespace": meta.get("namespace", ""), "age": age(meta.get("creationTimestamp")),
            "system": meta.get("namespace") in SYSTEM_NAMESPACES}
    containers = ((spec.get("template") or {}).get("spec") or {}).get("containers", []) or []
    base["images"] = [c.get("image", "") for c in containers]
    if kind == "daemonsets":
        want, ready = st.get("desiredNumberScheduled", 0), st.get("numberReady", 0)
        return {**base, "ready": f"{ready}/{want}", "replicas": want, "readyReplicas": ready, "upToDate": st.get("updatedNumberScheduled", 0),
                "available": st.get("numberAvailable", 0), "healthy": ready == want}
    want, ready = spec.get("replicas", 0) or 0, st.get("readyReplicas", 0) or 0
    return {**base, "ready": f"{ready}/{want}", "replicas": want, "readyReplicas": ready, "upToDate": st.get("updatedReplicas", 0) or 0,
            "available": st.get("availableReplicas", 0) or 0, "healthy": ready == want}


def generic_summary(item: dict, kind: str) -> dict:
    meta, spec, st = item.get("metadata") or {}, item.get("spec") or {}, item.get("status") or {}
    row = {"name": meta.get("name", ""), "namespace": meta.get("namespace", ""), "age": age(meta.get("creationTimestamp")),
           "system": meta.get("namespace") in SYSTEM_NAMESPACES}
    if kind == "services":
        lb = ((st.get("loadBalancer") or {}).get("ingress") or [{}])[0]
        row.update(type=spec.get("type", ""), clusterIp=spec.get("clusterIP", ""), external=lb.get("hostname") or lb.get("ip") or "",
                   ports=", ".join(f"{p.get('port')}{'/' + p['protocol'] if p.get('protocol') != 'TCP' else ''}{':' + str(p['nodePort']) if p.get('nodePort') else ''}" for p in spec.get("ports", []) or []))
    elif kind == "ingresses":
        lb = ((st.get("loadBalancer") or {}).get("ingress") or [{}])[0]
        row.update(className=spec.get("ingressClassName", ""), hosts=", ".join(r.get("host", "*") for r in spec.get("rules", []) or []),
                   address=lb.get("hostname") or lb.get("ip") or "", tls=bool(spec.get("tls")))
    elif kind == "configmaps":
        row.update(keys=len(item.get("data") or {}) + len(item.get("binaryData") or {}))
    elif kind == "hpa":
        ref = spec.get("scaleTargetRef") or {}
        targets = []
        for m in spec.get("metrics", []) or []:
            r = (m.get("resource") or {})
            tgt = (r.get("target") or {}).get("averageUtilization")
            cur = next(((c.get("resource") or {}).get("current", {}).get("averageUtilization") for c in st.get("currentMetrics", []) or []
                        if (c.get("resource") or {}).get("name") == r.get("name")), None)
            if r.get("name"):
                targets.append(f"{r['name']} {cur if cur is not None else '?'}%/{tgt}%")
        row.update(reference=f"{ref.get('kind', '')}/{ref.get('name', '')}", min=spec.get("minReplicas", 1), max=spec.get("maxReplicas"),
                   current=st.get("currentReplicas"), desired=st.get("desiredReplicas"), targets=", ".join(targets))
    elif kind == "pvc":
        row.update(status=st.get("phase", ""), volume=spec.get("volumeName", ""), capacity=(st.get("capacity") or {}).get("storage", ""),
                   storageClass=spec.get("storageClassName", ""), access=",".join(spec.get("accessModes", []) or []))
    elif kind == "cronjobs":
        row.update(schedule=spec.get("schedule", ""), suspend=bool(spec.get("suspend")), lastSchedule=age(st.get("lastScheduleTime")),
                   active=len(st.get("active", []) or []))
    elif kind == "namespaces":
        row.update(status=st.get("phase", ""), labels=meta.get("labels") or {}, system=meta.get("name") in SYSTEM_NAMESPACES)
    elif kind == "storageclasses":
        ann = meta.get("annotations") or {}
        row.update(provisioner=item.get("provisioner", ""), reclaim=item.get("reclaimPolicy", ""), binding=item.get("volumeBindingMode", ""),
                   expansion=bool(item.get("allowVolumeExpansion")), default=ann.get("storageclass.kubernetes.io/is-default-class") == "true",
                   type=(item.get("parameters") or {}).get("type", ""))
    elif kind == "pv":
        ref = spec.get("claimRef") or {}
        row.update(status=st.get("phase", ""), capacity=(spec.get("capacity") or {}).get("storage", ""), reclaim=spec.get("persistentVolumeReclaimPolicy", ""),
                   storageClass=spec.get("storageClassName", ""), claim=f"{ref.get('namespace', '')}/{ref.get('name', '')}" if ref else "")
    elif kind in ("rolebindings", "clusterrolebindings"):
        ref = item.get("roleRef") or {}
        row.update(role=f"{ref.get('kind', '')}/{ref.get('name', '')}", subjects=", ".join(f"{x.get('kind')}:{x.get('name')}" for x in item.get("subjects") or []),
                   managed=(meta.get("labels") or {}).get("app.kubernetes.io/managed-by") == "fde-nexus")
        if kind == "clusterrolebindings":
            row["system"] = ref.get("name", "").startswith("system:") or meta.get("name", "").startswith(("system:", "eks:"))
    elif kind == "networkpolicies":
        row.update(selector=", ".join(f"{k}={v}" for k, v in ((spec.get("podSelector") or {}).get("matchLabels") or {}).items()) or "all pods",
                   types=", ".join(spec.get("policyTypes", [])), ingressRules=len(spec.get("ingress", []) or []), egressRules=len(spec.get("egress", []) or []))
    elif kind == "limitranges":
        lim = (spec.get("limits") or [{}])[0]
        row.update(defaults=", ".join(f"{k}={v}" for k, v in (lim.get("default") or {}).items()),
                   requests=", ".join(f"{k}={v}" for k, v in (lim.get("defaultRequest") or {}).items()))
    elif kind == "resourcequotas":
        used, hard = st.get("used") or {}, st.get("hard") or spec.get("hard") or {}
        row.update(usage=", ".join(f"{k} {used.get(k, '0')}/{v}" for k, v in hard.items()))
    return row


def event_summary(e: dict) -> dict:
    obj = e.get("involvedObject") or e.get("regarding") or {}
    ts = e.get("lastTimestamp") or e.get("eventTime") or (e.get("metadata") or {}).get("creationTimestamp")
    return {"type": e.get("type", ""), "reason": e.get("reason", ""), "object": f"{obj.get('kind', '')}/{obj.get('name', '')}",
            "objectName": obj.get("name", ""), "namespace": (e.get("metadata") or {}).get("namespace", ""),
            "message": (e.get("message") or e.get("note") or "")[:500], "count": e.get("count") or (e.get("series") or {}).get("count") or 1,
            "last": age(ts), "ts": ts or ""}
