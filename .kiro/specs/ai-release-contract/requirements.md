# Requirements Document

## Introduction

AI Release Contract is a deterministic, local-first release policy gate for AI systems. It consumes evaluation metrics produced by external evaluation pipelines — one set from a known-good baseline AI system and one from a candidate AI system — along with a declarative release policy, and produces a deterministic APPROVE or BLOCK verdict. The tool targets AI QA and reliability engineering workflows where a new prompt, model, RAG configuration, agent configuration, or application version may silently regress critical quality dimensions. The system runs entirely offline, produces both human-readable console output and machine-readable JSON reports, and exits with a well-defined exit code so it can serve as a gate in automated CI/CD pipelines.

---

## Glossary

- **System**: The AI Release Contract command-line tool (`ai_release_contract`).
- **Baseline**: A JSON file containing evaluation metrics for a known-good AI system run.
- **Candidate**: A JSON file containing evaluation metrics for the AI system under consideration for release.
- **Policy**: A YAML file containing an ordered, flat list of Policy Rules that define the release contract.
- **Policy Rule**: A single declarative rule in the Policy that constrains one metric by name, direction, thresholds, severity, and gate status.
- **Metric**: A named numeric scalar value (float or integer) present in a Baseline or Candidate metrics map.
- **Direction**: A property of a Metric declared in a Policy Rule — either `higher_is_better` or `lower_is_better` — that determines which changes constitute a regression.
- **Absolute Threshold**: An optional bound declared in a Policy Rule — `min_value` (for `higher_is_better` metrics) or `max_value` (for `lower_is_better` metrics) — that the Candidate Metric value must satisfy regardless of the Baseline value.
- **Regression Threshold**: An optional `max_regression_pct` declared in a Policy Rule, expressing the maximum allowed percentage degradation of the Candidate Metric relative to the Baseline Metric value.
- **Severity**: A classification attached to a Policy Rule — one of `critical`, `high`, `warning`, or `info` — that determines whether a rule failure causes a BLOCK verdict.
- **Blocking Severity**: A Severity of `critical` or `high`. A Policy Rule violation at Blocking Severity causes the verdict to be BLOCK.
- **Non-Blocking Severity**: A Severity of `warning` or `info`. A Policy Rule violation at Non-Blocking Severity is reported but does not cause a BLOCK verdict.
- **Critical Gate**: A boolean property (`is_critical_gate: true`) on a Policy Rule indicating that the named Metric must be present in the Candidate for release to proceed.
- **Verdict**: The final release decision — either `APPROVE` or `BLOCK`.
- **Violation**: A record produced when a Candidate Metric fails a Policy Rule condition.
- **Report**: The machine-readable JSON document written by the System describing the verdict, all violations, and all rule evaluations.
- **Comparison Engine**: The internal subsystem that loads inputs, evaluates every Policy Rule against Baseline and Candidate Metrics, and accumulates Violations.
- **Exit Code**: The process exit status: `0` for APPROVE, `1` for BLOCK, `2` for invalid configuration or malformed input.

---

## Requirements

### Requirement 1 — Input Loading

**User Story:** As a release engineer, I want the System to load Baseline, Candidate, and Policy files from specified paths, so that every run operates on explicit, inspectable inputs.

#### Acceptance Criteria

1. WHEN the System is invoked with `--baseline <path>`, `--candidate <path>`, and `--policy <path>`, THE System SHALL load the Baseline JSON from `<path>`, the Candidate JSON from `<path>`, and the Policy YAML from `<path>` before performing any evaluation.

2. WHEN the Baseline JSON is loaded, THE System SHALL parse the top-level fields `model` (string), `run_id` (string), and `metrics` (object mapping string keys to numeric values).

3. WHEN the Candidate JSON is loaded, THE System SHALL parse the top-level fields `model` (string), `run_id` (string), and `metrics` (object mapping string keys to numeric values).

4. IF the Baseline JSON file is missing, unreadable, or does not conform to the required shape, THEN THE System SHALL exit with Exit Code 2 and emit a human-readable error message identifying the file and the specific parse or schema failure.

5. IF the Candidate JSON file is missing, unreadable, or does not conform to the required shape, THEN THE System SHALL exit with Exit Code 2 and emit a human-readable error message identifying the file and the specific parse or schema failure.

6. IF the Policy YAML file is missing, unreadable, or does not conform to the required shape, THEN THE System SHALL exit with Exit Code 2 and emit a human-readable error message identifying the file and the specific parse or schema failure.

7. WHEN the Policy YAML is loaded, THE System SHALL parse a top-level `rules` key containing a sequence of Policy Rule objects, each with at minimum the fields `metric` (string), `direction` (`higher_is_better` or `lower_is_better`), and `severity` (`critical`, `high`, `warning`, or `info`).

