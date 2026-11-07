"""Run budget tracking — PRD section 5.

The first limit reached stops the run (PRD section 5). The orchestrator calls
``charge`` before each request and ``exceeded`` to decide whether to stop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..models import RunBudget


@dataclass
class BudgetState:
    budget: RunBudget
    started_at: float = field(default_factory=time.monotonic)
    requests_made: int = 0
    bytes_received: int = 0
    model_cost_usd: float = 0.0

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def reason_exceeded(self, *, now: float | None = None) -> str | None:
        elapsed = (now - self.started_at) if now is not None else self.elapsed_seconds()
        if elapsed >= self.budget.max_duration_seconds:
            return "duration budget reached"
        if self.requests_made >= self.budget.max_requests:
            return "request budget reached"
        if self.bytes_received >= self.budget.max_response_bytes * self.budget.max_requests:
            return "response volume budget reached"
        if self.model_cost_usd >= self.budget.max_model_cost_usd:
            return "model cost budget reached"
        return None

    def exceeded(self, *, now: float | None = None) -> bool:
        return self.reason_exceeded(now=now) is not None

    def charge_request(self, *, response_bytes: int = 0, model_cost_usd: float = 0.0) -> None:
        self.requests_made += 1
        self.bytes_received += response_bytes
        self.model_cost_usd += model_cost_usd
