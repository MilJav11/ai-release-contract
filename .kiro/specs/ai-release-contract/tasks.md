# Implementation Plan: AI Release Contract

## Overview

Implement a deterministic, offline CLI tool in Python 3.12 that evaluates AI model release metrics
against a declarative policy and emits an APPROVE/BLOCK verdict via exit code, Rich console output,
and a JSON report. The implementation follows the layered architecture defined in the design: models
→ exceptions → loader → engine → verdict → reporter → CLI. Each task builds on the previous and
ends with a fully wired, runnable tool.

---

## Tasks

- [ ] 1. Initialise project structure and packaging
  - Create the `ai_release_contract/` package directory with `__init__.py` and `__main__.py`
  - Create the `ai_release_contract/reporter/` sub-package with `__init__.py`
  - Create `pyproject.toml` with project metadata, Python 3.12 requirement, and dependencies:
    PyYAML, Rich, pytest, and hypothesis (pinned to latest stable)
  - Create `README.md` with a one-paragraph description and a quick-start `python -m ai_release_contract check` example
  - Create `tests/` directory with an empty `conftest.py`
  - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [ ] 2. Implement data models
  - [ ] 2.1 Write `ai_release_contract/models.py`
    - Define `Direction`, `Severity`, `Verdict` enums with `str, Enum` base
    - Define `BLOCKING_SEVERITIES: frozenset[Severity]`
    - Define frozen dataclasses: `PolicyRule`, `EvalInput`, `Violation`, `RuleResult`, `Report`
    - Define `RuleResult` with `violations: tuple[Violation, ...]` (empty tuple when passed, one or more Violations when failed) — not a single nullable `violation` field
    - Add `EvalInput.__post_init__` to store `metrics` as `types.MappingProxyType`
    - _Requirements: 1.2, 1.3, 1.7, 6.1_

  - [ ] 2.2 Write `ai_release_contract/exceptions.py`
    - Define `InputError(Exception)` with `message: str` and `exit_code: int = 2`
    - _Requirements: 1.4, 1.5, 1.6, 11.3_

- [ ] 3. Implement the loader
  - [ ] 3.1 Write `ai_release_contract/loader.py` — `load_eval_input(path, role) -> EvalInput`
    - Open file; on `OSError` raise `InputError` naming the file and role
    - Parse with `json.load()`; on `JSONDecodeError` raise `InputError`
    - Validate top-level keys `model` (str), `run_id` (str), `metrics` (dict); raise `InputError` per missing/wrong-type field
    - Validate all metric values are `int` or `float`; raise `InputError` naming the offending key and value
    - Reject boolean metric values: check `isinstance(value, bool)` BEFORE `isinstance(value, (int, float))` (since `bool` subclasses `int` in Python); raise `InputError` naming the metric key and value
    - Reject non-finite metric values: check `math.isfinite(value)` after confirming numeric; raise `InputError` naming the metric key
    - Add `import math` to the module
    - Return `EvalInput(model, run_id, metrics)`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ] 3.2 Write `ai_release_contract/loader.py` — `load_policy(path) -> tuple[PolicyRule, ...]`
    - Open file; on `OSError` raise `InputError`
    - Parse with `yaml.safe_load()`; on `YAMLError` raise `InputError`
    - Validate top-level `rules` key is a list; raise `InputError` if absent or wrong type
    - For each rule item (0-based index), validate and parse: `metric` (non-empty str), `direction` (→ `Direction` enum), `severity` (→ `Severity` enum), optional numeric fields `min_value`, `max_value`, `max_regression_pct`, optional bool `is_critical_gate` (default `False`)
    - After parsing `min_value`/`max_value`: check `math.isfinite(value)`; raise `InputError` if not finite, naming field and rule index
    - After parsing `max_regression_pct`: check `math.isfinite(value) and value >= 0`; raise `InputError` if either fails, naming field and rule index
    - Direction-threshold consistency: if `direction == higher_is_better` and `max_value` is present → `InputError`; if `direction == lower_is_better` and `min_value` is present → `InputError`, naming the conflicting field and rule index
    - Raise `InputError` with rule index and field name on any schema violation or unknown enum value
    - Return `tuple[PolicyRule, ...]` in declaration order
    - _Requirements: 1.6, 1.7, 1.8, 2.1_

  - [ ]* 3.3 Write unit tests for `loader.py` in `tests/test_loader.py`
    - Parametrised tests: missing file, non-JSON content, missing top-level key (`model`, `run_id`, `metrics`), non-numeric metric value, non-string metric key
    - Tests for `load_policy`: missing file, invalid YAML, missing `rules` key, unknown `direction`, unknown `severity`, valid full policy round-trip
    - Verify error messages include the file path, field name, and (for rules) the rule index
    - Additional parametrised test cases:
      - Boolean metric value in baseline → exit code 2
      - Boolean metric value in candidate → exit code 2
      - Non-finite metric value (e.g., `float('nan')`, `float('inf')`) → exit code 2
      - Non-finite threshold value in policy rule → exit code 2
      - Negative `max_regression_pct` → exit code 2
      - `max_value` present on a `higher_is_better` rule → exit code 2
      - `min_value` present on a `lower_is_better` rule → exit code 2
    - _Requirements: 1.4, 1.5, 1.6, 1.7, 1.8, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