8. IF any Policy Rule contains an unrecognised `direction` value or an unrecognised `severity` value, THEN THE System SHALL exit with Exit Code 2 and identify the offending rule and field.

---

### Requirement 2 — Baseline Metric Availability

**User Story:** As a release engineer, I want the System to validate that every metric referenced by a Policy Rule exists in the Baseline, so that policy rules are always evaluated against a known reference point and configuration errors are surfaced immediately.

#### Acceptance Criteria

1. WHEN the Comparison Engine evaluates Policy Rules, THE System SHALL verify that every metric name referenced by a Policy Rule is present in the Baseline metrics map.

2. IF a Policy Rule references a metric name that is absent from the Baseline metrics map, THEN THE System SHALL exit with Exit Code 2 and emit a human-readable error message naming the missing Baseline metric and the offending Policy Rule.

---

### Requirement 3 — Critical Gate Enforcement

**User Story:** As a release engineer, I want the System to block releases when a required critical metric is absent from the Candidate, so that silent omissions in evaluation pipelines never bypass the release gate.

#### Acceptance Criteria

1. WHEN a Policy Rule has `is_critical_gate: true` and the named metric is absent from the Candidate metrics map, THE System SHALL record a Violation for that rule with the reason "required critical metric absent from candidate".

2. WHEN a Violation is recorded for an absent Critical Gate metric, THE System SHALL classify that Violation at Blocking Severity regardless of the `severity` field on the Policy Rule.

3. WHEN the Comparison Engine finishes evaluating all Policy Rules and at least one Critical Gate Violation exists, THE System SHALL set the Verdict to BLOCK.

---

### Requirement 4 — Metric Comparison: Higher-Is-Better

**User Story:** As a release engineer, I want the System to detect regressions in metrics where higher values indicate better quality (e.g., task success rate), so that improvements in other metrics cannot mask a degradation in these dimensions.

#### Acceptance Criteria

1. WHEN a Policy Rule specifies `direction: higher_is_better` and the Policy Rule includes a `min_value` threshold, THE System SHALL evaluate whether the Candidate Metric value is greater than or equal to `min_value`.

2. IF a Policy Rule specifies `direction: higher_is_better`, includes `min_value`, and the Candidate Metric value is less than `min_value`, THEN THE System SHALL record a Violation stating the Candidate value, the `min_value` threshold, and the direction.

3. WHEN a Policy Rule specifies `direction: higher_is_better` and the Policy Rule includes `max_regression_pct`, THE System SHALL compute the allowed floor as `baseline_value * (1 - max_regression_pct / 100)` and evaluate whether the Candidate Metric value is greater than or equal to that floor.

4. IF a Policy Rule specifies `direction: higher_is_better`, includes `max_regression_pct`, and the Candidate Metric value is less than the computed allowed floor, THEN THE System SHALL record a Violation stating the Candidate value, the Baseline value, the `max_regression_pct`, and the computed floor.

5. WHEN a Policy Rule specifies `direction: higher_is_better` and both `min_value` and `max_regression_pct` are present, and the Candidate Metric value violates both conditions, THE System SHALL record a Violation for each condition independently and preserve both Violations in the Report's violations list.

---

### Requirement 5 — Metric Comparison: Lower-Is-Better

**User Story:** As a release engineer, I want the System to detect regressions in metrics where lower values indicate better quality (e.g., hallucination rate, latency), so that increases in error-type metrics cannot be silently shipped.

#### Acceptance Criteria

1. WHEN a Policy Rule specifies `direction: lower_is_better` and the Policy Rule includes a `max_value` threshold, THE System SHALL evaluate whether the Candidate Metric value is less than or equal to `max_value`.

2. IF a Policy Rule specifies `direction: lower_is_better`, includes `max_value`, and the Candidate Metric value is greater than `max_value`, THEN THE System SHALL record a Violation stating the Candidate value, the `max_value` threshold, and the direction.

3. WHEN a Policy Rule specifies `direction: lower_is_better` and the Policy Rule includes `max_regression_pct`, THE System SHALL compute the allowed ceiling as `baseline_value * (1 + max_regression_pct / 100)` and evaluate whether the Candidate Metric value is less than or equal to that ceiling.

4. IF a Policy Rule specifies `direction: lower_is_better`, includes `max_regression_pct`, and the Candidate Metric value is greater than the computed allowed ceiling, THEN THE System SHALL record a Violation stating the Candidate value, the Baseline value, the `max_regression_pct`, and the computed ceiling.

