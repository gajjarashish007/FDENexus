"""Manifest builders and guardrails for M04 write operations.

Forms in the UI never send raw kubectl arguments. They send a template name and parameters;
this module validates them and builds Kubernetes objects, which are applied with
`kubectl apply -f -` after a server-side dry run. Raw YAML is accepted too, but only for an
allow-listed set of namespaced kinds (no Secrets, no cluster-wide RBAC, no CRDs/webhooks).
"""
from __future__ import annotations

import re

import yaml

from k8s_client import KubeError, check_name, check_ns

MANAGED = {"app.kubernetes.io/managed-by": "fde-nexus"}
SYSTEM_NS = {"kube-system", "kube-public", "kube-node-lease", "default"}
APPLY_KINDS = {
    "Deployment", "StatefulSet", "DaemonSet", "CronJob", "Job", "Service", "Ingress", "ConfigMap",
    "HorizontalPodAutoscaler", "PersistentVolumeClaim", "NetworkPolicy", "ResourceQuota", "LimitRange",
    "RoleBinding", "Role", "ServiceAccount", "Namespace", "PodDisruptionBudget",
}
DELETE_KINDS = {
    "deployment", "statefulset", "daemonset", "cronjob", "job", "service", "ingress", "configmap", "hpa",
    "pvc", "networkpolicy", "resourcequota", "limitrange", "rolebinding", "namespace",
}
CLUSTER_ROLES = {"view", "edit", "admin"}
IMAGE_RE = re.compile(r"^[a-z0-9]+([._/:@-][a-zA-Z0-9]+)*$")
QTY_CPU = re.compile(r"^\d+(\.\d+)?m?$")
QTY_MEM = re.compile(r"^\d+(Ki|Mi|Gi|Ti|K|M|G|T)?$")
HOST_RE = re.compile(r"^(\*\.)?[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?(\.[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?)+$")
SUBJECT_RE = re.compile(r"^[A-Za-z0-9@:._/+=,-]{1,200}$")


def _int(v, lo, hi, what):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise KubeError(f"{what} must be a whole number.") from None
    if not lo <= n <= hi:
        raise KubeError(f"{what} must be between {lo} and {hi}.")
    return n


def _qty(v, rx, what, required=False):
    v = str(v or "").strip()
    if not v:
        if required:
            raise KubeError(f"{what} is required.")
        return ""
    if not rx.match(v):
        raise KubeError(f"{what}: invalid quantity '{v}'.")
    return v


def _meta(name, ns=None, labels=None):
    m = {"name": name, "labels": {**MANAGED, **(labels or {})}}
    if ns:
        m["namespace"] = ns
    return m


def _labels(raw) -> dict:
    out = {}
    for part in [p.strip() for p in str(raw or "").split(",") if p.strip()]:
        if "=" not in part:
            raise KubeError(f"Label '{part}' must look like key=value.")
        k, v = part.split("=", 1)
        if not re.fullmatch(r"([a-z0-9.-]+/)?[A-Za-z0-9][-A-Za-z0-9_.]{0,62}", k) or not re.fullmatch(r"[A-Za-z0-9]([-A-Za-z0-9_.]{0,61}[A-Za-z0-9])?|", v):
            raise KubeError(f"Invalid label {part}.")
        out[k] = v
    return out


