"""
Cross-cutting Hypothesis property tests for AI Release Contract.

Properties covered here:
  Property 3 (Task 4.2) — missing baseline metric → InputError(exit_code=2)
  Property 4 (Task 4.3) — absent critical gate metric → is_critical_gate_violation
  Property 5 (Task 4.4) — higher-is-better threshold and regression checks
  Property 6 (Task 4.5) — lower-is-better threshold and regression checks

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ai_release_contract.engine import evaluate
from ai_release_contract.exceptions import InputError
from ai_release_contract.models import Direction, EvalInput, PolicyRule, Severity


# ---------------------------------------------------------------------------
# Shared strategy helpers
# ---------------------------------------------------------------------------


@st.composite
def valid_metric_name(draw: st.DrawFn) -> str:
    """Generate a non-empty alphanumeric metric name (max 20 chars)."""
    return draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"),
                min_codepoint=1,
            ),
            min_size=1,
            max_size=20,
        )
    )


@st.composite
def positive_finite_float(draw: st.DrawFn) -> float:
    """Generate a strictly positive, finite float in a sane range."""
    return draw(
        st.floats(
            min_value=0.001,
            max_value=1000.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )


@st.composite
def finite_float(draw: st.DrawFn) -> float:
    """Generate any finite float (no NaN / inf)."""
    return draw(st.floats(allow_nan=False, allow_infinity=False))


# ---------------------------------------------------------------------------
# Property 3 — Missing baseline metric → InputError(exit_code=2)
# Validates: Requirements 2.1
# ---------------------------------------------------------------------------


@st.composite
def policy_with_missing_baseline_metric(draw: st.DrawFn):
    """
    Produce a (baseline_metrics, candidate_metrics, rules) triple where at
    least one rule references a metric that is NOT present in baseline_metrics.
    """
    # Build a small pool of metric names that WILL be in the baseline.
    present_names: list[str] = draw(
        st.lists(valid_metric_name(), min_size=0, max_size=4, unique=True)
    )
    # A separate metric name that is guaranteed to be absent from baseline.
    absent_name: str = draw(valid_metric_name())
    assume(absent_name not in present_names)

    baseline_metrics: dict[str, float] = {
        name: draw(positive_finite_float()) for name in present_names
    }
    candidate_metrics: dict[str, float] = {
        name: draw(positive_finite_float()) for name in present_names
    }
    # Also put the absent metric in the candidate — doesn't matter; engine
    # checks baseline first.
    candidate_metrics[absent_name] = draw(positive_finite_float())

    # Build rules: at least one rule targets the absent metric.
    absent_rule = PolicyRule(
        metric=absent_name,
        direction=draw(st.sampled_from(Direction)),
        severity=draw(st.sampled_from(Severity)),
    )
    # Only add extra rules when there are present metrics to sample from.
    if present_names:
        extra_rule_metrics = draw(st.lists(st.sampled_from(present_names), max_size=2))
        extra_rules = [
            PolicyRule(
                metric=name,
                direction=draw(st.sampled_from(Direction)),
                severity=draw(st.sampled_from(Severity)),
            )
            for name in extra_rule_metrics
        ]
    else:
        extra_rules = []
    rules = tuple([absent_rule] + extra_rules)

    return baseline_metrics, candidate_metrics, rules


@given(triple=policy_with_missing_baseline_metric())
@settings(max_examples=50)
def test_property3_missing_baseline_metric_raises_input_error(triple):
    """
    Property 3: any rule that references a metric absent from the baseline
    causes evaluate() to raise InputError with exit_code == 2.

    **Validates: Requirements 2.1**
    """
    baseline_metrics, candidate_metrics, rules = triple

    baseline = EvalInput(model="baseline_model", run_id="b-1", metrics=baseline_metrics)
    candidate = EvalInput(model="candidate_model", run_id="c-1", metrics=candidate_metrics)

    with pytest.raises(InputError) as exc_info:
        evaluate(baseline, candidate, rules)

    assert exc_info.value.exit_code == 2


# ---------------------------------------------------------------------------
# Property 4 — Absent critical gate metric → is_critical_gate_violation
# Validates: Requirements 2.2
# ---------------------------------------------------------------------------


@st.composite
def critical_gate_absent_candidate(draw: st.DrawFn):
    """
    Produce a (baseline_metrics, candidate_metrics, rules) triple where at
    least one rule has is_critical_gate=True and that metric is present in
    the baseline but absent from the candidate.
    """
    # The critical metric name.
    critical_name: str = draw(valid_metric_name())
    baseline_value: float = draw(positive_finite_float())

    # Optional extra metrics that are present in both.
    extra_names: list[str] = draw(
        st.lists(valid_metric_name(), min_size=0, max_size=3, unique=True)
    )
    assume(critical_name not in extra_names)

    baseline_metrics: dict[str, float] = {critical_name: baseline_value}
    candidate_metrics: dict[str, float] = {}
    for name in extra_names:
        val = draw(positive_finite_float())
        baseline_metrics[name] = val
        candidate_metrics[name] = draw(positive_finite_float())
    # critical_name intentionally absent from candidate_metrics.

    critical_rule = PolicyRule(
        metric=critical_name,
        direction=draw(st.sampled_from(Direction)),
        severity=draw(st.sampled_from(Severity)),
        is_critical_gate=True,
    )
    extra_rules = [
        PolicyRule(
            metric=name,
            direction=draw(st.sampled_from(Direction)),
            severity=draw(st.sampled_from(Severity)),
        )
        for name in extra_names
    ]
    rules = tuple([critical_rule] + extra_rules)

    return baseline_metrics, candidate_metrics, rules


@given(triple=critical_gate_absent_candidate())
@settings(max_examples=50)
def test_property4_absent_critical_gate_metric_blocks(triple):
    """
    Property 4: when a critical gate rule's metric is absent from the
    candidate, the engine produces a Violation with is_critical_gate_violation=True.

    **Validates: Requirements 2.2**
    """
    baseline_metrics, candidate_metrics, rules = triple

    baseline = EvalInput(model="baseline_model", run_id="b-1", metrics=baseline_metrics)
    candidate = EvalInput(model="candidate_model", run_id="c-1", metrics=candidate_metrics)

    results = evaluate(baseline, candidate, rules)

    assert any(
        v.is_critical_gate_violation
        for r in results
        for v in r.violations
    ), (
        "Expected at least one is_critical_gate_violation=True violation when "
        "a critical gate metric is absent from the candidate."
    )


# ---------------------------------------------------------------------------
# Property 5 — Higher-is-better threshold and regression checks
# Validates: Requirements 2.3
# ---------------------------------------------------------------------------


@st.composite
def higher_is_better_scenario(draw: st.DrawFn):
    """
    Produce everything needed to check a single HIGHER_IS_BETTER rule:
      baseline_value, candidate_value, optional min_value, optional max_regression_pct.
    """
    baseline_value: float = draw(positive_finite_float())
    candidate_value: float = draw(
        st.floats(min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False)
    )
    min_value: float | None = draw(
        st.one_of(st.none(), positive_finite_float())
    )
    max_regression_pct: float | None = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        )
    )
    return baseline_value, candidate_value, min_value, max_regression_pct


@given(scenario=higher_is_better_scenario())
@settings(max_examples=50)
def test_property5_higher_is_better_threshold_and_regression(scenario):
    """
    Property 5: for a HIGHER_IS_BETTER rule:
      - A threshold violation exists iff candidate_value < min_value.
      - A regression violation exists iff candidate_value < baseline * (1 - pct/100).

    **Validates: Requirements 2.3**
    """
    baseline_value, candidate_value, min_value, max_regression_pct = scenario

    metric_name = "accuracy"
    rule = PolicyRule(
        metric=metric_name,
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.HIGH,
        min_value=min_value,
        max_regression_pct=max_regression_pct,
    )

    baseline = EvalInput(
        model="b", run_id="b-1", metrics={metric_name: baseline_value}
    )
    candidate = EvalInput(
        model="c", run_id="c-1", metrics={metric_name: candidate_value}
    )

    (result,) = evaluate(baseline, candidate, (rule,))

    # Collect whether a threshold violation and a regression violation were produced.
    threshold_violated = any(
        v.threshold == min_value for v in result.violations
    ) if min_value is not None else False

    regression_floor = (
        baseline_value * (1.0 - max_regression_pct / 100.0)
        if max_regression_pct is not None
        else None
    )
    regression_violated = any(
        v.threshold == regression_floor for v in result.violations
    ) if regression_floor is not None else False

    # Assert threshold check: violation iff candidate < min_value.
    if min_value is not None:
        if candidate_value < min_value:
            assert threshold_violated, (
                f"Expected threshold violation: {candidate_value} < {min_value}"
            )
        else:
            assert not threshold_violated, (
                f"Unexpected threshold violation: {candidate_value} >= {min_value}"
            )

    # Assert regression check: violation iff candidate < baseline * (1 - pct/100).
    if regression_floor is not None:
        if candidate_value < regression_floor:
            assert regression_violated, (
                f"Expected regression violation: {candidate_value} < {regression_floor}"
            )
        else:
            assert not regression_violated, (
                f"Unexpected regression violation: {candidate_value} >= {regression_floor}"
            )


# ---------------------------------------------------------------------------
# Property 6 — Lower-is-better threshold and regression checks
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------


@st.composite
def lower_is_better_scenario(draw: st.DrawFn):
    """
    Produce everything needed to check a single LOWER_IS_BETTER rule:
      baseline_value, candidate_value, optional max_value, optional max_regression_pct.
    """
    baseline_value: float = draw(positive_finite_float())
    candidate_value: float = draw(
        st.floats(min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False)
    )
    max_value: float | None = draw(
        st.one_of(st.none(), positive_finite_float())
    )
    max_regression_pct: float | None = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        )
    )
    return baseline_value, candidate_value, max_value, max_regression_pct


@given(scenario=lower_is_better_scenario())
@settings(max_examples=50)
def test_property6_lower_is_better_threshold_and_regression(scenario):
    """
    Property 6: for a LOWER_IS_BETTER rule:
      - A threshold violation exists iff candidate_value > max_value.
      - A regression violation exists iff candidate_value > baseline * (1 + pct/100).

    **Validates: Requirements 2.4**
    """
    baseline_value, candidate_value, max_value, max_regression_pct = scenario

    metric_name = "latency_p99"
    rule = PolicyRule(
        metric=metric_name,
        direction=Direction.LOWER_IS_BETTER,
        severity=Severity.HIGH,
        max_value=max_value,
        max_regression_pct=max_regression_pct,
    )

    baseline = EvalInput(
        model="b", run_id="b-1", metrics={metric_name: baseline_value}
    )
    candidate = EvalInput(
        model="c", run_id="c-1", metrics={metric_name: candidate_value}
    )

    (result,) = evaluate(baseline, candidate, (rule,))

    # Collect whether a threshold violation and a regression violation were produced.
    threshold_violated = any(
        v.threshold == max_value for v in result.violations
    ) if max_value is not None else False

    regression_ceiling = (
        baseline_value * (1.0 + max_regression_pct / 100.0)
        if max_regression_pct is not None
        else None
    )
    regression_violated = any(
        v.threshold == regression_ceiling for v in result.violations
    ) if regression_ceiling is not None else False

    # Assert threshold check: violation iff candidate > max_value.
    if max_value is not None:
        if candidate_value > max_value:
            assert threshold_violated, (
                f"Expected threshold violation: {candidate_value} > {max_value}"
            )
        else:
            assert not threshold_violated, (
                f"Unexpected threshold violation: {candidate_value} <= {max_value}"
            )

    # Assert regression check: violation iff candidate > baseline * (1 + pct/100).
    if regression_ceiling is not None:
        if candidate_value > regression_ceiling:
            assert regression_violated, (
                f"Expected regression violation: {candidate_value} > {regression_ceiling}"
            )
        else:
            assert not regression_violated, (
                f"Unexpected regression violation: {candidate_value} <= {regression_ceiling}"
            )

# ---------------------------------------------------------------------------
# Required Challenge Properties 4, 7, 8, 9
# ---------------------------------------------------------------------------

from ai_release_contract.models import RuleResult, Verdict, Violation
from ai_release_contract.verdict import determine_verdict


@given(triple=critical_gate_absent_candidate())
@settings(max_examples=50)
def test_property4_absent_critical_gate_metric_final_verdict_is_block(triple):
    """Property 4: an absent required critical-gate metric always BLOCKS."""

    baseline_metrics, candidate_metrics, rules = triple

    baseline = EvalInput(
        model="baseline",
        run_id="b-1",
        metrics=baseline_metrics,
    )
    candidate = EvalInput(
        model="candidate",
        run_id="c-1",
        metrics=candidate_metrics,
    )

    results = evaluate(baseline, candidate, rules)
    verdict, violations = determine_verdict(results)

    assert verdict == Verdict.BLOCK
    assert any(v.is_critical_gate_violation for v in violations)


@given(
    blocking_severity=st.sampled_from(
        [Severity.CRITICAL, Severity.HIGH]
    ),
    passing_count=st.integers(min_value=0, max_value=10),
)
@settings(max_examples=50)
def test_property7_blocking_violation_always_blocks(
    blocking_severity,
    passing_count,
):
    """
    Property 7: one blocking violation forces BLOCK regardless of
    how many other rules pass.
    """

    blocking_rule = PolicyRule(
        metric="blocking_metric",
        direction=Direction.HIGHER_IS_BETTER,
        severity=blocking_severity,
    )

    blocking_violation = Violation(
        metric="blocking_metric",
        severity=blocking_severity,
        reason="generated blocking violation",
        candidate_value=0.0,
        baseline_value=1.0,
        threshold=0.5,
    )

    results = [
        RuleResult(
            rule=blocking_rule,
            passed=False,
            violations=(blocking_violation,),
        )
    ]

    for index in range(passing_count):
        passing_rule = PolicyRule(
            metric=f"improved_metric_{index}",
            direction=Direction.HIGHER_IS_BETTER,
            severity=Severity.INFO,
        )
        results.append(
            RuleResult(
                rule=passing_rule,
                passed=True,
                violations=(),
            )
        )

    verdict, _ = determine_verdict(tuple(results))

    assert verdict == Verdict.BLOCK


@given(
    generated=st.lists(
        st.tuples(
            st.sampled_from(list(Severity)),
            st.booleans(),
        ),
        min_size=0,
        max_size=12,
    )
)
@settings(max_examples=100)
def test_property8_approve_iff_zero_blocking_violations(generated):
    """
    Property 8: APPROVE iff there are zero blocking violations.
    """

    results = []
    expected_block = False

    for index, (severity, critical_gate_violation) in enumerate(generated):
        rule = PolicyRule(
            metric=f"metric_{index}",
            direction=Direction.HIGHER_IS_BETTER,
            severity=severity,
        )

        violation = Violation(
            metric=f"metric_{index}",
            severity=severity,
            reason="generated violation",
            candidate_value=0.0,
            baseline_value=1.0,
            threshold=None,
            is_critical_gate_violation=critical_gate_violation,
        )

        results.append(
            RuleResult(
                rule=rule,
                passed=False,
                violations=(violation,),
            )
        )

        if (
            critical_gate_violation
            or severity in (Severity.CRITICAL, Severity.HIGH)
        ):
            expected_block = True

    verdict, _ = determine_verdict(tuple(results))

    assert (verdict == Verdict.APPROVE) == (not expected_block)


@given(scenario=higher_is_better_scenario())
@settings(max_examples=100)
def test_property9_identical_inputs_produce_identical_outputs(scenario):
    """
    Property 9: identical inputs always produce identical evaluation output.
    """

    baseline_value, candidate_value, min_value, max_regression_pct = scenario

    rule = PolicyRule(
        metric="deterministic_metric",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.HIGH,
        min_value=min_value,
        max_regression_pct=max_regression_pct,
    )

    baseline = EvalInput(
        model="baseline",
        run_id="b-1",
        metrics={"deterministic_metric": baseline_value},
    )
    candidate = EvalInput(
        model="candidate",
        run_id="c-1",
        metrics={"deterministic_metric": candidate_value},
    )

    first = evaluate(baseline, candidate, (rule,))
    second = evaluate(baseline, candidate, (rule,))

    assert first == second
    assert determine_verdict(first) == determine_verdict(second)
