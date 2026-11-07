"""Run lifecycle & stop control — PRD sections 7, 18.

The orchestrator binds a run to an approved scope version, tracks the budget,
and provides a stop that cuts network egress independent of model availability
(PRD section 18 and acceptance criterion 7). Resuming a run requires
re-validating the contract, budget and accounts (section 18).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from ..models import (
    Authorization,
    OperatingMode,
    RunStatus,
    ScanRun,
    ScopeVersion,
    ScopeVersionStatus,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RunError(RuntimeError):
    pass


class Orchestrator:
    """Owns run state transitions. The actual network egress happens through a
    separate egress callback so ``stop`` can sever it immediately."""

    def __init__(self, *, egress_shutdown: Optional[Callable[[], None]] = None):
        self._egress_shutdown = egress_shutdown
        self._stopped = False

    def open_run(
        self,
        scope: ScopeVersion,
        authorization: Authorization,
        mode: OperatingMode,
        *,
        now: Optional[datetime] = None,
    ) -> ScanRun:
        now = now or _now()
        if scope.status is not ScopeVersionStatus.APPROVED:
            raise RunError("scope version is not approved")
        if not authorization.is_valid_at(now):
            raise RunError("authorization is not valid for this time")
        if mode not in scope.allowed_modes:
            raise RunError(f"mode {mode.value} not permitted by scope")
        if scope.run_window_start and now < scope.run_window_start:
            raise RunError("run window has not opened")
        if scope.run_window_end and now > scope.run_window_end:
            raise RunError("run window has closed")

        run = ScanRun(
            organization_id=scope.organization_id,
            project_id=scope.project_id,
            scope_version_id=scope.id,
            mode=mode,
            status=RunStatus.RUNNING,
            started_at=now,
        )
        self._stopped = False
        return run

    def stop(self, run: ScanRun, reason: str = "operator stop") -> ScanRun:
        """Immediate stop: cut egress first, then mark state. Target product
        time of <=10s is measured in acceptance tests (PRD section 18)."""
        if self._egress_shutdown is not None:
            self._egress_shutdown()
        self._stopped = True
        run.status = RunStatus.STOPPED
        run.stopped_at = _now()
        run.stop_reason = reason
        return run

    def pause(self, run: ScanRun, reason: str = "") -> ScanRun:
        run.status = RunStatus.PAUSED
        run.stop_reason = reason
        return run

    @property
    def stopped(self) -> bool:
        return self._stopped

    def guard_authorization(
        self, run: ScanRun, authorization: Authorization, *, now: Optional[datetime] = None
    ) -> None:
        """Called before each new action — expired authorization stops the run
        with no new actions (PRD section 18)."""
        if not authorization.is_valid_at(now):
            self.stop(run, reason="authorization expired")
            raise RunError("authorization expired; run stopped")
