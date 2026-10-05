# Design Document — AI Release Contract

## Overview

AI Release Contract is a single-process, offline CLI tool that consumes three files (baseline metrics JSON, candidate metrics JSON, release policy YAML) and emits a deterministic APPROVE/BLOCK verdict via exit code, Rich console output, and a JSON report. The design is intentionally minimal: no threads, no I/O beyond file reads and a single file write, no global mutable state, and no external network calls.

---

## Module and Package Structure

```
ai_release_contract/
├── __init__.py
├── __main__.py          # entry point: python -m ai_release_contract
├── cli.py               # argparse wiring; calls loader → engine → reporter
├── models.py            # all dataclasses and enums
├── loader.py            # file I/O, JSON/YAML parsing, schema validation
├── engine.py            # comparison engine: rule evaluation, violation accumulation
├── verdict.py           # verdict determination from violation list
├── reporter/
│   ├── __init__.py
│   ├── console.py       # Rich-based console output
│   └── json_report.py   # JSON report serialisation and disk write
└── exceptions.py        # InputError (exit 2), typed subclasses

examples/
├── baseline.json
├── good_candidate.json
├── bad_candidate.json
└── policy.yaml

tests/
├── conftest.py          # shared fixtures, Hypothesis profiles
├── test_loader.py       # unit + property tests for loader
├── test_engine.py       # unit + property tests for engine
├── test_verdict.py      # unit + property tests for verdict
├── test_reporter.py     # unit tests for report schema
├── test_cli_examples.py # end-to-end example-file tests
└── test_properties.py   # cross-cutting Hypothesis property tests
```

`__main__.py` contains a single line:

```python
from ai_release_contract.cli import main
main()
```

This allows `python -m ai_release_contract check --baseline ... --candidate ... --policy ...`.

---

## Data Models (`models.py`)

All models are `@dataclass(frozen=True)` to enforce immutability and support equality comparison needed by the determinism properties.

### Enums

```python
from enum import Enum

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

BLOCKING_SEVERITIES: frozenset[Severity] = frozenset({Severity.CRITICAL, Severity.HIGH})
```

### PolicyRule

```python
@dataclass(frozen=True)
class PolicyRule:
    metric: str
    direction: Direction
    severity: Severity
    is_critical_gate: bool = False
    min_value: float | None = None      # only meaningful for higher_is_better
    max_value: float | None = None      # only meaningful for lower_is_better
    max_regression_pct: float | None = None
```

### EvalInput

Immutable snapshot of a loaded baseline or candidate file:

```python
@dataclass(frozen=True)
class EvalInput:
    model: str
    run_id: str
    metrics: dict[str, float]  # frozen via __post_init__ deepcopy
```

`EvalInput.__post_init__` stores `metrics` as a `types.MappingProxyType` to prevent mutation after load.

### Violation

```python
@dataclass(frozen=True)
class Violation:
    metric: str
    severity: Severity
    reason: str
    candidate_value: float | None
    baseline_value: float | None = None
    threshold: float | None = None
    is_critical_gate_violation: bool = False
```

`candidate_value` is `None` when the metric is absent from the candidate (critical gate absent case).

### RuleResult

Intermediate record produced for every rule, whether it passes or fails:

```python
@dataclass(frozen=True)
class RuleResult:
    rule: PolicyRule
    passed: bool
    violations: tuple[Violation, ...]  # empty tuple when passed
```

A passing rule has `violations = ()`. A failing rule has one or more `Violation` objects in `violations`.

### Report

Top-level output structure:

```python
@dataclass(frozen=True)
class Report:
    verdict: Verdict
    exit_code: int                  # 0 or 1
    baseline: EvalInput
    candidate: EvalInput
    violations: tuple[Violation, ...]
    rule_results: tuple[RuleResult, ...]  # all rules in policy order
```

---

## Loader (`loader.py`)

Responsibility: read files from disk, parse them, validate shapes, raise `InputError` (exit 2) on any problem.

### Public API

