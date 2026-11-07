"""Scope and egress enforcement (PRD section 9)."""

from .target import NormalizedTarget, TargetParseError, normalize
from .validator import Decision, EgressValidator

__all__ = [
    "NormalizedTarget", "TargetParseError", "normalize",
    "Decision", "EgressValidator",
]
