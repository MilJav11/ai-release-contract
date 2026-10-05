"""
Verdict determination for AI Release Contract.

Determines the final APPROVE/BLOCK verdict from a sequence of RuleResults.
This is a non-compensating evaluation: a single blocking violation causes
BLOCK regardless of how many other rules pass.
"""

from __future__ import annotations

from ai_release_contract.models import BLOCKING_SEVERITIES, RuleResult, Verdict, Violation


def determine_verdict(
    rule_results: tuple[RuleResult, ...],
) -> tuple[Verdict, tuple[Violation, ...]]:
    """
    Returns (verdict, all_violations_in_rule_order).

    Verdict is BLOCK if any violation is blocking; APPROVE otherwise.
    A violation is blocking when it is a critical gate violation OR its
    severity is in BLOCKING_SEVERITIES (CRITICAL or HIGH).
    Non-blocking violations (WARNING, INFO) are collected but do not
    affect the verdict — there is no scoring, weighting, or compensation.

    Args:
        rule_results: Tuple of RuleResult objects in policy declaration order.

    Returns:
        A 2-tuple of (Verdict, all violations across all rules in rule order).
    """
    all_violations: list[Violation] = []
    for result in rule_results:
        all_violations.extend(result.violations)  # violations is a tuple, never None

    is_blocked = any(
        v.is_critical_gate_violation or v.severity in BLOCKING_SEVERITIES
        for v in all_violations
    )

    verdict = Verdict.BLOCK if is_blocked else Verdict.APPROVE
    return verdict, tuple(all_violations)