```python
def load_eval_input(path: str, role: str) -> EvalInput:
    """role is "baseline" or "candidate" for error messages."""

def load_policy(path: str) -> tuple[PolicyRule, ...]:
    """Returns rules in YAML declaration order."""
```

### Load and Validate Flow

```
load_eval_input(path, role):
  1. Open file → OSError → InputError("Cannot read {role} file {path}: {e}")
  2. json.load()  → JSONDecodeError → InputError("Invalid JSON in {role}: {e}")
  3. Check top-level keys: model (str), run_id (str), metrics (dict)
     → missing/wrong type → InputError with field name
  4. Validate metrics values are all int or float
     → non-numeric value → InputError with metric name and value
  4a. Reject boolean metric values: check isinstance(value, bool) BEFORE
      isinstance(value, (int, float)), since bool is a subclass of int in Python.
      If bool, raise InputError naming the metric key and value.
  4b. Reject non-finite metric values: check math.isfinite(value) after confirming
      it is numeric. If not finite (NaN, Infinity, -Infinity), raise InputError
      naming the metric key.
  5. Return EvalInput(model, run_id, metrics)

load_policy(path):
  1. Open file → OSError → InputError(...)
  2. yaml.safe_load() → YAMLError → InputError(...)
  3. Check top-level key "rules" is a list → InputError if absent/wrong type
  4. For each item in rules:
     a. Check "metric" is a non-empty string
     b. Parse "direction" → Direction enum → InputError on unknown value
     c. Parse "severity" → Severity enum → InputError on unknown value
     d. Parse optional numeric fields: min_value, max_value, max_regression_pct
     d-i.  After parsing min_value / max_value: if present, check math.isfinite(value);
           raise InputError if not finite, naming the field and rule index.
     d-ii. After parsing max_regression_pct: if present, check math.isfinite(value)
           and value >= 0; raise InputError if either condition fails, naming the
           field and rule index.
     e. Direction-threshold consistency check:
        - If direction == higher_is_better and max_value is present in the rule dict:
          raise InputError("Rule {index}: max_value is not valid for direction higher_is_better").
        - If direction == lower_is_better and min_value is present in the rule dict:
          raise InputError("Rule {index}: min_value is not valid for direction lower_is_better").
     f. Parse optional bool: is_critical_gate (default False)
  5. Return tuple of PolicyRule in declaration order
```

The loader module imports `import math` for the finiteness checks in steps 4b, 4d-i, and 4d-ii.

All errors include the rule index (0-based) and the offending field to satisfy requirements 1.8 and 2.2.

---

## Comparison Engine (`engine.py`)

The engine is a pure function: given two `EvalInput` objects and a sequence of `PolicyRule` objects, it returns an ordered tuple of `RuleResult` objects. It has no side effects and reads no external state.

### Public API

```python
def evaluate(
    baseline: EvalInput,
    candidate: EvalInput,
    rules: tuple[PolicyRule, ...],
) -> tuple[RuleResult, ...]:
    """
    Raises InputError (exit 2) if any rule references a metric absent
    from baseline (Requirement 2). Otherwise returns one RuleResult per
    rule in declaration order.
    """
```

### Algorithm

