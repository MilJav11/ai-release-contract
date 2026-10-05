"""
Comparison engine for AI Release Contract.

evaluate() is a pure function — no side effects, no I/O, fully deterministic.
It compares a candidate EvalInput against a baseline EvalInput using a sequence
of PolicyRules and returns a tuple of RuleResult records in declaration order.
"""

from __future__ import annotations

from ai_release_contract.exceptions import InputError
from ai_release_contract.models import Direction, EvalInput, PolicyRule, RuleResult, Violation


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate(
    baseline: EvalInput,
    candidate: EvalInput,
    rules: tuple[PolicyRule, ...],
) -> tuple[RuleResult, ...]:
    """Evaluate *candidate* against *baseline* using *rules*.

    Args:
        baseline: The reference EvalInput whose metrics set the performance
                  floor.
        candidate: The EvalInput being assessed for release.
        rules: Policy rules in declaration order.

    Returns:
        A tuple of :class:`RuleResult` objects, one per rule, in declaration
        order.

    Raises:
        InputError: If any rule references a metric that is absent from the
                    baseline (exit_code=2).
    """
    # Step 1 — Baseline availability check
    for rule in rules:
        if rule.metric not in baseline.metrics:
            raise InputError(
                f"Policy rule '{rule.metric}' references metric not present in baseline. "
                f"Baseline metrics: {list(baseline.metrics.keys())}",
                exit_code=2,
            )

    # Step 2 — Rule evaluation loop (in declaration order)
    results: list[RuleResult] = []
    for rule in rules:
        result = _evaluate_rule(rule, baseline, candidate)
        results.append(result)

    return tuple(results)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _evaluate_rule(
    rule: PolicyRule,
    baseline: EvalInput,
    candidate: EvalInput,
) -> RuleResult:
    """Evaluate a single *rule* for the given *baseline* and *candidate*.

    Assumes ``rule.metric`` is present in ``baseline.metrics`` (Step 1 of
    :func:`evaluate` guarantees this).
    """
    baseline_value = baseline.metrics[rule.metric]  # always exists (Step 1 passed)

    # Critical gate check — takes priority over value comparisons.
    if rule.is_critical_gate and rule.metric not in candidate.metrics:
        violation = Violation(
            metric=rule.metric,
            severity=rule.severity,
            reason="required critical metric absent from candidate",
            candidate_value=None,
            baseline_value=baseline_value,
            threshold=None,
            is_critical_gate_violation=True,
        )
        return RuleResult(rule=rule, passed=False, violations=(violation,))

    # Metric absent from candidate but NOT a critical gate → pass (no violation).
    if rule.metric not in candidate.metrics:
        return RuleResult(rule=rule, passed=True, violations=())

    candidate_value = candidate.metrics[rule.metric]
    violations_for_rule: list[Violation] = []

    if rule.direction == Direction.HIGHER_IS_BETTER:
        # Absolute threshold check
        if rule.min_value is not None and candidate_value < rule.min_value:
            violations_for_rule.append(
                Violation(
                    metric=rule.metric,
                    severity=rule.severity,
                    reason=f"candidate {candidate_value} < min_value {rule.min_value}",
                    candidate_value=candidate_value,
                    baseline_value=baseline_value,
                    threshold=rule.min_value,
                )
            )
        # Regression check
        if rule.max_regression_pct is not None:
            floor = baseline_value * (1.0 - rule.max_regression_pct / 100.0)
            if candidate_value < floor:
                violations_for_rule.append(
                    Violation(
                        metric=rule.metric,
                        severity=rule.severity,
                        reason=(
                            f"candidate {candidate_value} < regression floor "
                            f"{floor:.6g} (baseline {baseline_value} "
                            f"- {rule.max_regression_pct}%)"
                        ),
                        candidate_value=candidate_value,
                        baseline_value=baseline_value,
                        threshold=floor,
                    )
                )

    else:  # LOWER_IS_BETTER
        # Absolute threshold check
        if rule.max_value is not None and candidate_value > rule.max_value:
            violations_for_rule.append(
                Violation(
                    metric=rule.metric,
                    severity=rule.severity,
                    reason=f"candidate {candidate_value} > max_value {rule.max_value}",
                    candidate_value=candidate_value,
                    baseline_value=baseline_value,
                    threshold=rule.max_value,
                )
            )
        # Regression check
        if rule.max_regression_pct is not None:
            ceiling = baseline_value * (1.0 + rule.max_regression_pct / 100.0)
            if candidate_value > ceiling:
                violations_for_rule.append(
                    Violation(
                        metric=rule.metric,
                        severity=rule.severity,
                        reason=(
                            f"candidate {candidate_value} > regression ceiling "
                            f"{ceiling:.6g} (baseline {baseline_value} "
                            f"+ {rule.max_regression_pct}%)"
                        ),
                        candidate_value=candidate_value,
                        baseline_value=baseline_value,
                        threshold=ceiling,
                    )
                )

    # A rule may produce 0, 1, or 2 violations (threshold + regression both fail).
    if violations_for_rule:
        return RuleResult(rule=rule, passed=False, violations=tuple(violations_for_rule))
    return RuleResult(rule=rule, passed=True, violations=())
