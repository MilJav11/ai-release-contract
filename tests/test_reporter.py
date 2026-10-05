from __future__ import annotations

import json

from ai_release_contract.models import (
    Direction,
    EvalInput,
    PolicyRule,
    Report,
    RuleResult,
    Severity,
    Verdict,
    Violation,
)
from ai_release_contract.reporter.json_report import write


def test_json_report_contains_complete_schema(tmp_path):
    rule = PolicyRule(
        metric="quality",
        direction=Direction.HIGHER_IS_BETTER,
        severity=Severity.HIGH,
    )

    first = Violation(
        metric="quality",
        severity=Severity.HIGH,
        reason="absolute threshold failed",
        candidate_value=0.5,
        baseline_value=0.9,
        threshold=0.8,
    )
    second = Violation(
        metric="quality",
        severity=Severity.HIGH,
        reason="regression threshold failed",
        candidate_value=0.5,
        baseline_value=0.9,
        threshold=0.85,
    )

    result = RuleResult(
        rule=rule,
        passed=False,
        violations=(first, second),
    )

    report = Report(
        verdict=Verdict.BLOCK,
        exit_code=1,
        baseline=EvalInput(
            model="baseline",
            run_id="b-1",
            metrics={"quality": 0.9},
        ),
        candidate=EvalInput(
            model="candidate",
            run_id="c-1",
            metrics={"quality": 0.5},
        ),
        violations=(first, second),
        rule_results=(result,),
    )

    output = tmp_path / "report.json"
    write(report, output)

    data = json.loads(output.read_text(encoding="utf-8"))

    assert set(data) == {
        "baseline",
        "candidate",
        "exit_code",
        "rule_results",
        "verdict",
        "violations",
    }
    assert data["verdict"] == "BLOCK"
    assert data["exit_code"] == 1
    assert len(data["violations"]) == 2
    assert data["rule_results"][0]["violation_summaries"] == [
        "absolute threshold failed",
        "regression threshold failed",
    ]