```
evaluate(baseline, candidate, rules):

  Step 1 — Baseline availability check (Req 2):
    For each rule in rules:
      if rule.metric not in baseline.metrics:
        raise InputError(exit_code=2,
          "Policy rule '{rule.metric}' references metric not present "
          "in baseline. Baseline metrics: {list(baseline.metrics.keys())}")

  Step 2 — Rule evaluation loop (in declaration order):
    results = []
    for rule in rules:
      result = _evaluate_rule(rule, baseline, candidate)
      results.append(result)
    return tuple(results)

_evaluate_rule(rule, baseline, candidate):

  baseline_value = baseline.metrics[rule.metric]  # always exists (Step 1 passed)

  # Critical gate check (Req 3) — takes priority over value comparisons
  if rule.is_critical_gate and rule.metric not in candidate.metrics:
    violation = Violation(
      metric=rule.metric,
      severity=rule.severity,   # preserved but always treated as blocking
      reason="required critical metric absent from candidate",
      candidate_value=None,
      baseline_value=baseline_value,
      threshold=None,
      is_critical_gate_violation=True,
    )
    return RuleResult(rule=rule, passed=False, violations=(violation,))

  # Metric absent from candidate but NOT a critical gate → skip (no violation)
  if rule.metric not in candidate.metrics:
    return RuleResult(rule=rule, passed=True, violations=())

  candidate_value = candidate.metrics[rule.metric]
  violations_for_rule: list[Violation] = []

  if rule.direction == Direction.HIGHER_IS_BETTER:
    # Absolute threshold check (Req 4.1–4.2)
    if rule.min_value is not None and candidate_value < rule.min_value:
      violations_for_rule.append(Violation(
        metric=rule.metric,
        severity=rule.severity,
        reason=f"candidate {candidate_value} < min_value {rule.min_value}",
        candidate_value=candidate_value,
        baseline_value=baseline_value,
        threshold=rule.min_value,
      ))
    # Regression check (Req 4.3–4.4)
    if rule.max_regression_pct is not None:
      floor = baseline_value * (1.0 - rule.max_regression_pct / 100.0)
      if candidate_value < floor:
        violations_for_rule.append(Violation(
          metric=rule.metric,
          severity=rule.severity,
          reason=(f"candidate {candidate_value} < regression floor "
                  f"{floor:.6g} (baseline {baseline_value} "
                  f"- {rule.max_regression_pct}%)"),
          candidate_value=candidate_value,
          baseline_value=baseline_value,
          threshold=floor,
        ))

  else:  # LOWER_IS_BETTER
    # Absolute threshold check (Req 5.1–5.2)
    if rule.max_value is not None and candidate_value > rule.max_value:
      violations_for_rule.append(Violation(
        metric=rule.metric,
        severity=rule.severity,
        reason=f"candidate {candidate_value} > max_value {rule.max_value}",
        candidate_value=candidate_value,
        baseline_value=baseline_value,
        threshold=rule.max_value,
      ))
    # Regression check (Req 5.3–5.4)
    if rule.max_regression_pct is not None:
      ceiling = baseline_value * (1.0 + rule.max_regression_pct / 100.0)
      if candidate_value > ceiling:
        violations_for_rule.append(Violation(
          metric=rule.metric,
          severity=rule.severity,
          reason=(f"candidate {candidate_value} > regression ceiling "
                  f"{ceiling:.6g} (baseline {baseline_value} "
                  f"+ {rule.max_regression_pct}%)"),
          candidate_value=candidate_value,
          baseline_value=baseline_value,
          threshold=ceiling,
        ))

  # A rule may produce 0, 1, or 2 violations (threshold + regression both fail).
  if violations_for_rule:
    return RuleResult(rule=rule, passed=False, violations=tuple(violations_for_rule))
  return RuleResult(rule=rule, passed=True, violations=())
```

---

## Verdict Determination (`verdict.py`)

```python
def determine_verdict(
    rule_results: tuple[RuleResult, ...],
) -> tuple[Verdict, tuple[Violation, ...]]:
    """
    Returns (verdict, all_violations_in_rule_order).
    Verdict is BLOCK if any violation is blocking; APPROVE otherwise.
    """

    all_violations: list[Violation] = []
    for result in rule_results:
        all_violations.extend(result.violations)

    is_blocked = any(
        v.is_critical_gate_violation or v.severity in BLOCKING_SEVERITIES
        for v in all_violations
    )

    verdict = Verdict.BLOCK if is_blocked else Verdict.APPROVE
    return verdict, tuple(all_violations)
```

The verdict function is intentionally trivial — it performs a single linear scan with no scoring, weighting, or aggregation. This structural simplicity is the non-compensation guarantee.

---

## CLI Entry Point (`cli.py`)

