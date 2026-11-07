"""Vercel connector: projects and deployments (read-only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .base import AssetRecord, EventRecord, SyncResult, classify_http_error, make_client

API = "https://api.vercel.com"


def _ms(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


class VercelConnector:
    provider = "vercel"

    def __init__(self, token: str, *, team_id: str = ""):
        self.token = token
        self.team_id = team_id.strip()

    def _client(self):
        return make_client({"Authorization": f"Bearer {self.token}"})

    def _q(self, extra: dict | None = None) -> dict:
        q = dict(extra or {})
        if self.team_id:
            q["teamId"] = self.team_id
        return q

    def verify(self) -> dict[str, Any]:
        with self._client() as c:
            r = c.get(f"{API}/v2/user")
            if r.status_code >= 400:
                raise classify_http_error(r)
            u = r.json().get("user", {})
            return {"account": u.get("username", ""), "capabilities": ["inventory", "deployments"]}

    def sync(self, *, since: Optional[datetime] = None) -> SyncResult:
        res = SyncResult(coverage={"inventory": "full", "deployments": "full"})
        with self._client() as c:
            r = c.get(f"{API}/v9/projects", params=self._q({"limit": 100}))
            if r.status_code >= 400:
                raise classify_http_error(r)
            for p in r.json().get("projects", []):
                link = p.get("link") or {}
                repo = f"{link.get('org', '')}/{link.get('repo', '')}" if link.get("repo") else ""
                res.assets.append(AssetRecord(
                    external_id=p["id"], kind="vercel_project", name=p.get("name", p["id"]), environment="production",
                    state=p.get("framework") or "project", url=f"https://vercel.com/{p.get('accountId', '')}/{p.get('name', '')}",
                    source_updated_at=_ms(p.get("updatedAt")) if p.get("updatedAt") else None,
                    meta={"framework": p.get("framework") or "", "linked_repo": repo, "repo_id": str(link.get("repoId", "") or "")},
                ))
                d = c.get(f"{API}/v6/deployments", params=self._q({"projectId": p["id"], "limit": 10}))
                if d.status_code >= 400:
                    res.coverage["deployments"] = "partial"; res.partial = True
                    continue
                for dep in d.json().get("deployments", []):
                    state = (dep.get("readyState") or dep.get("state") or "").upper()
                    result = {"READY": "success", "ERROR": "failure", "CANCELED": "cancelled"}.get(state, "running" if state in ("BUILDING", "INITIALIZING", "QUEUED") else "unknown")
                    env = "production" if dep.get("target") == "production" else "preview"
                    meta = dep.get("meta") or {}
                    res.events.append(EventRecord(
                        external_id=f"dpl:{dep.get('uid') or dep.get('id')}", asset_external_id=p["id"], kind="deployment",
                        result=result, occurred_at=_ms(dep.get("createdAt") or dep.get("created")),
                        title=f"{'Production' if env == 'production' else 'Preview'} · {meta.get('githubCommitRef', '')}".strip(" ·"),
                        environment=env, url=f"https://{dep.get('url', '')}" if dep.get("url") else "",
                        meta={"sha": (meta.get("githubCommitSha") or "")[:12], "branch": meta.get("githubCommitRef", ""), "state": state},
                    ))
        return res
