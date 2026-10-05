from __future__ import annotations

from ai_release_contract.models import (
    Direction,
    PolicyRule,
    RuleResult,
    Severity,
    Verdict,
    Violation,
)
from ai_release_contract.verdict import determine_verdict


def _result(severity: Severity, *, critical_gate: bool = False) -> RuleResult:
    rule = PolicyRule(
        metric="metric",
        direction=Direction.HIGHER_IS_BETTER,
        severity=severity,
    )
    violation = Violation(
        metric="metric",
        severity=severity,
        reason="failure",
        candidate_value=0.0,
        baseline_value=1.0,
        is_critical_gate_violation=critical_gate,
    )
    return RuleResult(rule=rule, passed=False, violations=(violation,))


def test_empty_results_approve():
    verdict, violations = determine_verdict(())
    assert verdict == Verdict.APPROVE
    assert violations == ()


def test_info_only_approves():
    verdict, _ = determine_verdict((_result(Severity.INFO),))
    assert verdict == Verdict.APPROVE


def test_warning_only_approves():
    verdict, _ = determine_verdict((_result(Severity.WARNING),))
    assert verdict == Verdict.APPROVE


def test_high_blocks():
    verdict, _ = determine_verdict((_result(Severity.HIGH),))
    assert verdict == Verdict.BLOCK


def test_critical_blocks():
    verdict, _ = determine_verdict((_result(Severity.CRITICAL),))
    assert verdict == Verdict.BLOCK


def test_critical_gate_blocks_regardless_of_severity():
    verdict, _ = determine_verdict(
        (_result(Severity.INFO, critical_gate=True),)
    )
    assert verdict == Verdict.BLOCK