```python
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m ai_release_contract",
        description="Deterministic AI release policy gate",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("--baseline", required=True)
    check.add_argument("--candidate", required=True)
    check.add_argument("--policy", required=True)
    check.add_argument("--output", default="release_report.json")

    args = parser.parse_args()

    try:
        baseline = load_eval_input(args.baseline, "baseline")
        candidate = load_eval_input(args.candidate, "candidate")
        rules = load_policy(args.policy)
    except InputError as e:
        console.print_error(str(e))
        sys.exit(2)

    try:
        rule_results = evaluate(baseline, candidate, rules)
    except InputError as e:          # baseline metric availability error
        console.print_error(str(e))
        sys.exit(2)

    verdict, violations = determine_verdict(rule_results)
    exit_code = 0 if verdict == Verdict.APPROVE else 1

    report = Report(
        verdict=verdict,
        exit_code=exit_code,
        baseline=baseline,
        candidate=candidate,
        violations=violations,
        rule_results=rule_results,
    )

    console_reporter.render(report)
    json_reporter.write(report, path=args.output)

    sys.exit(exit_code)
```

Error handling: only `InputError` propagates to `main`. All other exceptions are unhandled (unexpected bugs). This keeps the exit-code contract clean.

---

## Console Output Layout (`reporter/console.py`)

Uses `rich.console.Console`, `rich.table.Table`, `rich.panel.Panel`, and `rich.text.Text`.

### Rendering Sequence

```
┌─────────────────────────────────────────────────────┐
│            AI RELEASE CONTRACT VERDICT              │
│                     APPROVE                         │  ← green on APPROVE
│                      BLOCK                          │  ← red on BLOCK
└─────────────────────────────────────────────────────┘

Run Summary
  Baseline:  <model> / <run_id>
  Candidate: <model> / <run_id>
  Rules evaluated: N
  Violations: X critical, Y high, Z warning, W info

[If BLOCK] Blocking Violations
  ┌─────────────────┬──────────────┬──────────┬────────────────────────────────┐
  │ Metric          │ Candidate    │ Threshold│ Reason                         │
  ├─────────────────┼──────────────┼──────────┼────────────────────────────────┤
  │ task_success... │ 0.82         │ 0.90     │ candidate 0.82 < min_value 0.9 │
  └─────────────────┴──────────────┴──────────┴────────────────────────────────┘

[If non-blocking violations exist] Warnings / Info
  (same table structure, muted colours)
```

### Severity Colour Map

| Severity | Rich style |
|----------|-----------|
| critical | `bold red` |
| high     | `red` |
| warning  | `yellow` |
| info     | `cyan` |

Verdict banner: `bold green on dark_green` for APPROVE, `bold white on red` for BLOCK.

---

## JSON Report Schema (`reporter/json_report.py`)

Written by `json.dumps(..., indent=2, sort_keys=True)` for stable, diff-friendly output.

```json
{
  "verdict": "BLOCK",
  "exit_code": 1,
  "baseline": {
    "model": "gpt-4o-2024-11-20",
    "run_id": "eval-20240101-baseline"
  },
  "candidate": {
    "model": "gpt-4o-2024-12-17",
    "run_id": "eval-20240115-candidate"
  },
  "violations": [
    {
      "metric": "task_success_rate",
      "severity": "critical",
      "reason": "candidate 0.82 < min_value 0.9",
      "candidate_value": 0.82,
      "baseline_value": 0.95,
      "threshold": 0.9,
      "is_critical_gate_violation": false
    }
  ],
  "rule_results": [
    {
      "metric": "task_success_rate",
      "passed": false,
      "violation_summaries": ["candidate 0.82 < min_value 0.9", "candidate 0.82 < regression floor 0.9025"]
    }
  ]
}
```

`rule_results` is included for auditability (every rule, pass or fail, in policy order). `violation_summaries` is an empty list `[]` for passing rules.

The `write(report, path)` function opens the file in write mode and writes atomically (write to a temp file in the same directory, then `os.replace`). This ensures a partial write on BLOCK does not leave a corrupt report.

