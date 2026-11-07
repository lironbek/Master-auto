from __future__ import annotations

import os

os.environ.setdefault("PT_ALLOW_HEADER_AUTH", "1")

from datetime import datetime, timedelta, timezone

import pytest

from pt_agent.models import (
    Authorization,
    OperatingMode,
    RunBudget,
    ScopeVersion,
    ScopeVersionStatus,
    TargetSpec,
)

ORG_A = "org_aaaa"
ORG_B = "org_bbbb"
ORG_KEY = b"test-org-hmac-key-32-bytes-long!!"


@pytest.fixture
def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def authorization(now):
    return Authorization(
        organization_id=ORG_A,
        project_id="prj_1",
        approver_name="Dana Owner",
        approver_authority="CISO",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        control_verified=True,
        document_reference="DOC-1",
    )


@pytest.fixture
def scope(now, authorization):
    return ScopeVersion(
        organization_id=ORG_A,
        project_id="prj_1",
        version=1,
        status=ScopeVersionStatus.APPROVED,
        authorization_id=authorization.id,
        targets=[
            TargetSpec(scheme="https", host="app.test.example", ports=[443], allowed_paths=["/"])
        ],
        allowed_modules=["passive.security_headers", "passive.cookie_flags"],
        allowed_modes=[OperatingMode.PASSIVE, OperatingMode.ACTIVE_CONTROLLED],
        budget=RunBudget(max_requests=5, max_duration_seconds=60),
        run_window_start=now - timedelta(hours=1),
        run_window_end=now + timedelta(hours=1),
    )
