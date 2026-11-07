"""Vercel connector: projects and deployments (read-only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .base import AssetRecord, EventRecord, SyncResult, classify_http_error, make_client

API = "https://api.vercel.com"
MAX_PAGES = 10


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

    def project_profile(self, project_id: str) -> dict[str, Any]:
        """How the Vercel project is set up: framework, root dir, env var NAMES
        (never values), domains, latest production deployment, crons."""
        out: dict[str, Any] = {"project_id": project_id}
        with self._client() as c:
            r = c.get(f"{API}/v9/projects/{project_id}", params=self._q())
            if r.status_code >= 400:
                raise classify_http_error(r)
            p = r.json()
            link = p.get("link") or {}
            out.update({"name": p.get("name"), "framework": p.get("framework") or "", "node_version": p.get("nodeVersion", ""),
                        "root_directory": p.get("rootDirectory") or "", "linked_repo": f"{link.get('org', '')}/{link.get('repo', '')}" if link.get("repo") else "",
                        "production_branch": link.get("productionBranch", ""), "crons": [cr.get("path") for cr in (p.get("crons") or {}).get("definitions", [])] if isinstance(p.get("crons"), dict) else [],
                        "protection": "vercel_auth" if (p.get("ssoProtection") or {}).get("enabled") else ("password" if (p.get("passwordProtection") or {}).get("enabled") else "none")})
            r = c.get(f"{API}/v9/projects/{project_id}/env", params=self._q())
            envs = r.json().get("envs", []) if r.status_code < 400 else []
            out["env_names"] = sorted({e.get("key", "") for e in envs if e.get("key")})
            out["env_plain_secret_like"] = sorted({e["key"] for e in envs if e.get("type") == "plain" and any(s in e.get("key", "").upper() for s in ("KEY", "SECRET", "TOKEN", "PASSWORD"))})
            r = c.get(f"{API}/v9/projects/{project_id}/domains", params=self._q())
            out["domains"] = [d.get("name") for d in r.json().get("domains", [])] if r.status_code < 400 else []
            r = c.get(f"{API}/v6/deployments", params=self._q({"projectId": project_id, "limit": 1, "target": "production"}))
            deps = r.json().get("deployments", []) if r.status_code < 400 else []
            if deps:
                d = deps[0]
                out["last_production"] = {"state": (d.get("readyState") or d.get("state") or "").upper(), "at": _ms(d.get("createdAt") or d.get("created")),
                                          "url": f"https://{d.get('url', '')}" if d.get("url") else "", "branch": (d.get("meta") or {}).get("githubCommitRef", "")}
        return out

    def project_health(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        f: list[dict[str, Any]] = []

        def add(sev, title, detail, fix=""):
            f.append({"severity": sev, "title": title, "detail": detail, "fix": fix, "source": "vercel"})

        lp = profile.get("last_production") or {}
        if lp.get("state") == "ERROR":
            add("high", "הפריסה האחרונה לייצור נכשלה", f"{lp.get('at', '')} · {lp.get('branch', '')}", "פתח את לוג הבנייה ב-Vercel ותקן לפני פריסה נוספת.")
        if not lp:
            add("info", "אין פריסת ייצור", "הפרויקט מעולם לא נפרס לייצור.")
        if profile.get("env_plain_secret_like"):
            add("medium", "סודות שמורים כ-plain ב-Vercel", ", ".join(profile["env_plain_secret_like"]), "הגדר אותם מחדש כ-Sensitive כדי שלא ייקראו מה-dashboard.")
        if not profile.get("linked_repo"):
            add("low", "הפרויקט לא מקושר לריפו", "פריסות ידניות בלבד.", "חבר את הפרויקט לריפו כדי לקבל פריסה אוטומטית ו-Preview לכל PR.")
        if profile.get("protection") == "none" and profile.get("framework") in ("", None):
            add("info", "ללא הגנת פריסה", "preview deployments פתוחים לכל מי שיש לו קישור.")
        return f

    def sync(self, *, since: Optional[datetime] = None) -> SyncResult:
        res = SyncResult(coverage={"inventory": "full", "deployments": "full"})
        with self._client() as c:
            projects: list[dict] = []
            until: Any = None
            for _ in range(MAX_PAGES):
                r = c.get(f"{API}/v9/projects", params=self._q({"limit": 100, **({"until": until} if until else {})}))
                if r.status_code >= 400:
                    raise classify_http_error(r)
                body = r.json()
                projects.extend(body.get("projects", []))
                until = (body.get("pagination") or {}).get("next")
                if not until:
                    break
            else:
                res.coverage["inventory"] = "partial"; res.partial = True
                res.notes.append(f"inventory truncated after {MAX_PAGES * 100} projects")
            for p in projects:
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