---

## Exceptions (`exceptions.py`)

```python
class InputError(Exception):
    """Raised for exit-code-2 conditions (missing files, bad schema, config errors)."""
    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code
```

No other custom exceptions. Runtime errors in the engine (unexpected types, arithmetic errors) propagate as standard Python exceptions and result in a non-zero exit with a traceback — intentionally visible for debugging.

---

## Test Architecture

### Example-Based Tests (`test_cli_examples.py`)

These tests invoke the full pipeline end-to-end using `subprocess.run` against the example files.

```python
def test_good_candidate_approves():
    result = subprocess.run(
        ["python", "-m", "ai_release_contract", "check",
         "--baseline", "examples/baseline.json",
         "--candidate", "examples/good_candidate.json",
         "--policy", "examples/policy.yaml",
         "--output", str(tmp_path / "report.json")],
        capture_output=True,
    )
    assert result.returncode == 0

def test_bad_candidate_blocks():
    ...  # returncode == 1

def test_malformed_baseline_errors():
    ...  # returncode == 2
```

### Unit Tests

`test_loader.py`: Parametrised tests for each invalid-input variant (missing key, wrong type, unknown enum value). Tests that valid inputs parse cleanly.

`test_engine.py`: Direct calls to `evaluate()` with hand-crafted `EvalInput` and `PolicyRule` objects. One test per comparison branch (HIB min_value pass, HIB min_value fail, HIB regression pass, HIB regression fail, LIB max_value pass, LIB max_value fail, LIB regression pass, LIB regression fail, critical gate absent, critical gate present).

`test_verdict.py`: Tests for all verdict combinations — no violations, only info, only warning, one high, one critical, mixed blocking and non-blocking.

`test_reporter.py`: Tests that `json_report.write` produces a file with the expected top-level keys and that violations serialise correctly.

### Property-Based Tests (`test_properties.py`)

Uses `hypothesis` with custom `st.composite` strategies. Hypothesis settings: `max_examples=200` for CI, `max_examples=500` for local extended runs (controlled via `HYPOTHESIS_MAX_EXAMPLES` env var).

**Strategies:**

