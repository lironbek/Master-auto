"""Control Center server: one FastAPI app, one database, two modules.

- ``/auth/*``  shared authentication and roles (pt_agent.api.auth)
- ``/cc/*``    control center (workspaces, projects, connections, catalog, sessions, inbox, costs, agents)
- ``/pt/*``    authorized security surveys (the PT governance module, mounted as a sub-app)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from billing.routes import router as billing_router
from cc.routes import router as cc_router
from pt_agent.api.app import _auto_migrate, _migration_state
from pt_agent.api.app import app as pt_app
from pt_agent.api.auth import router as auth_router
from pt_agent.storage import backend_name


@asynccontextmanager
async def _lifespan(_: FastAPI):
    _auto_migrate()
    yield


app = FastAPI(title="Control Center", version="0.3.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("PT_CORS_ORIGINS", "http://localhost:5173").split(",") if o],
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(cc_router)
app.include_router(billing_router)
app.mount("/pt", pt_app)


@app.get("/healthz")
def healthz():
    out = {"status": "ok", "storage": backend_name(), "version": app.version,
           "modules": ["auth", "cc", "billing", "pt"], "secrets": bool(os.environ.get("CC_SECRET_KEY"))}
    if backend_name() == "postgres":
        out["migrations"] = _migration_state
        if _migration_state["error"]:
            out["status"] = "degraded"
    return out
