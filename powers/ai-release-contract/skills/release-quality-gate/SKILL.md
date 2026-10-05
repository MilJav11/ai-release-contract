---
name: release-quality-gate
description: Evaluate whether a new AI or LLM system version is safe to release using deterministic baseline-vs-candidate metrics and an explicit release policy. Use when reviewing AI evaluation results, release readiness, regressions, quality gates, prompt-injection resistance, hallucination metrics, latency, or security canaries.
---

# AI Release Quality Gate

Use AI Release Contract as a deterministic release decision layer.

## Principles

- Treat evaluation metrics as inputs, not model-generated truth.
- Compare a candidate against a known-good baseline.
- Apply the declared policy exactly.
- Critical and high-severity violations block release.
- Warning and info violations do not block release.
- Improvements in one metric never compensate for a blocking violation.
- Missing required critical-gate metrics fail closed.
- Never invent missing evaluation metrics.
- Never override a BLOCK verdict to make a release look better.

## Workflow

1. Identify:
   - baseline evaluation JSON
   - candidate evaluation JSON
   - release policy YAML

2. Run:

   python -m ai_release_contract check --baseline <baseline.json> --candidate <candidate.json> --policy <policy.yaml> --output release_report.json

3. Interpret the exit code:
   - 0 = APPROVE
   - 1 = BLOCK
   - 2 = invalid input or configuration

4. Review `release_report.json`.

5. Explain:
   - final verdict
   - blocking violations
   - non-blocking warnings
   - regressions from baseline
   - critical-gate failures

## Safety contract

Do not silently change thresholds, severities, metric directions, or critical-gate flags.

If a policy appears incorrect, report the concern separately. Evaluate the supplied policy as written unless explicitly asked to modify it.

## Example

For this repository:

python -m ai_release_contract check --baseline examples/baseline.json --candidate examples/bad_candidate.json --policy examples/policy.yaml --output release_report.json

The bad candidate must BLOCK when critical/high release conditions fail, even when unrelated metrics improve.