5. WHEN a Policy Rule specifies `direction: lower_is_better` and both `max_value` and `max_regression_pct` are present, and the Candidate Metric value violates both conditions, THE System SHALL record a Violation for each condition independently and preserve both Violations in the Report's violations list.

---

### Requirement 6 — Severity Classification and Verdict

**User Story:** As a release engineer, I want BLOCK decisions to be triggered only by critical and high severity violations, so that informational and warning signals are surfaced without halting a release unnecessarily.

#### Acceptance Criteria

1. WHEN the Comparison Engine finishes evaluating all Policy Rules, THE System SHALL classify each Violation by the `severity` field of its Policy Rule.

2. WHEN at least one Violation has Blocking Severity (`critical` or `high`), THE System SHALL set the Verdict to BLOCK.

3. WHEN all Violations have Non-Blocking Severity (`warning` or `info`) and no Critical Gate Violations exist, THE System SHALL set the Verdict to APPROVE.

4. WHEN no Violations exist, THE System SHALL set the Verdict to APPROVE.

5. THE System SHALL evaluate every Policy Rule independently; a passing rule at any severity level SHALL NOT cancel, offset, or compensate for a Violation at Blocking Severity on a different rule.

6. WHEN the Verdict is APPROVE and Non-Blocking Violations exist, THE System SHALL include all Non-Blocking Violations in the Report and display them in the console output.

---

### Requirement 7 — Non-Compensation Invariant

**User Story:** As a release engineer, I want improvements in any metric to never override or cancel a critical or high severity failure, so that composite scoring cannot mask a regression in any single critical dimension.

#### Acceptance Criteria

1. THE System SHALL NOT compute any aggregate or composite score across metrics.

2. THE System SHALL NOT apply an improvement in one metric as a credit or offset against a Violation in any other metric.

3. WHEN a Violation at Blocking Severity exists, THE System SHALL set the Verdict to BLOCK regardless of how many other metrics show improvement over Baseline.

---

### Requirement 8 — Determinism

**User Story:** As a release engineer, I want the same inputs always to produce the same verdict, so that the gate behaves predictably and is safe to use in automated pipelines.

#### Acceptance Criteria

1. WHEN the System is invoked multiple times with identical Baseline, Candidate, and Policy inputs, THE System SHALL produce identical Verdicts, identical Violation sets, and identical Exit Codes on every invocation.

2. THE System SHALL NOT read from sources of non-determinism (clocks, random number generators, network, environment variables) during the evaluation phase.

3. THE System SHALL evaluate Policy Rules in the order they appear in the Policy YAML, and SHALL produce rule evaluation results in that order in the Report.

---

### Requirement 9 — Human-Readable Console Output

**User Story:** As a release engineer, I want clear, formatted console output that explains every blocking decision, so that I can immediately understand why a release was blocked without parsing the JSON report.

#### Acceptance Criteria

1. WHEN the System completes evaluation, THE System SHALL print to standard output a summary including: the Verdict (`APPROVE` or `BLOCK`), the Baseline `model` and `run_id`, the Candidate `model` and `run_id`, and the total count of Violations by severity.

2. WHEN the Verdict is BLOCK, THE System SHALL print each Blocking Violation to standard output, including the metric name, the Candidate value, the threshold or baseline comparison that was violated, the severity, and a human-readable reason.

3. WHEN Non-Blocking Violations exist, THE System SHALL print each Non-Blocking Violation to standard output, labelled with its severity, so engineers are aware of degraded but non-blocking dimensions.

4. THE System SHALL use the Rich library to format console output with colour-coded severity levels and a clearly visible APPROVE or BLOCK banner.

---

### Requirement 10 — Machine-Readable JSON Report

**User Story:** As a release engineer, I want a structured JSON report written to disk, so that downstream CI/CD tools and dashboards can consume the verdict and violation details programmatically.

#### Acceptance Criteria

1. WHEN the System completes evaluation, THE System SHALL write a JSON Report to the path specified by `--output` if provided, or to `release_report.json` in the current working directory if `--output` is not provided.

2. THE System SHALL include in the JSON Report: the Verdict string, the Exit Code integer, the Baseline metadata (`model`, `run_id`), the Candidate metadata (`model`, `run_id`), and a `violations` array.

3. WHEN the `violations` array is populated, THE System SHALL include every Violation produced across all rules — including multiple Violations from a single rule when both an absolute threshold and a regression threshold are violated. For each Violation, the report SHALL include: the `metric` name, the `severity`, the `reason` string, the `candidate_value`, the `baseline_value` (if applicable), and the `threshold` (if applicable).

4. WHEN the Verdict is APPROVE and no Violations exist, THE System SHALL write a Report with an empty `violations` array.

