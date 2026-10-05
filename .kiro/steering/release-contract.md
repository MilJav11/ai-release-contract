# Release Contract — Implementation Invariants

These are the non-negotiable correctness invariants of AI Release Contract. Every implementation decision must be consistent with all of them. They are also the formal basis for the required property-based tests.

---

## Verdict Invariants

### 1. Critical and high severity violations always block

If any `Violation` in the engine output has `severity == critical` or `severity == high`, the verdict MUST be `BLOCK`. No other metric, rule result, or condition can override this.

### 2. Warning and info violations never block

`warning` and `info` violations are recorded and reported, but they MUST NOT cause a `BLOCK` verdict. A release with only warning/info violations MUST be `APPROVE`.

### 3. No compensation across metrics

The system MUST NOT compute any aggregate score, composite score, or weighted sum across metrics. A passing result on one rule MUST NOT reduce, cancel, or offset a violation on any other rule. Rules are evaluated independently.

### 4. Fail closed for missing required critical metrics

If a policy rule has `is_critical_gate: true` and the named metric is **absent** from the candidate, the system MUST produce a `BLOCK` verdict. Absence is treated as a critical failure, not as a skipped check. This applies regardless of the rule's `severity` field value.

### 5. All violations are preserved

Every violation produced by every rule evaluation MUST be included in the `Report.violations` tuple and serialised into the JSON report. A rule may produce up to two violations (one for an absolute threshold failure, one for a regression threshold failure). Both MUST be preserved.

---

## Determinism Invariants

### 6. Identical inputs always produce identical outputs

Invoking `engine.evaluate()` twice on the same `(baseline, candidate, rules)` objects MUST return `RuleResult` tuples that are equal element-by-element, the same `Verdict`, and the same violation set. There are no sources of non-determinism permitted: no clocks, no RNG, no network, no environment variable reads during evaluation.

### 7. Rule evaluation order matches policy declaration order

`rule_results[i].rule` MUST equal `rules[i]` for all valid indices. The engine MUST process and return results in the order rules appear in the YAML file.

---

## Input Validation Invariants

### 8. Malformed or semantically invalid configuration exits with code 2

Any of the following conditions MUST cause the system to exit with code `2` before evaluation begins:

- Baseline or candidate file is missing, unreadable, or contains invalid JSON
- Policy file is missing, unreadable, or contains invalid YAML
- `model`, `run_id`, or `metrics` keys are missing or wrong type in a metrics file
- A metric value is a boolean (`True`/`False`) — check `isinstance(value, bool)` BEFORE `isinstance(value, (int, float))` because `bool` is a subclass of `int` in Python
- A metric value is non-finite (`NaN`, `+Infinity`, `-Infinity`)
- A policy rule's `min_value` or `max_value` is non-finite
- A policy rule's `max_regression_pct` is negative or non-finite
- A policy rule has an unknown `direction` or `severity` value
- A `higher_is_better` rule contains a `max_value` field (semantically incorrect)
- A `lower_is_better` rule contains a `min_value` field (semantically incorrect)
- A policy rule references a metric name absent from the baseline

### 9. Boolean values are invalid metric values

Python's `bool` is a subclass of `int`. The loader MUST explicitly check `isinstance(value, bool)` first and reject it with exit code 2. It MUST NOT allow `True` or `False` to pass through as `1` or `0`.

---

## Runtime Constraints (Absolute)

### 10. No network or runtime AI dependency

The system MUST be fully offline. It MUST NOT make any network calls, HTTP requests, DNS lookups, or calls to any LLM API at runtime — including during evaluation, loading, or reporting. This is a hard architectural constraint, not a performance preference.

---

## Required Property-Based Tests

The following four properties MUST be verified with Hypothesis and are not optional:

| Property | Invariant Verified |
|----------|-------------------|
| **Property 4** | Absent critical gate metric always produces `BLOCK` |
| **Property 7** | Blocking violation always produces `BLOCK` regardless of improvements elsewhere |
| **Property 8** | `APPROVE` if and only if there are zero blocking violations |
| **Property 9** | Identical inputs always produce identical outputs (determinism) |

These tests MUST use `@given` strategies that generate arbitrary valid inputs, not just fixed examples. Hypothesis settings: `max_examples=200` for CI, `max_examples=500` when `HYPOTHESIS_MAX_EXAMPLES` env var is set.

---

## Version Control

The entire `.kiro/` directory — including specs, steering files, and hooks — is intentional project evidence and MUST be committed to version control. Do NOT add `.kiro` to `.gitignore`.