# ---------------------------------------------------------------- templates
def t_deployment(p):
    name, ns = check_name(p.get("name")), check_ns(p.get("namespace"))
    image = str(p.get("image", "")).strip()
    if not IMAGE_RE.match(image) or len(image) > 300:
        raise KubeError("Image must look like registry/repo:tag.")
    replicas = _int(p.get("replicas", 2), 0, 50, "Replicas")
    port = _int(p.get("port", 8080), 1, 65535, "Container port") if p.get("port") not in (None, "") else None
    res = {}
    req = {k: v for k, v in (("cpu", _qty(p.get("cpu", "100m"), QTY_CPU, "CPU request")), ("memory", _qty(p.get("memory", "128Mi"), QTY_MEM, "Memory request"))) if v}
    lim = {k: v for k, v in (("memory", _qty(p.get("memory_limit") or p.get("memory", "128Mi"), QTY_MEM, "Memory limit")),) if v}
    if req:
        res["requests"] = req
    if lim:
        res["limits"] = lim
    sel = {"app.kubernetes.io/name": name}
    c = {"name": name, "image": image, "resources": res,
         "securityContext": {"allowPrivilegeEscalation": False, "runAsNonRoot": bool(p.get("run_as_non_root", True))}}
    if port:
        c["ports"] = [{"containerPort": port}]
        if p.get("probe_path"):
            path = str(p["probe_path"])
            if not re.fullmatch(r"/[A-Za-z0-9._~/-]{0,200}", path):
                raise KubeError("Probe path must start with / .")
            c["readinessProbe"] = {"httpGet": {"path": path, "port": port}, "periodSeconds": 10}
    docs = [{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": _meta(name, ns, sel),
             "spec": {"replicas": replicas, "selector": {"matchLabels": sel},
                      "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1}},
                      "template": {"metadata": {"labels": {**sel, **MANAGED}}, "spec": {"containers": [c]}}}}]
    svc = p.get("service", "ClusterIP")
    if port and svc in ("ClusterIP", "LoadBalancer", "NodePort"):
        spec = {"type": svc, "selector": sel, "ports": [{"port": _int(p.get("service_port", 80), 1, 65535, "Service port"), "targetPort": port}]}
        meta = _meta(name, ns, sel)
        if svc == "LoadBalancer" and p.get("internal_lb", True):
            meta["annotations"] = {"service.beta.kubernetes.io/aws-load-balancer-scheme": "internal"}
        docs.append({"apiVersion": "v1", "kind": "Service", "metadata": meta, "spec": spec})
    if replicas >= 2 and p.get("pdb", True):
        docs.append({"apiVersion": "policy/v1", "kind": "PodDisruptionBudget", "metadata": _meta(name, ns, sel),
                     "spec": {"minAvailable": 1, "selector": {"matchLabels": sel}}})
    return docs


def t_namespace(p):
    name = check_ns(p.get("name"))
    if name in SYSTEM_NS:
        raise KubeError("That name is reserved.")
    labels = _labels(p.get("labels"))
    if p.get("team"):
        labels["team"] = check_ns(str(p["team"]).lower())
    labels["pod-security.kubernetes.io/enforce"] = p.get("pod_security", "baseline") if p.get("pod_security") in ("privileged", "baseline", "restricted") else "baseline"
    docs = [{"apiVersion": "v1", "kind": "Namespace", "metadata": _meta(name, None, labels)}]
    cpu, mem = _qty(p.get("quota_cpu"), QTY_CPU, "CPU quota"), _qty(p.get("quota_memory"), QTY_MEM, "Memory quota")
    pods = _int(p["quota_pods"], 1, 5000, "Pod quota") if p.get("quota_pods") not in (None, "") else None
    hard = {k: v for k, v in (("requests.cpu", cpu), ("requests.memory", mem), ("limits.memory", mem), ("pods", str(pods) if pods else "")) if v}
    if hard:
        docs.append({"apiVersion": "v1", "kind": "ResourceQuota", "metadata": _meta("default-quota", name), "spec": {"hard": hard}})
        docs.append({"apiVersion": "v1", "kind": "LimitRange", "metadata": _meta("default-limits", name),
                     "spec": {"limits": [{"type": "Container", "defaultRequest": {"cpu": "100m", "memory": "128Mi"}, "default": {"memory": "256Mi"}}]}})
    if p.get("default_deny", True):
        docs += t_networkpolicy({"namespace": name, "policy": "default-deny"})
        docs += t_networkpolicy({"namespace": name, "policy": "allow-same-namespace"})
    return docs


def t_hpa(p):
    ns, target = check_ns(p.get("namespace")), check_name(p.get("target"))
    kind = p.get("kind", "Deployment") if p.get("kind") in ("Deployment", "StatefulSet") else "Deployment"
    lo, hi = _int(p.get("min", 2), 1, 100, "Min replicas"), _int(p.get("max", 10), 1, 500, "Max replicas")
    if lo > hi:
        raise KubeError("Min replicas must not exceed max.")
    cpu = _int(p.get("cpu", 70), 10, 100, "CPU target %")
    metrics = [{"type": "Resource", "resource": {"name": "cpu", "target": {"type": "Utilization", "averageUtilization": cpu}}}]
    if p.get("memory"):
        metrics.append({"type": "Resource", "resource": {"name": "memory", "target": {"type": "Utilization", "averageUtilization": _int(p["memory"], 10, 100, "Memory target %")}}})
    return [{"apiVersion": "autoscaling/v2", "kind": "HorizontalPodAutoscaler", "metadata": _meta(check_name(p.get("name") or target), ns),
             "spec": {"scaleTargetRef": {"apiVersion": "apps/v1", "kind": kind, "name": target}, "minReplicas": lo, "maxReplicas": hi, "metrics": metrics,
                      "behavior": {"scaleDown": {"stabilizationWindowSeconds": 300}}}}]


