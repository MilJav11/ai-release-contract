"""
Data models for AI Release Contract.

All models are frozen dataclasses to enforce immutability and support
equality comparison needed by the determinism properties.
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Direction(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    WARNING = "warning"
    INFO = "info"


class Verdict(str, Enum):
    APPROVE = "APPROVE"
    BLOCK = "BLOCK"


# Severities that cause a BLOCK verdict when violated.
BLOCKING_SEVERITIES: frozenset[Severity] = frozenset({Severity.CRITICAL, Severity.HIGH})


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyRule:
    """A single declarative rule in the release policy."""

    metric: str
    direction: Direction
    severity: Severity
    is_critical_gate: bool = False
    min_value: float | None = None      # only valid for higher_is_better
    max_value: float | None = None      # only valid for lower_is_better
    max_regression_pct: float | None = None


@dataclass(frozen=True)
class EvalInput:
    """Immutable snapshot of a loaded baseline or candidate evaluation file."""

    model: str
    run_id: str
    # Declared as dict in the signature so callers can pass a plain dict;
    # __post_init__ immediately wraps it in MappingProxyType.
    metrics: dict[str, float]

    def __post_init__(self) -> None:
        # The dataclass is frozen, so we must use object.__setattr__ to
        # replace the mutable dict with an immutable MappingProxyType.
        object.__setattr__(self, "metrics", types.MappingProxyType(self.metrics))


@dataclass(frozen=True)
class Violation:
    """A record produced when a candidate metric fails a policy rule condition."""

    metric: str
    severity: Severity
    reason: str
    # None when the metric is absent from the candidate (critical gate case).
    candidate_value: float | None
    baseline_value: float | None = None
    threshold: float | None = None
    is_critical_gate_violation: bool = False


@dataclass(frozen=True)
class RuleResult:
    """Intermediate record produced for every rule, whether it passes or fails."""

    rule: PolicyRule
    passed: bool
    # Empty tuple () when the rule passes; one or more Violations when it fails.
    violations: tuple[Violation, ...]


@dataclass(frozen=True)
class Report:
    """Top-level output structure holding the verdict and all evaluation details."""

    verdict: Verdict
    exit_code: int                      # 0 for APPROVE, 1 for BLOCK
    baseline: EvalInput
    candidate: EvalInput
    violations: tuple[Violation, ...]
    rule_results: tuple[RuleResult, ...]  # all rules in policy declaration order