- [ ] 4. Implement the comparison engine
  - [ ] 4.1 Write `ai_release_contract/engine.py` — `evaluate(baseline, candidate, rules) -> tuple[RuleResult, ...]`
    - Step 1: check every rule's metric is in `baseline.metrics`; raise `InputError(exit_code=2)` listing the missing metric and rule
    - Step 2: iterate rules in order; call `_evaluate_rule(rule, baseline, candidate)` per rule
    - In `_evaluate_rule`:
      - Critical gate absent check (produces `is_critical_gate_violation=True`)
      - Non-critical absent metric → pass (no violation)
      - `higher_is_better`: check `min_value` threshold, check `max_regression_pct` floor
      - `lower_is_better`: check `max_value` threshold, check `max_regression_pct` ceiling
      - Collect ALL violations per rule into `violations_for_rule: list[Violation]`
      - Return `RuleResult(rule=rule, passed=False, violations=tuple(violations_for_rule))` for failing rules
      - Return `RuleResult(rule=rule, passed=True, violations=())` for passing rules
    - Return `tuple(results)` preserving declaration order
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4_

  - [ ]* 4.2 Write property test for engine — Property 3 (missing baseline metric is always exit-2)
    - **Property 3: Missing baseline metric reference is always a configuration error**
    - **Validates: Requirements 2.1, 2.2**
    - Generate a policy with at least one rule whose metric is absent from the baseline; assert `InputError` is raised

  - [ ] 4.3 Write property test for engine — Property 4 (absent critical gate always blocks)
    - **Property 4: Absent critical gate metric always blocks**
    - **Validates: Requirements 3.1, 3.2, 3.3**
    - Generate a policy with `is_critical_gate=True`; omit the metric from candidate; assert verdict is BLOCK

  - [ ]* 4.4 Write property test for engine — Property 5 (higher-is-better checks are correct)
    - **Property 5: Higher-is-better threshold and regression checks are correct**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    - For random `b > 0`, `c`, `min_value`, `max_regression_pct`, assert violation presence/absence matches the comparison formula

  - [ ]* 4.5 Write property test for engine — Property 6 (lower-is-better checks are correct)
    - **Property 6: Lower-is-better threshold and regression checks are correct**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    - For random `b > 0`, `c`, `max_value`, `max_regression_pct`, assert violation presence/absence matches the comparison formula

  - [ ]* 4.6 Write unit tests for `engine.py` in `tests/test_engine.py`
    - One test per comparison branch: HIB min_value pass/fail, HIB regression pass/fail, LIB max_value pass/fail, LIB regression pass/fail
    - Tests for critical gate absent and present (both directions)
    - Test for non-critical absent metric returning a passing `RuleResult`
    - Test that rule order in results matches input rule order (Property 10 example)
    - Test that when a rule fails BOTH its absolute threshold AND its regression threshold simultaneously, the returned `RuleResult.violations` tuple contains TWO `Violation` objects
    - _Requirements: 3.1, 3.2, 4.1–4.4, 5.1–5.4, 8.3_

- [ ] 5. Checkpoint — Ensure all tests pass so far
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement verdict determination
  - [ ] 6.1 Write `ai_release_contract/verdict.py` — `determine_verdict(rule_results) -> tuple[Verdict, tuple[Violation, ...]]`
    - Collect all violations by iterating `result.violations` for each result (a tuple, never None); use `all_violations.extend(result.violations)` pattern
    - Set verdict to BLOCK if any violation has `is_critical_gate_violation=True` or `severity in BLOCKING_SEVERITIES`; otherwise APPROVE
    - Return `(verdict, tuple(all_violations))`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3_

  - [ ] 6.2 Write property test for verdict — Property 7 (blocking violation always blocks regardless of improvements)
    - **Property 7: Non-compensation — blocking violation always blocks regardless of improvements**
    - **Validates: Requirements 6.2, 6.5, 7.1, 7.2, 7.3**
    - Generate rule results with at least one blocking violation; assert verdict is BLOCK

  - [ ] 6.3 Write property test for verdict — Property 8 (APPROVE iff zero blocking violations)
    - **Property 8: APPROVE requires zero blocking violations**
    - **Validates: Requirements 6.3, 6.4**
    - Generate rule results with only warning/info violations; assert verdict is APPROVE; test biconditional

  - [ ]* 6.4 Write unit tests for `verdict.py` in `tests/test_verdict.py`
    - No violations → APPROVE; only info → APPROVE; only warning → APPROVE
    - One high → BLOCK; one critical → BLOCK; critical gate violation → BLOCK
    - Mixed blocking + non-blocking → BLOCK; empty rule_results → APPROVE
    - _Requirements: 6.2, 6.3, 6.4, 7.3_