5. THE System SHALL write the JSON Report before exiting, including in cases where the Verdict is BLOCK.

---

### Requirement 11 — Exit Codes

**User Story:** As a CI/CD pipeline author, I want well-defined exit codes, so that I can integrate the gate as a pipeline step without parsing output.

#### Acceptance Criteria

1. WHEN the Verdict is APPROVE, THE System SHALL exit with Exit Code 0.

2. WHEN the Verdict is BLOCK, THE System SHALL exit with Exit Code 1.

3. IF the System encounters invalid configuration, a missing required file, or malformed input prior to evaluation, THEN THE System SHALL exit with Exit Code 2.

4. THE System SHALL NOT exit with Exit Code 0 when the Verdict is BLOCK.

5. THE System SHALL NOT exit with Exit Code 1 when the Verdict is APPROVE.

---

### Requirement 12 — Example Data

**User Story:** As a new user, I want realistic example input files shipped with the tool, so that I can run the tool immediately and understand the expected input format.

#### Acceptance Criteria

1. THE System SHALL include an example Baseline JSON file at `examples/baseline.json` containing at minimum the metrics: `task_success_rate`, `prompt_injection_resistance`, `hallucination_rate`, `latency_p95_ms`, and `canary_leaks`.

2. THE System SHALL include an example good-candidate JSON file at `examples/good_candidate.json` where all metrics satisfy the example Policy Rules and the expected Verdict is APPROVE.

3. THE System SHALL include an example bad-candidate JSON file at `examples/bad_candidate.json` where at least one metric violates a Blocking Severity rule and the expected Verdict is BLOCK. The bad candidate SHALL set `canary_leaks` to `2`, demonstrating that a release may be BLOCKED due to a critical security violation even if some quality metrics improved relative to Baseline.

4. THE System SHALL include an example Policy YAML file at `examples/policy.yaml` that exercises: `higher_is_better` direction, `lower_is_better` direction, `min_value`, `max_value`, `max_regression_pct`, `is_critical_gate: true`, and all four severity levels (`critical`, `high`, `warning`, `info`). The `canary_leaks` rule in this Policy SHALL use `severity: critical`, `is_critical_gate: true`, and `max_value: 0`.

---

### Requirement 13 — Automated Tests

**User Story:** As a contributor, I want an automated test suite covering both example-based and property-based cases, so that the correctness invariants of the tool are continuously verified.

#### Acceptance Criteria

1. THE System SHALL include a pytest test suite that verifies: the good-candidate example produces Exit Code 0, the bad-candidate example produces Exit Code 1, and a malformed input file produces Exit Code 2.

2. THE System SHALL include Hypothesis-based property tests that verify the following universal invariants:
   a. WHEN a required critical gate metric is absent from any Candidate, THE System SHALL produce Verdict BLOCK.
   b. WHEN any Candidate Metric produces a Violation with severity `critical` or `high` (or is a critical gate violation), THE System SHALL produce Verdict BLOCK regardless of any improvements in other metrics.
   c. WHEN all blocking contract conditions are satisfied across all rules, THE System SHALL produce Verdict APPROVE.
   d. WHEN the System is invoked twice with identical Baseline, Candidate, and Policy inputs, THE System SHALL produce identical Verdicts and identical Violation sets.
   These four property tests are required and must not be marked optional.

3. WHEN the test suite is run with `pytest`, THE System SHALL produce a passing test run against the example files and all property tests.

---

### Requirement 14 — Input Validation Hardening

**User Story:** As a release engineer, I want the System to reject malformed or semantically incorrect numeric inputs and policy configurations, so that evaluation never silently proceeds on invalid data.

#### Acceptance Criteria

1. IF a metric value in the Baseline or Candidate metrics map is a boolean (Python `bool`), THEN THE System SHALL reject it with Exit Code 2 and identify the metric name and value.

2. IF a metric value in the Baseline or Candidate metrics map is non-finite (`NaN`, `+Infinity`, or `-Infinity`), THEN THE System SHALL reject it with Exit Code 2.

3. IF a Policy Rule's threshold field (`min_value` or `max_value`) contains a non-finite value, THEN THE System SHALL reject it with Exit Code 2.

4. IF a Policy Rule's `max_regression_pct` is negative or non-finite, THEN THE System SHALL reject it with Exit Code 2.

5. IF a Policy Rule with `direction: higher_is_better` contains a `max_value` field, THEN THE System SHALL reject it with Exit Code 2, as `max_value` is semantically incorrect for a higher-is-better metric.

6. IF a Policy Rule with `direction: lower_is_better` contains a `min_value` field, THEN THE System SHALL reject it with Exit Code 2, as `min_value` is semantically incorrect for a lower-is-better metric.
