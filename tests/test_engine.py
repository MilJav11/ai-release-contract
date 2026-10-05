"""
Unit tests for ai_release_contract.engine.

Covers all 17 test cases specified in Task 4.6.
"""

import pytest

from ai_release_contract.engine import evaluate
from ai_release_contract.exceptions import InputError
from ai_release_contract.models import (
    Direction,
    EvalInput,
    PolicyRule,
    RuleResult,
    Severity,
    Violation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_baseline(metric: str, value: float, **extra) -> EvalInput:
    return EvalInput(model="baseline-model", run_id="run-base", metrics={metric: value, **extra})


def make_candidate(metric: str, value: float, **extra) -> EvalInput:
    return EvalInput(model="candidate-model", run_id="run-cand", metrics={metric: value, **extra})


def make_baseline_empty_candidate(metric: str, baseline_value: float) -> tuple[EvalInput, EvalInput]:
    """Baseline has the metric; candidate does NOT."""
    baseline = make_baseline(metric, baseline_value)
    candidate = EvalInput(model="candidate-model", run_id="run-cand", metrics={})
    return baseline, candidate


# ---------------------------------------------------------------------------
# 1. HIB min_value — candidate meets threshold → passes (no violations)
# ---------------------------------------------------------------------------

def test_hib_min_value_meets_threshold_passes():
    rule = PolicyRule(
        metric="accuracy",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.HIGH,
        min_value=0.80,
    )
    baseline = make_baseline("accuracy", 0.85)
    candidate = make_candidate("accuracy", 0.82)  # above 0.80

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is True
    assert isinstance(result.violations, tuple)
    assert result.violations == ()


# ---------------------------------------------------------------------------
# 2. HIB min_value — candidate below threshold → fails with 1 violation, correct reason
# ---------------------------------------------------------------------------

def test_hib_min_value_below_threshold_fails():
    rule = PolicyRule(
        metric="accuracy",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.HIGH,
        min_value=0.80,
    )
    baseline = make_baseline("accuracy", 0.85)
    candidate = make_candidate("accuracy", 0.75)  # below 0.80

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is False
    assert isinstance(result.violations, tuple)
    assert len(result.violations) == 1

    v = result.violations[0]
    assert v.candidate_value == 0.75
    assert v.baseline_value == 0.85
    assert v.threshold == 0.80
    assert "0.75" in v.reason
    assert "0.8" in v.reason or "min_value" in v.reason


# ---------------------------------------------------------------------------
# 3. HIB regression — candidate within pct → passes
# ---------------------------------------------------------------------------

def test_hib_regression_within_pct_passes():
    rule = PolicyRule(
        metric="f1",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.WARNING,
        max_regression_pct=5.0,  # floor = 0.90 * 0.95 = 0.855
    )
    baseline = make_baseline("f1", 0.90)
    candidate = make_candidate("f1", 0.86)  # above floor of 0.855

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is True
    assert result.violations == ()


# ---------------------------------------------------------------------------
# 4. HIB regression — candidate below floor → fails with 1 violation, correct reason
# ---------------------------------------------------------------------------

def test_hib_regression_below_floor_fails():
    rule = PolicyRule(
        metric="f1",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.WARNING,
        max_regression_pct=5.0,  # floor = 0.90 * 0.95 = 0.855
    )
    baseline = make_baseline("f1", 0.90)
    candidate = make_candidate("f1", 0.80)  # below floor 0.855

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is False
    assert isinstance(result.violations, tuple)
    assert len(result.violations) == 1

    v = result.violations[0]
    assert v.candidate_value == 0.80
    assert v.baseline_value == 0.90
    expected_floor = 0.90 * (1.0 - 5.0 / 100.0)
    assert abs(v.threshold - expected_floor) < 1e-9
    assert "regression" in v.reason.lower() or "floor" in v.reason.lower()


# ---------------------------------------------------------------------------
# 5. HIB dual violation — below BOTH min_value AND regression floor → 2 violations
# ---------------------------------------------------------------------------

def test_hib_dual_violation_two_violations():
    rule = PolicyRule(
        metric="precision",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.CRITICAL,
        min_value=0.85,          # candidate (0.70) < 0.85
        max_regression_pct=5.0,  # floor = 0.90 * 0.95 = 0.855; candidate (0.70) < 0.855
    )
    baseline = make_baseline("precision", 0.90)
    candidate = make_candidate("precision", 0.70)

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is False
    assert isinstance(result.violations, tuple)
    assert len(result.violations) == 2

    # Both violations should reference the same metric
    for v in result.violations:
        assert v.metric == "precision"
        assert v.candidate_value == 0.70


# ---------------------------------------------------------------------------
# 6. LIB max_value — candidate meets threshold → passes
# ---------------------------------------------------------------------------

def test_lib_max_value_meets_threshold_passes():
    rule = PolicyRule(
        metric="latency_ms",
        direction=Direction.LOWER_IS_BETTER,
        severity=Severity.HIGH,
        max_value=200.0,
    )
    baseline = make_baseline("latency_ms", 180.0)
    candidate = make_candidate("latency_ms", 195.0)  # at/below 200

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is True
    assert result.violations == ()


# ---------------------------------------------------------------------------
# 7. LIB max_value — candidate above threshold → fails with 1 violation
# ---------------------------------------------------------------------------

def test_lib_max_value_above_threshold_fails():
    rule = PolicyRule(
        metric="latency_ms",
        direction=Direction.LOWER_IS_BETTER,
        severity=Severity.HIGH,
        max_value=200.0,
    )
    baseline = make_baseline("latency_ms", 180.0)
    candidate = make_candidate("latency_ms", 250.0)  # above 200

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is False
    assert isinstance(result.violations, tuple)
    assert len(result.violations) == 1

    v = result.violations[0]
    assert v.candidate_value == 250.0
    assert v.baseline_value == 180.0
    assert v.threshold == 200.0


# ---------------------------------------------------------------------------
# 8. LIB regression — candidate within pct → passes
# ---------------------------------------------------------------------------

def test_lib_regression_within_pct_passes():
    rule = PolicyRule(
        metric="error_rate",
        direction=Direction.LOWER_IS_BETTER,
        severity=Severity.WARNING,
        max_regression_pct=10.0,  # ceiling = 0.05 * 1.10 = 0.055
    )
    baseline = make_baseline("error_rate", 0.05)
    candidate = make_candidate("error_rate", 0.054)  # below ceiling

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is True
    assert result.violations == ()


# ---------------------------------------------------------------------------
# 9. LIB regression — candidate above ceiling → fails with 1 violation
# ---------------------------------------------------------------------------

def test_lib_regression_above_ceiling_fails():
    rule = PolicyRule(
        metric="error_rate",
        direction=Direction.LOWER_IS_BETTER,
        severity=Severity.WARNING,
        max_regression_pct=10.0,  # ceiling = 0.05 * 1.10 = 0.055
    )
    baseline = make_baseline("error_rate", 0.05)
    candidate = make_candidate("error_rate", 0.07)  # above ceiling 0.055

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is False
    assert isinstance(result.violations, tuple)
    assert len(result.violations) == 1

    v = result.violations[0]
    assert v.candidate_value == 0.07
    assert v.baseline_value == 0.05
    expected_ceiling = 0.05 * 1.10
    assert abs(v.threshold - expected_ceiling) < 1e-9


# ---------------------------------------------------------------------------
# 10. LIB dual violation — above BOTH max_value AND regression ceiling → 2 violations
# ---------------------------------------------------------------------------

def test_lib_dual_violation_two_violations():
    rule = PolicyRule(
        metric="p99_latency_ms",
        direction=Direction.LOWER_IS_BETTER,
        severity=Severity.HIGH,
        max_value=500.0,         # candidate (700) > 500
        max_regression_pct=5.0,  # ceiling = 400 * 1.05 = 420; candidate (700) > 420
    )
    baseline = make_baseline("p99_latency_ms", 400.0)
    candidate = make_candidate("p99_latency_ms", 700.0)

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is False
    assert isinstance(result.violations, tuple)
    assert len(result.violations) == 2

    for v in result.violations:
        assert v.metric == "p99_latency_ms"
        assert v.candidate_value == 700.0


# ---------------------------------------------------------------------------
# 11. Critical gate — metric absent from candidate → is_critical_gate_violation=True, passed=False
# ---------------------------------------------------------------------------

def test_critical_gate_absent_metric_blocks():
    rule = PolicyRule(
        metric="safety_score",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.CRITICAL,
        is_critical_gate=True,
        min_value=0.99,
    )
    baseline = make_baseline("safety_score", 0.995)
    candidate = EvalInput(model="candidate-model", run_id="run-cand", metrics={})

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is False
    assert isinstance(result.violations, tuple)
    assert len(result.violations) == 1

    v = result.violations[0]
    assert v.is_critical_gate_violation is True
    assert v.candidate_value is None
    assert v.metric == "safety_score"


# ---------------------------------------------------------------------------
# 12. Critical gate — metric present in candidate → normal value comparison proceeds
# ---------------------------------------------------------------------------

def test_critical_gate_metric_present_proceeds_normally():
    rule = PolicyRule(
        metric="safety_score",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.CRITICAL,
        is_critical_gate=True,
        min_value=0.99,
    )
    baseline = make_baseline("safety_score", 0.995)
    # Candidate has the metric and it passes
    candidate = make_candidate("safety_score", 0.995)

    (result,) = evaluate(baseline, candidate, (rule,))

    # The critical gate check is bypassed because the metric is present;
    # value comparison proceeds — in this case it passes
    assert result.passed is True
    for v in result.violations:
        assert v.is_critical_gate_violation is False


def test_critical_gate_metric_present_but_fails_value():
    """Metric is present in candidate but below min_value → normal violation, not a critical gate violation."""
    rule = PolicyRule(
        metric="safety_score",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.CRITICAL,
        is_critical_gate=True,
        min_value=0.99,
    )
    baseline = make_baseline("safety_score", 0.995)
    candidate = make_candidate("safety_score", 0.97)  # below 0.99

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is False
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.is_critical_gate_violation is False
    assert v.candidate_value == 0.97


# ---------------------------------------------------------------------------
# 13. Non-critical absent metric — not in candidate, is_critical_gate=False → passed=True
# ---------------------------------------------------------------------------

def test_non_critical_absent_metric_passes():
    rule = PolicyRule(
        metric="bleu_score",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.INFO,
        is_critical_gate=False,
    )
    baseline = make_baseline("bleu_score", 0.75)
    candidate = EvalInput(model="candidate-model", run_id="run-cand", metrics={})

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is True
    assert isinstance(result.violations, tuple)
    assert result.violations == ()


# ---------------------------------------------------------------------------
# 14. Missing baseline metric → raises InputError with exit_code=2
# ---------------------------------------------------------------------------

def test_missing_baseline_metric_raises_input_error():
    rule = PolicyRule(
        metric="rouge_score",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.WARNING,
    )
    # Baseline does NOT contain the metric referenced by the rule
    baseline = EvalInput(model="baseline-model", run_id="run-base", metrics={"other_metric": 1.0})
    candidate = make_candidate("rouge_score", 0.80)

    with pytest.raises(InputError) as exc_info:
        evaluate(baseline, candidate, (rule,))

    assert exc_info.value.exit_code == 2
    assert "rouge_score" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 15. Rule order — results tuple length equals rules tuple length, results[i].rule == rules[i]
# ---------------------------------------------------------------------------

def test_rule_order_preserved():
    rules = (
        PolicyRule(
            metric="accuracy",
            direction=Direction.HIGHER_IS_BETTER,
            severity=Severity.HIGH,
            min_value=0.80,
        ),
        PolicyRule(
            metric="latency_ms",
            direction=Direction.LOWER_IS_BETTER,
            severity=Severity.WARNING,
            max_value=300.0,
        ),
        PolicyRule(
            metric="f1",
            direction=Direction.HIGHER_IS_BETTER,
            severity=Severity.INFO,
            min_value=0.70,
        ),
    )
    baseline = EvalInput(
        model="baseline-model",
        run_id="run-base",
        metrics={"accuracy": 0.90, "latency_ms": 200.0, "f1": 0.80},
    )
    candidate = EvalInput(
        model="candidate-model",
        run_id="run-cand",
        metrics={"accuracy": 0.88, "latency_ms": 220.0, "f1": 0.78},
    )

    results = evaluate(baseline, candidate, rules)

    assert len(results) == len(rules)
    for i, (result, rule) in enumerate(zip(results, rules)):
        assert result.rule is rule, f"results[{i}].rule does not match rules[{i}]"


# ---------------------------------------------------------------------------
# 16. Multiple rules — evaluate returns one RuleResult per rule in order
# ---------------------------------------------------------------------------

def test_multiple_rules_one_result_per_rule():
    """Checks both ordering and independence of results for multiple rules."""
    rules = (
        PolicyRule(
            metric="accuracy",
            direction=Direction.HIGHER_IS_BETTER,
            severity=Severity.HIGH,
            min_value=0.80,
        ),
        PolicyRule(
            metric="latency_ms",
            direction=Direction.LOWER_IS_BETTER,
            severity=Severity.WARNING,
            max_value=250.0,
        ),
    )
    baseline = EvalInput(
        model="baseline-model",
        run_id="run-base",
        metrics={"accuracy": 0.90, "latency_ms": 200.0},
    )
    # accuracy passes (0.85 >= 0.80); latency fails (300 > 250)
    candidate = EvalInput(
        model="candidate-model",
        run_id="run-cand",
        metrics={"accuracy": 0.85, "latency_ms": 300.0},
    )

    results = evaluate(baseline, candidate, rules)

    assert len(results) == 2

    accuracy_result = results[0]
    assert accuracy_result.rule is rules[0]
    assert accuracy_result.passed is True
    assert accuracy_result.violations == ()

    latency_result = results[1]
    assert latency_result.rule is rules[1]
    assert latency_result.passed is False
    assert len(latency_result.violations) == 1
    assert latency_result.violations[0].candidate_value == 300.0


# ---------------------------------------------------------------------------
# 17. HIB with only max_regression_pct (no min_value) — correct floor calculation
# ---------------------------------------------------------------------------

def test_hib_only_regression_pct_correct_floor():
    """max_regression_pct=10 with baseline=0.90 → floor=0.81; candidate just below fails."""
    rule = PolicyRule(
        metric="recall",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.WARNING,
        max_regression_pct=10.0,  # floor = 0.90 * 0.90 = 0.81
    )
    baseline = make_baseline("recall", 0.90)

    # Candidate above floor → passes
    candidate_above = make_candidate("recall", 0.82)
    (result_pass,) = evaluate(baseline, candidate_above, (rule,))
    assert result_pass.passed is True
    assert result_pass.violations == ()

    # Candidate at exactly the floor → passes (boundary: floor is inclusive only in the strict <)
    # engine uses: candidate_value < floor → violation, so exactly at floor passes
    candidate_at_floor = make_candidate("recall", 0.81)
    (result_at,) = evaluate(baseline, candidate_at_floor, (rule,))
    assert result_at.passed is True

    # Candidate below floor → fails
    candidate_below = make_candidate("recall", 0.80)
    (result_fail,) = evaluate(baseline, candidate_below, (rule,))
    assert result_fail.passed is False
    assert len(result_fail.violations) == 1
    v = result_fail.violations[0]
    expected_floor = 0.90 * (1.0 - 10.0 / 100.0)
    assert abs(v.threshold - expected_floor) < 1e-9
    assert v.candidate_value == 0.80
    assert v.baseline_value == 0.90


# ---------------------------------------------------------------------------
# Additional invariant checks
# ---------------------------------------------------------------------------

def test_violations_is_always_tuple_not_list():
    """RuleResult.violations must always be a tuple, never a list or None."""
    rule = PolicyRule(
        metric="accuracy",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.HIGH,
        min_value=0.80,
    )
    baseline = make_baseline("accuracy", 0.90)

    for candidate_value, should_pass in [(0.85, True), (0.75, False)]:
        candidate = make_candidate("accuracy", candidate_value)
        (result,) = evaluate(baseline, candidate, (rule,))
        assert isinstance(result.violations, tuple), (
            f"violations should be tuple, got {type(result.violations)}"
        )
        assert result.violations is not None

    # Also check non-critical absent metric case
    absent_candidate = EvalInput(model="m", run_id="r", metrics={})
    (result_absent,) = evaluate(baseline, absent_candidate, (rule,))
    assert isinstance(result_absent.violations, tuple)


def test_passed_false_iff_violations_nonempty():
    """passed is False if and only if violations is non-empty."""
    rules = (
        PolicyRule(
            metric="accuracy",
            direction=Direction.HIGHER_IS_BETTER,
            severity=Severity.HIGH,
            min_value=0.80,
        ),
        PolicyRule(
            metric="latency_ms",
            direction=Direction.LOWER_IS_BETTER,
            severity=Severity.WARNING,
            max_value=250.0,
        ),
    )
    baseline = EvalInput(
        model="m", run_id="r",
        metrics={"accuracy": 0.90, "latency_ms": 200.0},
    )
    candidate = EvalInput(
        model="m", run_id="r",
        metrics={"accuracy": 0.75, "latency_ms": 300.0},  # both fail
    )

    results = evaluate(baseline, candidate, rules)
    for result in results:
        if result.passed:
            assert result.violations == ()
        else:
            assert len(result.violations) > 0


def test_violation_fields_set_correctly_hib_min_value():
    """Verify candidate_value, baseline_value, threshold are all set on a min_value violation."""
    rule = PolicyRule(
        metric="accuracy",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.HIGH,
        min_value=0.90,
    )
    baseline = make_baseline("accuracy", 0.95)
    candidate = make_candidate("accuracy", 0.85)

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is False
    v = result.violations[0]
    assert v.metric == "accuracy"
    assert v.candidate_value == 0.85
    assert v.baseline_value == 0.95
    assert v.threshold == 0.90
    assert v.reason  # not empty
    assert isinstance(v.reason, str)


def test_violation_fields_set_correctly_lib_max_value():
    """Verify candidate_value, baseline_value, threshold on a max_value violation."""
    rule = PolicyRule(
        metric="latency_ms",
        direction=Direction.LOWER_IS_BETTER,
        severity=Severity.WARNING,
        max_value=100.0,
    )
    baseline = make_baseline("latency_ms", 80.0)
    candidate = make_candidate("latency_ms", 150.0)

    (result,) = evaluate(baseline, candidate, (rule,))

    assert result.passed is False
    v = result.violations[0]
    assert v.metric == "latency_ms"
    assert v.candidate_value == 150.0
    assert v.baseline_value == 80.0
    assert v.threshold == 100.0
    assert v.reason
    assert isinstance(v.reason, str)


def test_empty_rules_returns_empty_tuple():
    """No rules → empty results tuple."""
    baseline = make_baseline("accuracy", 0.90)
    candidate = make_candidate("accuracy", 0.85)

    results = evaluate(baseline, candidate, ())

    assert results == ()
    assert isinstance(results, tuple)
