"""GitHub connector: repositories, pull requests, Actions runs (read-only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .base import AssetRecord, ConnectorError, EventRecord, SyncResult, classify_http_error, make_client

API = "https://api.github.com"
MAX_PAGES = 10   # 1,000 repositories per connection; beyond that the sync is marked partial

# Dependency name -> integration label (what the project talks to).
INTEGRATION_HINTS = {
    "@anthropic-ai/sdk": "Claude", "anthropic": "Claude", "@google/generative-ai": "Gemini", "@google/genai": "Gemini", "google-generativeai": "Gemini",
    "google-genai": "Gemini", "openai": "OpenAI", "groq-sdk": "Groq", "groq": "Groq", "@supabase/supabase-js": "Supabase", "supabase": "Supabase",
    "@supabase/ssr": "Supabase", "stripe": "Stripe", "resend": "Resend", "nodemailer": "SMTP", "twilio": "Twilio", "@google-cloud/vision": "Google Vision (OCR)",
    "google-cloud-vision": "Google Vision (OCR)", "tesseract.js": "Tesseract (OCR)", "pytesseract": "Tesseract (OCR)", "prisma": "Prisma", "@prisma/client": "Prisma",
    "drizzle-orm": "Drizzle", "sqlalchemy": "SQLAlchemy", "psycopg": "Postgres", "psycopg2-binary": "Postgres", "pg": "Postgres", "@neondatabase/serverless": "Neon",
    "redis": "Redis", "ioredis": "Redis", "next-auth": "NextAuth", "@auth/core": "Auth.js", "firebase": "Firebase", "@sentry/nextjs": "Sentry", "sentry-sdk": "Sentry",
    "@vercel/analytics": "Vercel Analytics", "@vercel/blob": "Vercel Blob", "shopify-api-node": "Shopify", "@shopify/shopify-api": "Shopify", "telegraf": "Telegram",
    "python-telegram-bot": "Telegram", "whatsapp-web.js": "WhatsApp", "fastapi": "FastAPI", "django": "Django", "flask": "Flask", "next": "Next.js", "react": "React",
    "vue": "Vue", "svelte": "Svelte", "tailwindcss": "Tailwind", "playwright": "Playwright", "@playwright/test": "Playwright", "vitest": "Vitest", "jest": "Jest", "pytest": "pytest",
}


def _detect_integrations(deps: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    for d in deps:
        label = INTEGRATION_HINTS.get(d.lower())
        if label and label not in seen:
            seen.append(label)
    return seen


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

    # --- project profile & health (read-only, on demand) --------------------

    def repo_profile(self, full_name: str) -> dict[str, Any]:
        """How a repository is built: languages, framework hints, manifests,
        top-level structure, CI, tests, docs. Metadata only, no source code is
        stored beyond manifest names/versions and a README excerpt."""
        out: dict[str, Any] = {"full_name": full_name}
        with self._client() as c:
            r = c.get(f"{API}/repos/{full_name}")
            if r.status_code >= 400:
                raise classify_http_error(r)
            repo = r.json()
            out.update({"default_branch": repo.get("default_branch", ""), "visibility": "private" if repo.get("private") else "public",
                        "archived": bool(repo.get("archived")), "pushed_at": repo.get("pushed_at"), "size_kb": repo.get("size"),
                        "open_issues": repo.get("open_issues_count", 0), "license": (repo.get("license") or {}).get("spdx_id", ""),
                        "description": repo.get("description") or "", "homepage": repo.get("homepage") or ""})
            r = c.get(f"{API}/repos/{full_name}/languages")
            out["languages"] = r.json() if r.status_code < 400 else {}
            r = c.get(f"{API}/repos/{full_name}/git/trees/{out['default_branch']}", params={"recursive": "1"})
            paths: list[str] = []
            if r.status_code < 400:
                paths = [t["path"] for t in r.json().get("tree", []) if t.get("type") == "blob"]
                out["truncated_tree"] = bool(r.json().get("truncated"))
            out["files"] = len(paths)
            top: dict[str, int] = {}
            for p in paths:
                top[p.split("/")[0]] = top.get(p.split("/")[0], 0) + 1
            out["top_level"] = dict(sorted(top.items(), key=lambda kv: -kv[1])[:30])
            names = set(paths)
            out["manifests"] = [m for m in ("package.json", "pyproject.toml", "requirements.txt", "Dockerfile", "vercel.json", "docker-compose.yml",
                                            "prisma/schema.prisma", "supabase/config.toml", "go.mod", "Cargo.toml", "next.config.js", "next.config.ts",
                                            "vite.config.ts", "vite.config.js", "tsconfig.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "poetry.lock")
                                if m in names]
            out["workflows"] = [p.split("/")[-1] for p in paths if p.startswith(".github/workflows/")]
            out["has_tests"] = any(("/tests/" in f"/{p}" or "/test/" in f"/{p}" or "__tests__" in p or p.endswith((".test.ts", ".test.tsx", ".spec.ts", "_test.py", ".test.js")) or p.startswith("tests/")) for p in paths)
            out["has_readme"] = any(p.lower() in ("readme.md", "readme") for p in paths)
            out["env_files_committed"] = [p for p in paths if p.split("/")[-1] in (".env", ".env.local", ".env.production")]
            out["migrations"] = sum(1 for p in paths if "/migrations/" in f"/{p}" and p.endswith(".sql"))
            out["dependencies"], out["scripts"], out["framework"], out["runtime"] = {}, {}, "", ""
            if "package.json" in names:
                pj = self._json_file(c, full_name, "package.json", out["default_branch"])
                deps = {**(pj.get("dependencies") or {}), **(pj.get("devDependencies") or {})}
                out["dependencies"] = dict(list(deps.items())[:80])
                out["scripts"] = {k: v[:80] for k, v in (pj.get("scripts") or {}).items()}
                out["runtime"] = "node"
                for key, fw in (("next", "Next.js"), ("nuxt", "Nuxt"), ("@remix-run/react", "Remix"), ("vite", "Vite"), ("react-native", "React Native"), ("express", "Express"), ("fastify", "Fastify"), ("nestjs", "NestJS"), ("@nestjs/core", "NestJS")):
                    if key in deps:
                        out["framework"] = fw; break
            if "requirements.txt" in names or "pyproject.toml" in names:
                out["runtime"] = (out["runtime"] + "+python") if out["runtime"] else "python"
                txt = self._text_file(c, full_name, "requirements.txt" if "requirements.txt" in names else "pyproject.toml", out["default_branch"])
                pkgs = [ln.strip().split("==")[0].split(">=")[0].split("[")[0].strip().strip('",') for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith(("#", "[", "name", "version", "description", "requires"))]
                out["dependencies"].update({p: "" for p in pkgs[:80] if p and len(p) < 60})
                low = txt.lower()
                for key, fw in (("fastapi", "FastAPI"), ("django", "Django"), ("flask", "Flask")):
                    if key in low and not out["framework"]:
                        out["framework"] = fw
            out["integrations"] = _detect_integrations(out["dependencies"])
            if out["has_readme"]:
                out["readme_excerpt"] = self._text_file(c, full_name, "README.md", out["default_branch"])[:1500]
        return out

    def repo_health(self, full_name: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
        """Health / hygiene findings for a repository, from metadata the token can
        read. Each finding: severity (high|medium|low|info), title, detail, fix."""
        f: list[dict[str, Any]] = []

        def add(sev, title, detail, fix=""):
            f.append({"severity": sev, "title": title, "detail": detail, "fix": fix, "source": "github"})

        with self._client() as c:
            br = profile.get("default_branch") or "main"
            r = c.get(f"{API}/repos/{full_name}/branches/{br}/protection")
            if r.status_code == 404:
                add("medium", "אין הגנה על ענף הייצור", f"הענף {br} מאפשר push ישיר ומחיקה.", "הפעל branch protection: PR חובה, לפחות בדיקה אחת ירוקה.")
            elif r.status_code == 403:
                add("info", "הגנת ענף: לא ניתן לבדוק", "הטוקן אינו רואה הגדרות הגנה (דורש Administration: read).")
            for path, label, perm in (("dependabot/alerts", "Dependabot", "Dependabot alerts: read"), ("secret-scanning/alerts", "סריקת סודות", "Secret scanning alerts: read"), ("code-scanning/alerts", "סריקת קוד", "Code scanning alerts: read")):
                r = c.get(f"{API}/repos/{full_name}/{path}", params={"state": "open", "per_page": 100})
                if r.status_code < 400:
                    n = len(r.json())
                    if n:
                        sev = "high" if path.startswith("secret") else ("medium" if n > 3 else "low")
                        add(sev, f"{label}: {n} התראות פתוחות", f"{n} התראות פתוחות ב-GitHub.", f"טפל בהתראות במסך Security של הריפו.")
                    else:
                        add("info", f"{label}: אין התראות פתוחות", "0 התראות.")
                elif r.status_code in (403, 404):
                    add("info", f"{label}: לא מופעל או ללא הרשאה", f"GitHub החזיר {r.status_code}; הפעל את התכונה ב-Security או תן לטוקן {perm}.")
        if profile.get("env_files_committed"):
            add("high", "קובץ .env נמצא בריפו", ", ".join(profile["env_files_committed"]), "הסר מהגיט, סובב את הסודות שבו, הוסף ל-.gitignore.")
        if not profile.get("workflows"):
            add("low", "אין CI (GitHub Actions)", "לא נמצאו workflows.", "הוסף workflow שמריץ בדיקות ו-lint על כל PR.")
        if not profile.get("has_tests"):
            add("medium", "לא נמצאו בדיקות", "אין תיקיית tests או קובצי *.test / *_test.", "הוסף בדיקות לפחות לזרימות הקריטיות.")
        if not profile.get("has_readme"):
            add("low", "אין README", "", "תאר בקצרה מה המערכת עושה ואיך מריצים.")
        if profile.get("manifests") and "package.json" in profile["manifests"] and not any(l in profile["manifests"] for l in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock")):
            add("medium", "אין lockfile", "התקנות לא דטרמיניסטיות; builds יכולים להישבר בלי שינוי קוד.", "התחייב package-lock.json / pnpm-lock.yaml.")
        if not profile.get("license"):
            add("info", "אין רישיון", "", "הוסף LICENSE אם הריפו ציבורי.")
        if profile.get("archived"):
            add("info", "הריפו מאורכב", "")
        return f

    def list_files(self, full_name: str) -> tuple[str, list[tuple[str, int]]]:
        """(default_branch, [(path, size)]) for the code-review scan."""
        with self._client() as c:
            r = c.get(f"{API}/repos/{full_name}")
            if r.status_code >= 400:
                raise classify_http_error(r)
            branch = r.json().get("default_branch", "main")
            r = c.get(f"{API}/repos/{full_name}/git/trees/{branch}", params={"recursive": "1"})
            if r.status_code >= 400:
                raise classify_http_error(r)
            return branch, [(t["path"], int(t.get("size") or 0)) for t in r.json().get("tree", []) if t.get("type") == "blob"]

    def read_file(self, full_name: str, path: str, ref: str) -> str:
        with self._client() as c:
            return self._text_file(c, full_name, path, ref)

    def _json_file(self, c, full_name: str, path: str, ref: str) -> dict:
        try:
            import json as _json
            return _json.loads(self._text_file(c, full_name, path, ref) or "{}")
        except Exception:
            return {}

    def _text_file(self, c, full_name: str, path: str, ref: str) -> str:
        r = c.get(f"{API}/repos/{full_name}/contents/{path}", params={"ref": ref}, headers={"Accept": "application/vnd.github.raw+json"})
        return r.text[:200_000] if r.status_code < 400 else ""

    # --- destructive actions (PRD: explicit capability, never part of sync) ----

    def archive_repository(self, full_name: str) -> dict[str, Any]:
        """Archive a repository (reversible from GitHub). Needs a token with
        Administration: write on the repository."""
        with self._client() as c:
            r = c.patch(f"{API}/repos/{full_name}", json={"archived": True})
            if r.status_code in (401, 403, 404):
                raise ConnectorError("the GitHub token cannot administer this repository (needs Administration: write)", status="reauth")
            if r.status_code >= 400:
                raise classify_http_error(r)
            return {"archived": bool(r.json().get("archived"))}

    def delete_repository(self, full_name: str) -> dict[str, Any]:
        """Delete a repository. Irreversible. Needs a token with the
        delete_repo scope (classic) or Administration: write (fine-grained)."""
        with self._client() as c:
            r = c.delete(f"{API}/repos/{full_name}")
            if r.status_code in (401, 403, 404):
                raise ConnectorError("the GitHub token cannot delete this repository (needs delete_repo / Administration: write)", status="reauth")
            if r.status_code >= 400:
                raise classify_http_error(r)
            return {"deleted": True}

    def _list_repos(self, c, res: SyncResult) -> list[dict]:
        if self.repos:
            out = []
            for full in self.repos:
                r = c.get(f"{API}/repos/{full}")
                if r.status_code == 404:
                    # An allow-listed repo the token cannot see is a coverage gap,
                    # not evidence that the repo disappeared.
                    res.coverage["inventory"] = "partial"; res.partial = True
                    res.notes.append(f"{full}: not visible to this token")
                    continue
                if r.status_code >= 400:
                    raise classify_http_error(r)
                out.append(r.json())
            return out
        base = f"{API}/orgs/{self.org}/repos?per_page=100&sort=pushed" if self.org else f"{API}/user/repos?per_page=100&sort=pushed&affiliation=owner,collaborator,organization_member"
        out: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            r = c.get(f"{base}&page={page}")
            if r.status_code >= 400:
                raise classify_http_error(r)
            batch = r.json()
            out.extend(batch)
            if len(batch) < 100:
                return out
        # More pages than we are willing to walk: the inventory is incomplete,
        # so the disappearance pass must not run.
        res.coverage["inventory"] = "partial"; res.partial = True
        res.notes.append(f"inventory truncated after {MAX_PAGES * 100} repositories")
        return out

    def sync(self, *, since: Optional[datetime] = None) -> SyncResult:
        res = SyncResult(coverage={"inventory": "full", "pull_requests": "full", "actions": "full"})
        with self._client() as c:
            for repo in self._list_repos(c, res):
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