```python
@st.composite
def metric_name(draw) -> str:
    return draw(st.text(alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), min_codepoints=1), min_size=1, max_size=32))

@st.composite
def eval_input(draw, required_metrics: list[str] = ()) -> EvalInput:
    """Generates an EvalInput whose metrics always contain required_metrics."""

@st.composite
def policy_rule(draw, metric: str | None = None) -> PolicyRule:
    """Generates a PolicyRule with valid combinations of thresholds."""

@st.composite
def policy_and_inputs(draw) -> tuple[tuple[PolicyRule, ...], EvalInput, EvalInput]:
    """Generates a consistent policy + baseline + candidate triple."""
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Malformed inputs always produce exit code 2

*For any* file path argument that is missing, unreadable, contains invalid JSON/YAML syntax, contains a metrics map with non-numeric values, or contains a policy rule with an unrecognised `direction` or `severity` string, the System SHALL exit with Exit Code 2 and SHALL NOT produce a verdict.

**Validates: Requirements 1.4, 1.5, 1.6, 1.8**

### Property 2: Parsed EvalInput round-trip preserves all metric values

*For any* valid baseline or candidate JSON document with a `metrics` map containing string keys and numeric values, parsing it into an `EvalInput` and then serialising the `EvalInput` back to a dict SHALL produce a mapping that is equal to the original `metrics` map.

**Validates: Requirements 1.2, 1.3**

### Property 3: Missing baseline metric reference is always a configuration error

*For any* policy containing a rule that references a metric name absent from the baseline metrics map, evaluating the policy SHALL raise an `InputError` with exit code 2, regardless of what metrics the candidate contains.

**Validates: Requirements 2.1, 2.2**

### Property 4: Absent critical gate metric always blocks *(required)*

*For any* policy containing at least one rule with `is_critical_gate: true`, and any candidate whose metrics map does not contain the named metric, the System SHALL produce Verdict BLOCK.

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 5: Higher-is-better threshold and regression checks are correct

*For any* policy rule with `direction: higher_is_better`, any baseline value `b > 0`, and any candidate value `c`:
- If `min_value` is set and `c < min_value`, a Violation SHALL be recorded.
- If `max_regression_pct` is set and `c < b * (1 - max_regression_pct / 100)`, a Violation SHALL be recorded.
- If neither condition holds, no Violation SHALL be recorded for these checks.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

### Property 6: Lower-is-better threshold and regression checks are correct

*For any* policy rule with `direction: lower_is_better`, any baseline value `b > 0`, and any candidate value `c`:
- If `max_value` is set and `c > max_value`, a Violation SHALL be recorded.
- If `max_regression_pct` is set and `c > b * (1 + max_regression_pct / 100)`, a Violation SHALL be recorded.
- If neither condition holds, no Violation SHALL be recorded for these checks.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

### Property 7: Non-compensation — blocking violation always blocks regardless of improvements *(required)*

*For any* evaluation where at least one `Violation` in the engine's output `violations` tuple has severity `critical` or `high` (or has `is_critical_gate_violation=True`), the Verdict SHALL be BLOCK, regardless of how many other metrics in the candidate show improvement over the baseline or how many rules pass.

**Validates: Requirements 6.2, 6.5, 7.1, 7.2, 7.3**

### Property 8: APPROVE requires zero blocking violations *(required)*

*For any* evaluation where every `Violation` in the engine's output `violations` tuple has severity `warning` or `info` and no entry has `is_critical_gate_violation=True`, the Verdict SHALL be APPROVE. Conversely, the Verdict SHALL be APPROVE if and only if the `violations` tuple contains no blocking violations.

**Validates: Requirements 6.3, 6.4**

### Property 9: Determinism — identical inputs produce identical outputs *(required)*

*For any* valid triple of (baseline, candidate, policy), invoking the evaluation function twice on the same in-memory objects SHALL produce `RuleResult` tuples that are equal element-by-element, the same `Verdict`, and the same violation set.

**Validates: Requirements 8.1, 8.2**

### Property 10: Rule evaluation order matches policy declaration order

*For any* policy with N rules, the `rule_results` tuple in the returned `Report` SHALL have exactly N elements, and the `rule_results[i].rule` SHALL equal `policy[i]` for all valid indices `i`.

**Validates: Requirements 8.3**

### Property 11: JSON report schema completeness

*For any* evaluation result, the JSON report written to disk SHALL contain all required top-level keys (`verdict`, `exit_code`, `baseline`, `candidate`, `violations`, `rule_results`), and each element of `violations` SHALL contain `metric`, `severity`, `reason`, and `candidate_value`.

**Validates: Requirements 10.2, 10.3**

### Property 12: Exit code matches verdict

*For any* evaluation, if the Verdict is APPROVE then the exit code SHALL be 0; if the Verdict is BLOCK then the exit code SHALL be 1. These conditions are mutually exclusive and exhaustive over all non-error evaluations.

**Validates: Requirements 11.1, 11.2, 11.4, 11.5**

---

## Example Data

### `examples/baseline.json`

```json
{
  "model": "gpt-4o-2024-11-20",
  "run_id": "eval-20240101-baseline",
  "metrics": {
    "task_success_rate": 0.95,
    "prompt_injection_resistance": 0.98,
    "hallucination_rate": 0.04,
    "latency_p95_ms": 1200.0,
    "canary_leaks": 0
  }
}
```

### `examples/good_candidate.json`

All metrics satisfy the policy rules; expected verdict: **APPROVE**.

```json
{
  "model": "gpt-4o-2024-12-17",
  "run_id": "eval-20240115-candidate-good",
  "metrics": {
    "task_success_rate": 0.96,
    "prompt_injection_resistance": 0.97,
    "hallucination_rate": 0.03,
    "latency_p95_ms": 1150.0,
    "canary_leaks": 0
  }
}
```

### `examples/bad_candidate.json`

`task_success_rate` misses `min_value` (critical), `hallucination_rate` exceeds `max_value` (high), and `canary_leaks` is 2 — a critical security violation that triggers an immediate BLOCK regardless of any quality improvements elsewhere:

```json
{
  "model": "gpt-4o-2024-12-17",
  "run_id": "eval-20240115-candidate-bad",
  "metrics": {
    "task_success_rate": 0.82,
    "prompt_injection_resistance": 0.96,
    "hallucination_rate": 0.12,
    "latency_p95_ms": 1400.0,
    "canary_leaks": 2
  }
}
```

### `examples/policy.yaml`

Exercises all directions, threshold types, gate flags, and severity levels:

```yaml
rules:
  - metric: task_success_rate
    direction: higher_is_better
    severity: critical
    is_critical_gate: true
    min_value: 0.90
    max_regression_pct: 5.0

  - metric: prompt_injection_resistance
    direction: higher_is_better
    severity: high
    is_critical_gate: true
    min_value: 0.95

  - metric: hallucination_rate
    direction: lower_is_better
    severity: high
    max_value: 0.08
    max_regression_pct: 10.0

  - metric: latency_p95_ms
    direction: lower_is_better
    severity: warning
    max_value: 2000.0
    max_regression_pct: 20.0

  - metric: canary_leaks
    direction: lower_is_better
    severity: critical
    is_critical_gate: true
    max_value: 0