- [ ] 7. Implement reporters
  - [ ] 7.1 Write `ai_release_contract/reporter/json_report.py` — `write(report, path) -> None`
    - Serialise `Report` to a dict: top-level keys `verdict`, `exit_code`, `baseline`, `candidate`, `violations`, `rule_results`
    - Each violation includes: `metric`, `severity`, `reason`, `candidate_value`, `baseline_value`, `threshold`, `is_critical_gate_violation`
    - Each rule result entry uses `violation_summaries` (list of reason strings, `[]` for passing rules), not a single nullable `violation_summary` field
    - Use `json.dumps(data, indent=2, sort_keys=True)` for stable output
    - Write atomically: write to a temp file in the same directory, then `os.replace(tmp, path)`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ] 7.2 Write `ai_release_contract/reporter/console.py` — `render(report) -> None` and `print_error(msg) -> None`
    - Use `rich.console.Console`, `rich.table.Table`, `rich.panel.Panel`, `rich.text.Text`
    - Render verdict banner: bold green on dark_green for APPROVE, bold white on red for BLOCK
    - Render run summary: baseline model/run_id, candidate model/run_id, rules evaluated, violation counts by severity
    - Render blocking violations table (metric, candidate value, threshold, reason) — only when verdict is BLOCK
    - Render non-blocking violations table (same columns, muted colours) — only when non-blocking violations exist
    - Apply severity colour map: critical→`bold red`, high→`red`, warning→`yellow`, info→`cyan`
    - `print_error` prints an error-styled message to stderr
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 7.3 Write unit tests for reporters in `tests/test_reporter.py`
    - `json_report.write`: verify output file has all required top-level keys, verify `violations` array serialises each field correctly, verify empty violations produces empty array, verify `sort_keys=True` produces stable ordering
    - Verify that when a rule produces two violations, both reason strings appear in `violation_summaries` for that rule's entry
    - `console.py`: smoke-test `render` with an APPROVE report and a BLOCK report (no exceptions); verify `print_error` writes to stderr
    - _Requirements: 10.2, 10.3, 10.4, 10.5_

  - [ ]* 7.4 Write property test for reporters — Property 11 (JSON report schema completeness)
    - **Property 11: JSON report schema completeness**
    - **Validates: Requirements 10.2, 10.3**
    - Generate arbitrary valid `Report` objects; assert all required top-level keys and per-violation keys are present in the written JSON

- [ ] 8. Implement the CLI entry point
  - [ ] 8.1 Write `ai_release_contract/cli.py` — `main() -> None`
    - Set up `argparse` with `check` subcommand and `--baseline`, `--candidate`, `--policy`, `--output` arguments
    - Wrap `load_eval_input` and `load_policy` calls in `try/except InputError`; on error call `console.print_error` and `sys.exit(2)`
    - Wrap `evaluate` call in `try/except InputError` (baseline availability error); on error `sys.exit(2)`
    - Call `determine_verdict`, build `Report`, call `console_reporter.render(report)` and `json_reporter.write(report, path=args.output)`
    - Call `sys.exit(0 if verdict == Verdict.APPROVE else 1)`
    - _Requirements: 1.1, 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ] 8.2 Update `ai_release_contract/__main__.py`
    - Single import and call: `from ai_release_contract.cli import main; main()`
    - _Requirements: 1.1_

- [ ] 9. Create example data files
  - [ ] 9.1 Create `examples/baseline.json`
    - Include metrics: `task_success_rate`, `prompt_injection_resistance`, `hallucination_rate`, `latency_p95_ms`, `canary_leaks` with values matching the design specification
    - _Requirements: 12.1_

  - [ ] 9.2 Create `examples/good_candidate.json`
    - All metrics satisfy the example policy rules; expected verdict APPROVE
    - _Requirements: 12.2_

  - [ ] 9.3 Create `examples/bad_candidate.json`
    - Set `canary_leaks` to `2`
    - `task_success_rate` misses `min_value` (critical), `hallucination_rate` exceeds `max_value` (high); expected verdict BLOCK
    - Note: the bad candidate demonstrates that a release is BLOCKED for a critical security violation (`canary_leaks: 2`) even if some quality metrics improved relative to Baseline
    - _Requirements: 12.3_

  - [ ] 9.4 Create `examples/policy.yaml`
    - Exercises `higher_is_better`, `lower_is_better`, `min_value`, `max_value`, `max_regression_pct`, `is_critical_gate: true`, and all four severity levels, matching the values in the design specification
    - `canary_leaks` rule uses `severity: critical`, `is_critical_gate: true`, `max_value: 0` (previously info severity; it is now a critical blocking security contract)
    - _Requirements: 12.4_

