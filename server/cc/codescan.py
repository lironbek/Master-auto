"""Code review scan: a bounded, read-only review of a repository's most
security-relevant source files by Claude, stored as a project scan.

What is sent to the model: up to MAX_FILES files (each at most MAX_FILE_BYTES,
MAX_TOTAL_BYTES in total), chosen by path heuristics (auth, api, routes, db,
webhooks, payments, config) from the repository tree. Secrets are redacted
before sending (the PT redaction layer). The model must answer in strict JSON;
anything else is recorded as a failed scan, never as findings.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from pt_agent.evidence.redaction import redact

from .service import iso

Row = dict[str, Any]

MAX_FILES = 25
MAX_FILE_BYTES = 24_000
MAX_TOTAL_BYTES = 180_000
SKIP_DIRS = ("node_modules/", "dist/", "build/", ".next/", "vendor/", "coverage/", "public/", "assets/", ".git/", "__pycache__/", "migrations/")
SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".pdf", ".lock", ".map", ".min.js", ".snap", ".csv", ".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".css", ".scss")
SOURCE_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".go", ".rb", ".php", ".java", ".kt", ".rs", ".sql", ".prisma")
PRIORITY = (("auth", 50), ("login", 50), ("session", 40), ("middleware", 40), ("api/", 35), ("routes", 35), ("router", 35), ("server", 30), ("webhook", 45),
            ("payment", 45), ("stripe", 45), ("whatsapp", 40), ("green", 30), ("supabase", 30), ("db", 25), ("prisma", 25), ("models", 20), ("schema", 20),
            ("config", 20), ("env", 20), ("upload", 30), ("admin", 35), ("cron", 25), ("main.", 25), ("app.", 25), ("index.", 15))

SYSTEM = (
    "אתה סוקר קוד בכיר. אתה מקבל קבצי מקור נבחרים מריפוזיטורי (סודות הושחרו). "
    "מצא בעיות אמיתיות בלבד: אבטחה (הזרקות, הרשאות חסרות, סודות בקוד, SSRF, קלט לא מאומת, CORS פתוח, webhooks ללא אימות), "
    "נכונות (באגים ברורים, טיפול בשגיאות חסר, race), ותחזוקה רק אם היא משמעותית. "
    "לכל ממצא: severity (high|medium|low|info), title (עברית, קצר), detail (מה ובאיזה קובץ/שורה), fix (מה לעשות), file, line (מספר או null). "
    "ענה אך ורק ב-JSON תקין בצורה: {\"summary\": \"...\", \"findings\": [...]} בלי טקסט נוסף. אל תמציא קבצים שלא קיבלת."
)


def _score(path: str) -> int:
    low = path.lower()
    s = sum(w for key, w in PRIORITY if key in low)
    depth = low.count("/")
    return s - depth


def select_files(paths_with_size: list[tuple[str, int]]) -> list[str]:
    cands = []
    for p, size in paths_with_size:
        low = p.lower()
        if any(d in f"/{low}" for d in SKIP_DIRS) or low.endswith(SKIP_EXT) or not low.endswith(SOURCE_EXT):
            continue
        if size <= 0 or size > MAX_FILE_BYTES:
            continue
        cands.append((p, size))
    cands.sort(key=lambda ps: -_score(ps[0]))
    out, total = [], 0
    for p, size in cands:
        if len(out) >= MAX_FILES or total + size > MAX_TOTAL_BYTES:
            break
        out.append(p); total += size
    return out


def gather(connector, full_name: str) -> tuple[str, list[dict[str, Any]]]:
    """Return (default_branch, [{path, content}]) for the selected files."""
    branch, files = connector.list_files(full_name)
    chosen = select_files(files)
    out = []
    for p in chosen:
        text = connector.read_file(full_name, p, branch)
        if text:
            out.append({"path": p, "content": redact(text).text})
    return branch, out


def review_with_claude(api_key: str, model: str, full_name: str, files: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, int]]:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    body = "\n\n".join(f"===== {f['path']} =====\n{f['content']}" for f in files)
    resp = client.messages.create(
        model=model, max_tokens=6000, system=SYSTEM,
        messages=[{"role": "user", "content": f"ריפוזיטורי: {full_name}\nקבצים ({len(files)}):\n\n{body}"}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    usage = {"input": resp.usage.input_tokens, "output": resp.usage.output_tokens}
    return parse_review(text), usage


def parse_review(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0) if m else text)
    findings = []
    for f in data.get("findings", []) or []:
        sev = str(f.get("severity", "info")).lower()
        findings.append({"severity": sev if sev in ("high", "medium", "low", "info") else "info", "title": str(f.get("title", ""))[:200],
                         "detail": str(f.get("detail", ""))[:1000], "fix": str(f.get("fix", ""))[:600], "file": str(f.get("file", ""))[:200],
                         "line": f.get("line") if isinstance(f.get("line"), int) else None, "source": "code"})
    return {"summary": str(data.get("summary", ""))[:2000], "findings": findings}


def resolve_key(store, org_id: str, project: Row) -> tuple[Optional[str], Optional[str], str]:
    """Project default key (anthropic) > ANTHROPIC_API_KEY env. Returns (key, key_id, model)."""
    from .secrets import SecretsUnavailable, decrypt

    model = os.environ.get("CC_SCAN_MODEL", "claude-sonnet-5-5")
    if project.get("default_key_id"):
        k = store.get("provider_keys", project["default_key_id"], organization_id=org_id)
        if k and k.get("provider") == "anthropic" and k.get("secret_enc"):
            try:
                return decrypt(k["secret_enc"]), k["id"], model
            except SecretsUnavailable:
                pass
    env = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return (env or None), None, model