def t_ingress(p):
    name, ns, svc = check_name(p.get("name")), check_ns(p.get("namespace")), check_name(p.get("service"), "service")
    host = str(p.get("host", "")).strip().lower()
    if host and not HOST_RE.match(host):
        raise KubeError("Host must be a DNS name like app.example.com.")
    path = str(p.get("path") or "/")
    if not re.fullmatch(r"/[A-Za-z0-9._~/-]{0,200}", path):
        raise KubeError("Path must start with / .")
    cls = str(p.get("class") or "alb")
    if not re.fullmatch(r"[a-z0-9-]{1,60}", cls):
        raise KubeError("Invalid ingress class.")
    rule = {"http": {"paths": [{"path": path, "pathType": "Prefix", "backend": {"service": {"name": svc, "port": {"number": _int(p.get("port", 80), 1, 65535, "Service port")}}}}]}}
    if host:
        rule["host"] = host
    meta = _meta(name, ns)
    if cls == "alb":
        meta["annotations"] = {"alb.ingress.kubernetes.io/scheme": "internet-facing" if p.get("public") else "internal",
                               "alb.ingress.kubernetes.io/target-type": "ip"}
        if p.get("certificate_arn"):
            arn = str(p["certificate_arn"])
            if not re.fullmatch(r"arn:aws[a-z-]*:acm:[a-z0-9-]+:\d{12}:certificate/[0-9a-f-]{36}", arn):
                raise KubeError("Invalid ACM certificate ARN.")
            meta["annotations"].update({"alb.ingress.kubernetes.io/certificate-arn": arn,
                                        "alb.ingress.kubernetes.io/listen-ports": '[{"HTTP": 80}, {"HTTPS": 443}]',
                                        "alb.ingress.kubernetes.io/ssl-redirect": "443"})
    spec = {"ingressClassName": cls, "rules": [rule]}
    if p.get("tls_secret"):
        spec["tls"] = [{"hosts": [host] if host else [], "secretName": check_name(p["tls_secret"], "TLS secret")}]
    return [{"apiVersion": "networking.k8s.io/v1", "kind": "Ingress", "metadata": meta, "spec": spec}]


def t_pvc(p):
    name, ns = check_name(p.get("name")), check_ns(p.get("namespace"))
    size = _qty(p.get("size", "10Gi"), QTY_MEM, "Size", required=True)
    mode = p.get("access_mode", "ReadWriteOnce")
    if mode not in ("ReadWriteOnce", "ReadWriteMany", "ReadOnlyMany", "ReadWriteOncePod"):
        raise KubeError("Invalid access mode.")
    spec = {"accessModes": [mode], "resources": {"requests": {"storage": size}}}
    if p.get("storage_class"):
        spec["storageClassName"] = check_name(p["storage_class"], "storage class")
    return [{"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": _meta(name, ns), "spec": spec}]


def t_quota(p):
    ns = check_ns(p.get("namespace"))
    hard = {}
    for key, rx, label in (("requests.cpu", QTY_CPU, "CPU requests"), ("limits.cpu", QTY_CPU, "CPU limits"),
                           ("requests.memory", QTY_MEM, "Memory requests"), ("limits.memory", QTY_MEM, "Memory limits"),
                           ("requests.storage", QTY_MEM, "Storage")):
        v = _qty(p.get(key.replace(".", "_")), rx, label)
        if v:
            hard[key] = v
    for key in ("pods", "services", "persistentvolumeclaims"):
        if p.get(key) not in (None, ""):
            hard[key] = str(_int(p[key], 0, 10000, key))
    if not hard:
        raise KubeError("Set at least one limit.")
    return [{"apiVersion": "v1", "kind": "ResourceQuota", "metadata": _meta(check_name(p.get("name") or "default-quota"), ns), "spec": {"hard": hard}}]