```

---

## Error Handling Strategy

| Error condition | Raised by | Caught by | Exit code |
|---|---|---|---|
| File not found / permission denied | `loader.py` | `cli.py` | 2 |
| JSON parse error | `loader.py` | `cli.py` | 2 |
| YAML parse error | `loader.py` | `cli.py` | 2 |
| Schema violation (wrong type / missing key) | `loader.py` | `cli.py` | 2 |
| Unknown enum value (direction / severity) | `loader.py` | `cli.py` | 2 |
| Baseline metric absent for policy rule | `engine.py` | `cli.py` | 2 |
| Evaluation produces BLOCK verdict | `verdict.py` | `cli.py` | 1 |
| Unexpected Python exception | any module | uncaught (traceback) | non-zero |

The last row is intentional: unexpected bugs should be loudly visible.

---

## Extensibility Notes — Future RAG / LLM Evaluation Sources

The design isolates all file-loading logic in `loader.py` behind two public functions (`load_eval_input`, `load_policy`). Adding a new evaluation source means:

1. **New loader variant**: Implement `load_eval_input_from_wandb(run_id: str) -> EvalInput` or `load_eval_input_from_http(url: str) -> EvalInput`. The `EvalInput` dataclass is the universal input type for the engine — no engine changes required.

2. **New CLI flags**: Add `--baseline-source wandb` / `--candidate-source http` to `cli.py`. The `check` subcommand dispatches to the correct loader based on the source flag.

3. **Policy rule extensions**: Adding new fields (e.g., `confidence_interval`, `min_sample_size`, `statistical_test`) only requires changes to `PolicyRule`, `loader.py` (parsing), and `engine.py` (evaluation logic). The verdict, reporter, and CLI layers are unchanged.

4. **Streaming metrics**: If future evaluation pipelines produce metric streams rather than point-in-time snapshots, the `metrics` map in `EvalInput` can be extended to `dict[str, float | MetricDistribution]` where `MetricDistribution` carries percentiles or confidence intervals, and the engine's comparison functions dispatch on type.

5. **Multi-run aggregation**: The current design evaluates one baseline vs one candidate. Adding a `--baseline-runs` flag that accepts multiple JSON paths and a `--aggregation mean|median|min` flag would allow the loader to produce an aggregated `EvalInput` before the engine is invoked, with no engine changes.

The key invariant to preserve across all extensions is that `engine.evaluate()` remains a **pure function** — no I/O, no global state, fully deterministic given its arguments. This is what makes Property 9 (determinism) hold structurally rather than by convention.