- [ ] 10. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Write cross-cutting property and end-to-end tests
  - [ ] 11.1 Add Hypothesis strategies and profiles to `tests/conftest.py`
    - Define `metric_name`, `eval_input`, `policy_rule`, and `policy_and_inputs` composite strategies
    - Configure Hypothesis settings: `max_examples=200` for CI, `max_examples=500` when `HYPOTHESIS_MAX_EXAMPLES` env var is set
    - These strategies are required infrastructure for all property-based tests in the suite
    - _Requirements: 13.2_

  - [ ]* 11.2 Write property test — Property 1 (malformed inputs always exit 2)
    - **Property 1: Malformed inputs always produce exit code 2**
    - **Validates: Requirements 1.4, 1.5, 1.6, 1.8**
    - Generate syntactically invalid or schema-invalid inputs; assert `InputError` is raised (or subprocess exits 2)

  - [ ]* 11.3 Write property test — Property 2 (EvalInput round-trip preserves metric values)
    - **Property 2: Parsed EvalInput round-trip preserves all metric values**
    - **Validates: Requirements 1.2, 1.3**
    - Serialise an `EvalInput` back to a dict and compare with the original metrics map

  - [ ] 11.4 Write property test — Property 9 (determinism)
    - **Property 9: Determinism — identical inputs produce identical outputs**
    - **Validates: Requirements 8.1, 8.2**
    - Call `evaluate` twice on the same objects; assert `RuleResult` tuples are equal element-by-element

  - [ ]* 11.5 Write property test — Property 10 (rule evaluation order matches declaration order)
    - **Property 10: Rule evaluation order matches policy declaration order**
    - **Validates: Requirements 8.3**
    - For a policy of N rules, assert `len(rule_results) == N` and `rule_results[i].rule == rules[i]` for all `i`

  - [ ]* 11.6 Write property test — Property 12 (exit code matches verdict)
    - **Property 12: Exit code matches verdict**
    - **Validates: Requirements 11.1, 11.2, 11.4, 11.5**
    - Generate valid inputs; assert `exit_code == 0` iff `verdict == APPROVE`, `exit_code == 1` iff `verdict == BLOCK`

  - [ ] 11.7 Write end-to-end example-file tests in `tests/test_cli_examples.py`
    - `test_good_candidate_approves`: invoke CLI via `subprocess.run`; assert `returncode == 0`
    - `test_bad_candidate_blocks`: assert `returncode == 1`
    - `test_malformed_baseline_errors`: pass a malformed JSON file; assert `returncode == 2`
    - `test_missing_policy_errors`: pass a non-existent policy path; assert `returncode == 2`
    - Verify the JSON report file is written to the `--output` path in all non-error cases
    - _Requirements: 13.1, 13.3_

- [ ] 12. Final checkpoint — Ensure all tests pass
  - Run `pytest tests/` and verify all tests pass. Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; this applies only to the additional/supporting property tests (Properties 1, 2, 3, 5, 6, 10, 11, 12) — Properties 4, 7, 8, and 9 are required and their tasks carry no `*` marker
- Each task references specific requirements for traceability
- Checkpoints at Tasks 5, 10, and 12 provide incremental validation gates
- Property tests validate universal correctness invariants; unit tests validate specific examples and edge cases
- All 12 correctness properties from the design are covered by property test sub-tasks (Properties 1–12)
- The engine's `_evaluate_rule` function accumulates ALL violations per rule into `violations_for_rule: list[Violation]`; `RuleResult.violations` is a tuple of all of them — test_engine.py covers the dual-violation case
- Atomic write via `os.replace` in `json_report.py` ensures a partial write on BLOCK never leaves a corrupt report on disk

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "2.2"] },
    { "id": 1, "tasks": ["3.1", "3.2"] },
    { "id": 2, "tasks": ["3.3", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "4.4", "4.5", "4.6", "6.1", "9.1", "9.2", "9.3", "9.4"] },
    { "id": 4, "tasks": ["6.2", "6.3", "6.4", "7.1", "7.2"] },
    { "id": 5, "tasks": ["7.3", "7.4", "8.1"] },
    { "id": 6, "tasks": ["8.2", "11.1"] },
    { "id": 7, "tasks": ["11.2", "11.3", "11.4", "11.5", "11.6", "11.7"] }
  ]
}
```
