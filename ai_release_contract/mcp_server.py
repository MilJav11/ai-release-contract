"""MCP server exposing AI Release Contract capabilities."""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from ai_release_contract.engine import evaluate
from ai_release_contract.loader import load_eval_input, load_policy
from ai_release_contract.models import BLOCKING_SEVERITIES, Violation
from ai_release_contract.verdict import determine_verdict


mcp = MCPServer("ai-release-contract")


def _violation_to_dict(violation: Violation) -> dict[str, Any]:
    return {
        "metric": violation.metric,
        "severity": violation.severity.value,
        "reason": violation.reason,
        "candidate_value": violation.candidate_value,
        "baseline_value": violation.baseline_value,
        "threshold": violation.threshold,
        "is_critical_gate_violation": violation.is_critical_gate_violation,
    }


def _is_blocking(violation: Violation) -> bool:
    return (
        violation.is_critical_gate_violation
        or violation.severity in BLOCKING_SEVERITIES
    )


@mcp.tool()
def check_release(
    baseline_path: str,
    candidate_path: str,
    policy_path: str,
) -> dict[str, Any]:
    """Evaluate an AI candidate against a baseline and release policy."""

    baseline = load_eval_input(baseline_path, "baseline")
    candidate = load_eval_input(candidate_path, "candidate")
    rules = load_policy(policy_path)

    rule_results = evaluate(baseline, candidate, rules)
    verdict, violations = determine_verdict(rule_results)

    exit_code = 0 if verdict.value == "APPROVE" else 1

    return {
        "verdict": verdict.value,
        "exit_code": exit_code,
        "baseline": {
            "model": baseline.model,
            "run_id": baseline.run_id,
        },
        "candidate": {
            "model": candidate.model,
            "run_id": candidate.run_id,
        },
        "violations": [
            _violation_to_dict(violation)
            for violation in violations
        ],
    }


@mcp.tool()
def compare_metrics(
    baseline_path: str,
    candidate_path: str,
) -> dict[str, Any]:
    """Compare raw baseline and candidate metrics without applying policy."""

    baseline = load_eval_input(baseline_path, "baseline")
    candidate = load_eval_input(candidate_path, "candidate")

    metric_names = sorted(
        set(baseline.metrics) | set(candidate.metrics)
    )

    comparisons: list[dict[str, Any]] = []

    for metric in metric_names:
        baseline_value = baseline.metrics.get(metric)
        candidate_value = candidate.metrics.get(metric)

        delta = None
        if baseline_value is not None and candidate_value is not None:
            delta = candidate_value - baseline_value

        comparisons.append(
            {
                "metric": metric,
                "baseline_value": baseline_value,
                "candidate_value": candidate_value,
                "delta": delta,
                "missing_from_baseline": baseline_value is None,
                "missing_from_candidate": candidate_value is None,
            }
        )

    return {
        "baseline_model": baseline.model,
        "candidate_model": candidate.model,
        "metrics": comparisons,
    }


@mcp.tool()
def explain_blockers(
    baseline_path: str,
    candidate_path: str,
    policy_path: str,
) -> dict[str, Any]:
    """Return only release-blocking violations for an AI candidate."""

    baseline = load_eval_input(baseline_path, "baseline")
    candidate = load_eval_input(candidate_path, "candidate")
    rules = load_policy(policy_path)

    rule_results = evaluate(baseline, candidate, rules)
    verdict, violations = determine_verdict(rule_results)

    blockers = tuple(
        violation
        for violation in violations
        if _is_blocking(violation)
    )

    return {
        "verdict": verdict.value,
        "blocking_count": len(blockers),
        "blocking_metrics": sorted(
            {violation.metric for violation in blockers}
        ),
        "blockers": [
            _violation_to_dict(violation)
            for violation in blockers
        ],
    }


if __name__ == "__main__":
    mcp.run()
