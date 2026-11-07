"""Agent center (PRD section 9.4) — read-only agents, manual runs.

An agent is a saved, versioned configuration. A run binds it to one allowed
project, checks permissions and budget, gathers read-only context from the
catalog, and produces an artifact (a status summary). If an Anthropic key is
configured for the agent (or ``ANTHROPIC_API_KEY`` is set) the summary is
written by Claude through the official SDK; otherwise a deterministic summary
is produced so the flow works without a provider key. Usage and an estimated
cost are recorded as a cost entry linked to the project and the key.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .secrets import SecretsUnavailable, decrypt
from .service import iso, new_id, now

Row = dict[str, Any]

# USD per 1M tokens for estimates (PRD 9.3 "אומדן"); kept with the version date.
PRICING = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}
PRICING_VERSION = "2026-10-06"


class AgentRunError(RuntimeError):
    pass


def gather_context(store, org_id: str, project: Row) -> dict[str, Any]:
    ws = project["workspace_id"]
    links = store.list("project_assets", organization_id=org_id, project_id=project["id"])
    assets = [a for a in (store.get("cc_assets", l["asset_id"], organization_id=org_id) for l in links) if a]
    events = store.list("activity_events", organization_id=org_id, workspace_id=ws, project_id=project["id"])[-25:]
    sessions = store.list("work_sessions", organization_id=org_id, workspace_id=ws, project_id=project["id"])
    costs = store.list("cost_entries", organization_id=org_id, workspace_id=ws, project_id=project["id"])
    alerts = [a for a in store.list("alerts", organization_id=org_id, workspace_id=ws, status="open")
              if a.get("target_id") in {x["id"] for x in assets}]
    return {
        "project": {k: project.get(k) for k in ("id", "name", "owner", "importance", "status", "environment", "description")},
        "assets": [{k: a.get(k) for k in ("name", "kind", "provider", "environment", "state", "url")} for a in assets],
        "events": [{k: e.get(k) for k in ("kind", "result", "environment", "title", "occurred_at", "url")} for e in events],
        "sessions": [{k: s.get(k) for k in ("title", "status", "tool", "owner")} for s in sessions if s["status"] in ("open", "waiting")],
        "costs_total_usd": round(sum(float(c.get("amount") or 0) for c in costs), 2),
        "alerts": [a.get("message") for a in alerts],
        "architecture": (project.get("profile_summary") or {}).get("text", ""),
        "last_scan": {"grade": project.get("last_scan_grade"), "at": project.get("last_scan_at")} if project.get("last_scan_grade") else None,
    }


def deterministic_summary(ctx: dict[str, Any]) -> str:
    p = ctx["project"]
    fails = [e for e in ctx["events"] if e["result"] == "failure"]
    prod_fail = [e for e in fails if e["environment"] == "production"]
    lines = [f"סיכום מצב — {p['name']}"]
    lines.append(f"נכסים משויכים: {len(ctx['assets'])} · אירועים אחרונים: {len(ctx['events'])} · סשנים פתוחים: {len(ctx['sessions'])}")
    if prod_fail:
        lines.append(f"חריגה: {len(prod_fail)} כשלים בייצור. אחרון: {prod_fail[-1]['title']} ({prod_fail[-1]['occurred_at']})")
    elif fails:
        lines.append(f"{len(fails)} כשלים בסביבות שאינן ייצור; הייצור ללא כשל מדווח.")
    else:
        lines.append("לא נרשמו כשלים באירועים שנקלטו.")
    if ctx["alerts"]:
        lines.append("התראות פתוחות: " + "; ".join(ctx["alerts"][:5]))
    lines.append(f"עלות משויכת (כולל אומדנים): ${ctx['costs_total_usd']}")
    by_kind: dict[str, int] = {}
    for a in ctx["assets"]:
        by_kind[a["kind"]] = by_kind.get(a["kind"], 0) + 1
    if by_kind:
        lines.append("הרכב: " + ", ".join(f"{k} {v}" for k, v in by_kind.items()))
    lines.append("מקור: קטלוג ואירועים שנקלטו במרכז הבקרה. סיכום דטרמיניסטי ללא מודל.")
    return "\n".join(lines)


def _resolve_key(store, org_id: str, agent: Row) -> tuple[Optional[str], Optional[str]]:
    """Return (api_key, key_id). Agent key > workspace default > env."""
    if agent.get("key_id"):
        k = store.get("provider_keys", agent["key_id"], organization_id=org_id)
        if k and k.get("workspace_id") == agent["workspace_id"] and k.get("provider") == "anthropic":
            try:
                return decrypt(k.get("secret_enc", "")), k["id"]
            except SecretsUnavailable:
                return None, None
    env = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return (env or None), None


def claude_summary(api_key: str, model: str, instructions: str, ctx: dict[str, Any]) -> tuple[str, dict[str, int]]:
    import json

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    system = (
        "אתה סוכן קריאה-בלבד במרכז בקרה לפרויקטים. אתה מקבל מטא-דאטה בלבד (שמות, סטטוסים, זמנים, קישורים). "
        "כתוב סיכום מצב קצר בעברית: מה קיים, מה נכשל, מה דורש תשומת לב, ומה הצעד הבא. "
        "אל תמציא נתונים שאינם בקלט. אל תציע פעולות שמשנות מערכות חיצוניות.\n\nהוראות המפעיל:\n" + (instructions or "")
    )
    resp = client.messages.create(
        model=model, max_tokens=4000, system=system,
        messages=[{"role": "user", "content": "נתוני הפרויקט (JSON):\n" + json.dumps(ctx, ensure_ascii=False)[:60000]}],
    )
    if resp.stop_reason == "refusal":
        raise AgentRunError("the model declined the request")
    text = "".join(b.text for b in resp.content if b.type == "text")
    usage = {"input": resp.usage.input_tokens, "output": resp.usage.output_tokens}
    return text, usage


def estimate_cost(model: str, usage: dict[str, int]) -> float:
    pin, pout = PRICING.get(model, PRICING["claude-opus-5-5"])
    return round(usage.get("input", 0) / 1e6 * pin + usage.get("output", 0) / 1e6 * pout, 6)


def execute_run(store, org_id: str, run: Row, agent: Row, project: Row, *, actor: str) -> Row:
    """Execute a queued run synchronously; returns the final run row."""
    store.update("agent_runs", run["id"], organization_id=org_id, patch={"status": "running", "started_at": iso()})
    steps: list[dict[str, Any]] = []
    try:
        if not agent.get("enabled", True):
            raise AgentRunError("agent is disabled")
        allowed = agent.get("allowed_projects") or []
        if agent.get("project_id") and agent["project_id"] != project["id"]:
            raise AgentRunError("dedicated agent cannot run on another project")
        if not agent.get("project_id") and allowed and project["id"] not in allowed:
            raise AgentRunError("project not in the agent's allowed list")

        steps.append({"tool": "catalog.read", "at": iso(), "note": "gathered assets, events, sessions, costs, alerts"})
        ctx = gather_context(store, org_id, project)

        api_key, key_id = _resolve_key(store, org_id, agent)
        model = agent.get("model") or "claude-opus-5-5"
        usage = {"input": 0, "output": 0}
        if api_key:
            steps.append({"tool": "model.summarize", "at": iso(), "note": f"{agent.get('provider', 'anthropic')}/{model}"})
            text, usage = claude_summary(api_key, model, agent.get("instructions", ""), ctx)
        else:
            steps.append({"tool": "summary.deterministic", "at": iso(), "note": "no provider key configured"})
            text = deterministic_summary(ctx)

        cost = estimate_cost(model, usage) if usage["input"] or usage["output"] else 0.0
        if usage["input"] or usage["output"]:
            # Metered usage per client (PRD 9.3): one entry per metric, de-duplicated by run.
            from .usage import UsageEntryIn, record
            for metric, qty in (("requests", 1), ("tokens_in", usage["input"]), ("tokens_out", usage["output"])):
                record(store, org_id, project["workspace_id"],
                       UsageEntryIn(provider=agent.get("provider", "anthropic").replace("anthropic", "claude"), metric=metric, quantity=qty,
                                    interface=f"agent:{agent['name']}", project_id=project["id"], model=model,
                                    external_id=f"run:{run['id']}:{metric}", meta={"run_id": run["id"], "key_id": key_id}),
                       client_id=project.get("client_id"), source="agent")
        if cost:
            store.insert("cost_entries", {
                "id": new_id("cost"), "organization_id": org_id, "workspace_id": project["workspace_id"],
                "project_id": project["id"], "provider": agent.get("provider", "anthropic"), "kind": "estimate",
                "amount": cost, "currency": "USD", "period_start": now().date().isoformat(), "period_end": now().date().isoformat(),
                "created_at": iso(), "tokens_in": usage["input"], "tokens_out": usage["output"], "model": model,
                "key_id": key_id, "run_id": run["id"], "pricing_version": PRICING_VERSION, "note": f"ריצת סוכן {agent['name']}",
            })
        final = store.update("agent_runs", run["id"], organization_id=org_id, patch={
            "status": "completed", "finished_at": iso(), "steps": steps, "result": text, "usage": usage,
            "cost_usd": cost, "key_id": key_id, "model": model, "config_version": agent.get("version", 1),
        })
        return final
    except AgentRunError as exc:
        return store.update("agent_runs", run["id"], organization_id=org_id, patch={
            "status": "failed", "finished_at": iso(), "steps": steps, "error": str(exc)})
    except Exception as exc:  # provider/network
        return store.update("agent_runs", run["id"], organization_id=org_id, patch={
            "status": "failed", "finished_at": iso(), "steps": steps, "error": f"{type(exc).__name__}: {exc}"[:300]})
