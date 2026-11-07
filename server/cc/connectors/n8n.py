"""n8n connector: workflows and executions via the Public API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .base import AssetRecord, EventRecord, SyncResult, classify_http_error, make_client

MAX_PAGES = 10


class N8nConnector:
    provider = "n8n"

    def __init__(self, token: str, *, base_url: str):
        self.token = token
        self.base = base_url.rstrip("/")

    def _client(self):
        return make_client({"X-N8N-API-KEY": self.token})

    def verify(self) -> dict[str, Any]:
        with self._client() as c:
            r = c.get(f"{self.base}/api/v1/workflows", params={"limit": 1})
            if r.status_code >= 400:
                raise classify_http_error(r)
            return {"account": self.base, "capabilities": ["inventory", "executions"]}

    def sync(self, *, since: Optional[datetime] = None) -> SyncResult:
        res = SyncResult(coverage={"inventory": "full", "executions": "full"})
        with self._client() as c:
            workflows: list[dict] = []
            cursor = None
            for _ in range(MAX_PAGES):
                r = c.get(f"{self.base}/api/v1/workflows", params={"limit": 100, **({"cursor": cursor} if cursor else {})})
                if r.status_code >= 400:
                    raise classify_http_error(r)
                body = r.json()
                workflows.extend(body.get("data", []))
                cursor = body.get("nextCursor")
                if not cursor:
                    break
            else:
                res.coverage["inventory"] = "partial"; res.partial = True
                res.notes.append(f"inventory truncated after {MAX_PAGES * 100} workflows")
            for wf in workflows:
                res.assets.append(AssetRecord(
                    external_id=str(wf["id"]), kind="workflow", name=wf.get("name", str(wf["id"])), environment="production",
                    state="active" if wf.get("active") else "inactive", url=f"{self.base}/workflow/{wf['id']}",
                    source_updated_at=wf.get("updatedAt"),
                ))
            e = c.get(f"{self.base}/api/v1/executions", params={"limit": 50})
            if e.status_code in (401, 403):
                res.coverage["executions"] = "inventory_only"; res.partial = True
                res.notes.append("Executions scope missing on this API key; inventory only.")
            elif e.status_code < 400:
                for ex in e.json().get("data", []):
                    status = ex.get("status") or ("success" if ex.get("finished") else "unknown")
                    result = {"success": "success", "error": "failure", "crashed": "failure", "canceled": "cancelled", "running": "running", "waiting": "running"}.get(status, "unknown")
                    res.events.append(EventRecord(
                        external_id=f"exec:{ex['id']}", asset_external_id=str(ex.get("workflowId", "")), kind="execution",
                        result=result, occurred_at=ex.get("stoppedAt") or ex.get("startedAt"), title=f"Execution {ex['id']}",
                        environment="production", url=f"{self.base}/workflow/{ex.get('workflowId', '')}/executions/{ex['id']}",
                        meta={"mode": ex.get("mode", "")},
                    ))
        return res
