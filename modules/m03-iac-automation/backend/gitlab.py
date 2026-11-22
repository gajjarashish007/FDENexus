"""Minimal GitLab REST v4 client used to publish approved changes as merge requests.

Repository settings (URL, project, target branch, path prefix) are editable in the
portal. The access token is read ONLY from the GITLAB_TOKEN environment variable and
is never stored, returned by the API, or logged. Use a project access token with the
`api` scope and the Developer role (it can push branches and open MRs; merging is
still governed by the project's own approval rules).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class GitLabError(Exception):
    pass


def token_present() -> bool:
    return bool(os.environ.get("GITLAB_TOKEN"))


class GitLab:
    def __init__(self, url: str, project: str, timeout: int = 20):
        if not url or not project:
            raise GitLabError("GitLab URL and project are required.")
        if not url.startswith("https://") and not url.startswith("http://localhost") and not url.startswith("http://127.0.0.1"):
            raise GitLabError("GitLab URL must use https.")
        self.base = url.rstrip("/") + "/api/v4"
        self.project = urllib.parse.quote(str(project), safe="")
        self.timeout = timeout
        tok = os.environ.get("GITLAB_TOKEN")
        if not tok:
            raise GitLabError("GITLAB_TOKEN is not set on the portal host.")
        self._headers = {"PRIVATE-TOKEN": tok, "Content-Type": "application/json"}

    def _req(self, method: str, path: str, body: dict | None = None, ok404: bool = False):
        url = f"{self.base}/projects/{self.project}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=self._headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if ok404 and e.code == 404:
                return None
            detail = e.read().decode(errors="replace")[:300]
            raise GitLabError(f"GitLab {method} {path.split('?')[0]} failed ({e.code}): {detail}") from None
        except urllib.error.URLError as e:
            raise GitLabError(f"Cannot reach GitLab: {e.reason}") from None

    # ---- read
    def project_info(self) -> dict:
        p = self._req("GET", "")
        return {"id": p.get("id"), "path": p.get("path_with_namespace"), "default_branch": p.get("default_branch"),
                "web_url": p.get("web_url")}

    def file_exists(self, path: str, ref: str) -> bool:
        q = urllib.parse.quote(path, safe="")
        return self._req("GET", f"/repository/files/{q}?ref={urllib.parse.quote(ref)}", ok404=True) is not None

    def merge_request(self, iid: int) -> dict:
        mr = self._req("GET", f"/merge_requests/{int(iid)}")
        pipe = mr.get("head_pipeline") or {}
        return {"iid": mr.get("iid"), "state": mr.get("state"), "web_url": mr.get("web_url"),
                "merge_status": mr.get("detailed_merge_status") or mr.get("merge_status"),
                "pipeline_status": pipe.get("status"), "pipeline_url": pipe.get("web_url"),
                "merged_by": (mr.get("merged_by") or {}).get("username")}

    # ---- write
    def commit_files(self, branch: str, start_branch: str, message: str, files: dict[str, str | None]) -> dict:
        actions = []
        for path, content in files.items():
            exists = self.file_exists(path, start_branch)
            if content is None:
                if exists:
                    actions.append({"action": "delete", "file_path": path})
                continue
            actions.append({"action": "update" if exists else "create", "file_path": path, "content": content})
        if not actions:
            raise GitLabError("Nothing to commit.")
        return self._req("POST", "/repository/commits", {
            "branch": branch, "start_branch": start_branch, "commit_message": message, "actions": actions})

    def open_merge_request(self, source: str, target: str, title: str, description: str, labels: list[str]) -> dict:
        mr = self._req("POST", "/merge_requests", {
            "source_branch": source, "target_branch": target, "title": title, "description": description,
            "remove_source_branch": True, "squash": True, "labels": ",".join(labels)})
        return {"iid": mr["iid"], "web_url": mr.get("web_url"), "state": mr.get("state")}

    def merge(self, iid: int) -> dict:
        mr = self._req("PUT", f"/merge_requests/{int(iid)}/merge", {"should_remove_source_branch": True, "squash": True})
        return {"iid": mr.get("iid"), "state": mr.get("state"), "web_url": mr.get("web_url")}