def t_rolebinding(p):
    ns = check_ns(p.get("namespace"))
    role = p.get("role")
    if role not in CLUSTER_ROLES:
        raise KubeError("Role must be view, edit or admin.")
    kind = p.get("subject_kind", "Group")
    if kind not in ("User", "Group", "ServiceAccount"):
        raise KubeError("Subject must be a User, Group or ServiceAccount.")
    subj = str(p.get("subject", "")).strip()
    if not SUBJECT_RE.match(subj):
        raise KubeError("Enter the user, group or service account name.")
    s = {"kind": kind, "name": subj}
    if kind == "ServiceAccount":
        s["name"], s["namespace"] = check_name(subj, "service account"), ns
    else:
        s["apiGroup"] = "rbac.authorization.k8s.io"
    name = check_name(p.get("name") or f"{role}-{re.sub(r'[^a-z0-9-]+', '-', subj.lower()).strip('-')[:40]}")
    return [{"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "RoleBinding", "metadata": _meta(name, ns),
             "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": role}, "subjects": [s]}]


def t_networkpolicy(p):
    ns = check_ns(p.get("namespace"))
    pol = p.get("policy")
    if pol == "default-deny":
        return [{"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": _meta("default-deny-ingress", ns),
                 "spec": {"podSelector": {}, "policyTypes": ["Ingress"]}}]
    if pol == "allow-same-namespace":
        return [{"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": _meta("allow-same-namespace", ns),
                 "spec": {"podSelector": {}, "policyTypes": ["Ingress"], "ingress": [{"from": [{"podSelector": {}}]}]}}]
    if pol == "allow-from-namespace":
        src = check_ns(p.get("from_namespace"))
        return [{"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": _meta(f"allow-from-{src}", ns),
                 "spec": {"podSelector": {}, "policyTypes": ["Ingress"],
                          "ingress": [{"from": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": src}}}]}]}}]
    if pol == "allow-port":
        port = _int(p.get("port"), 1, 65535, "Port")
        app = check_name(p.get("app"), "app label")
        return [{"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": _meta(f"allow-{app}-{port}", ns),
                 "spec": {"podSelector": {"matchLabels": {"app.kubernetes.io/name": app}}, "policyTypes": ["Ingress"],
                          "ingress": [{"ports": [{"port": port, "protocol": "TCP"}]}]}}]
    raise KubeError("Pick a policy type.")


TEMPLATES = {"deployment": t_deployment, "namespace": t_namespace, "hpa": t_hpa, "ingress": t_ingress, "pvc": t_pvc,
             "quota": t_quota, "rolebinding": t_rolebinding, "networkpolicy": t_networkpolicy}


def build(template: str, params: dict) -> list[dict]:
    if template not in TEMPLATES:
        raise KubeError("Unknown template.")
    return TEMPLATES[template](params or {})


def parse_yaml(text: str, is_admin: bool) -> list[dict]:
    if not text or len(text) > 200_000:
        raise KubeError("Paste a manifest (up to 200 KB).")
    try:
        docs = [d for d in yaml.safe_load_all(text) if d]
    except yaml.YAMLError as e:
        raise KubeError(f"Invalid YAML: {str(e)[:200]}") from None
    if not docs or len(docs) > 50:
        raise KubeError("1 to 50 objects per apply.")
    for d in docs:
        if not isinstance(d, dict) or not d.get("kind") or not d.get("apiVersion"):
            raise KubeError("Every document needs apiVersion and kind.")
        if d["kind"] not in APPLY_KINDS:
            raise KubeError(f"{d['kind']} cannot be applied from the portal (allowed: {', '.join(sorted(APPLY_KINDS))}).")
        meta = d.setdefault("metadata", {})
        check_name(meta.get("name", ""), f"{d['kind']} name")
        if d["kind"] != "Namespace":
            ns = meta.get("namespace")
            if not ns:
                raise KubeError(f"{d['kind']} {meta['name']}: set metadata.namespace.")
            check_ns(ns)
            if ns in ("kube-system", "kube-public", "kube-node-lease") and not is_admin:
                raise KubeError("Only admins can apply into system namespaces.")
        meta.setdefault("labels", {}).update(MANAGED)
    return docs


def to_yaml(docs: list[dict]) -> str:
    return yaml.safe_dump_all(docs, sort_keys=False, default_flow_style=False)


def namespaces_of(docs: list[dict]) -> set[str]:
    return {d["metadata"].get("namespace") or d["metadata"]["name"] for d in docs}
