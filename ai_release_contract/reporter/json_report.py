"""Machine-readable JSON reporter."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ai_release_contract.models import Report, Violation


def _violation_to_dict(violation: Violation) -> dict[str, object]:
    return {
        "metric": violation.metric,
        "severity": violation.severity.value,
        "reason": violation.reason,
        "candidate_value": violation.candidate_value,
        "baseline_value": violation.baseline_value,
        "threshold": violation.threshold,
        "is_critical_gate_violation": violation.is_critical_gate_violation,
    }


def _report_to_dict(report: Report) -> dict[str, object]:
    return {
        "verdict": report.verdict.value,
        "exit_code": report.exit_code,
        "baseline": {
            "model": report.baseline.model,
            "run_id": report.baseline.run_id,
        },
        "candidate": {
            "model": report.candidate.model,
            "run_id": report.candidate.run_id,
        },
        "violations": [
            _violation_to_dict(violation)
            for violation in report.violations
        ],
        "rule_results": [
            {
                "metric": result.rule.metric,
                "passed": result.passed,
                "violation_summaries": [
                    violation.reason for violation in result.violations
                ],
            }
            for result in report.rule_results
        ],
    }


def write(report: Report, path: str | Path) -> None:
    """Write a stable JSON report atomically."""

    target = Path(path)
    data = _report_to_dict(report)
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"

    temp_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = handle.name
            handle.write(payload)

        os.replace(temp_path, target)

    except Exception:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        raise
