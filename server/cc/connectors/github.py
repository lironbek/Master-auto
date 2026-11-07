"""GitHub connector: repositories, pull requests, Actions runs (read-only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .base import AssetRecord, ConnectorError, EventRecord, SyncResult, classify_http_error, make_client

API = "https://api.github.com"


class GitHubConnector:
    provider = "github"

    def __init__(self, token: str, *, repos: list[str] | None = None, org: str = ""):
        self.token = token
        self.repos = [r.strip() for r in (repos or []) if r.strip()]   # explicit "owner/name" allowlist
        self.org = org.strip()

    def _client(self):
        return make_client({"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2022-11-28"})

    def verify(self) -> dict[str, Any]:
        with self._client() as c:
            r = c.get(f"{API}/user")
            if r.status_code >= 400:
                raise classify_http_error(r)
            me = r.json()
            scopes = r.headers.get("x-oauth-scopes", "")
            return {"account": me.get("login", ""), "scopes": scopes, "capabilities": ["inventory", "pull_requests", "actions"]}

    def _list_repos(self, c) -> list[dict]:
        if self.repos:
            out = []
            for full in self.repos:
                r = c.get(f"{API}/repos/{full}")
                if r.status_code == 404:
                    continue
                if r.status_code >= 400:
                    raise classify_http_error(r)
                out.append(r.json())
            return out
        url = f"{API}/orgs/{self.org}/repos?per_page=100&sort=pushed" if self.org else f"{API}/user/repos?per_page=100&sort=pushed&affiliation=owner,collaborator,organization_member"
        r = c.get(url)
        if r.status_code >= 400:
            raise classify_http_error(r)
        return r.json()

    def sync(self, *, since: Optional[datetime] = None) -> SyncResult:
        res = SyncResult(coverage={"inventory": "full", "pull_requests": "full", "actions": "full"})
        with self._client() as c:
            for repo in self._list_repos(c):
                full = repo["full_name"]
                res.assets.append(AssetRecord(
                    external_id=str(repo["id"]), kind="repo", name=full, environment="development",
                    state="archived" if repo.get("archived") else ("private" if repo.get("private") else "public"),
                    url=repo.get("html_url", ""), description=(repo.get("description") or "")[:300],
                    source_updated_at=repo.get("pushed_at"),
                    meta={"default_branch": repo.get("default_branch", ""), "language": repo.get("language") or ""},
                ))
                # Pull requests (latest 10)
                r = c.get(f"{API}/repos/{full}/pulls?state=all&per_page=10&sort=updated&direction=desc")
                if r.status_code == 403:
                    res.coverage["pull_requests"] = "blocked"; res.partial = True
                elif r.status_code < 400:
                    for pr in r.json():
                        result = "success" if pr.get("merged_at") else ("cancelled" if pr.get("state") == "closed" else "running")
                        res.events.append(EventRecord(
                            external_id=f"pr:{pr['id']}", asset_external_id=str(repo["id"]), kind="pull_request",
                            result=result, occurred_at=pr.get("updated_at") or pr.get("created_at"),
                            title=f"PR #{pr['number']} {pr.get('title', '')[:120]}", environment="development",
                            url=pr.get("html_url", ""), meta={"number": pr["number"], "branch": pr.get("head", {}).get("ref", ""), "state": pr.get("state")},
                        ))
                # Actions runs (latest 10)
                r = c.get(f"{API}/repos/{full}/actions/runs?per_page=10")
                if r.status_code == 403:
                    res.coverage["actions"] = "blocked"; res.partial = True
                elif r.status_code < 400:
                    for run in r.json().get("workflow_runs", []):
                        concl = run.get("conclusion")
                        result = {"success": "success", "failure": "failure", "cancelled": "cancelled"}.get(concl or "", "running" if run.get("status") in ("in_progress", "queued") else "unknown")
                        res.events.append(EventRecord(
                            external_id=f"run:{run['id']}:{run.get('run_attempt', 1)}", asset_external_id=str(repo["id"]),
                            kind="workflow_run", result=result, occurred_at=run.get("updated_at") or run.get("created_at"),
                            title=f"{run.get('name', 'workflow')} · {run.get('head_branch', '')}", environment="development",
                            url=run.get("html_url", ""), meta={"branch": run.get("head_branch", ""), "sha": (run.get("head_sha") or "")[:12], "event": run.get("event", "")},
                        ))
        return res
