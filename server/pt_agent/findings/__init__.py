"""Findings service (PRD section 12)."""

from .finding import FindingsService, InvalidTransition, dedup_key

__all__ = ["FindingsService", "InvalidTransition", "dedup_key"]
