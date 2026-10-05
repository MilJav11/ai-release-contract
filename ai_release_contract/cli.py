"""Command-line entry point for AI Release Contract."""

from __future__ import annotations

import argparse
import sys

from ai_release_contract.engine import evaluate
from ai_release_contract.exceptions import InputError
from ai_release_contract.loader import load_eval_input, load_policy
from ai_release_contract.models import Report, Verdict
from ai_release_contract.reporter import console as console_reporter
from ai_release_contract.reporter import json_report as json_reporter
from ai_release_contract.verdict import determine_verdict


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ai_release_contract",
        description="Deterministic AI release policy gate",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    check = subparsers.add_parser(
        "check",
        help="Evaluate a candidate against a baseline and release policy",
    )

    check.add_argument("--baseline", required=True)
    check.add_argument("--candidate", required=True)
    check.add_argument("--policy", required=True)
    check.add_argument("--output", default="release_report.json")

    return parser


def main() -> None:
    args = _build_parser().parse_args()

    try:
        baseline = load_eval_input(args.baseline, "baseline")
        candidate = load_eval_input(args.candidate, "candidate")
        rules = load_policy(args.policy)

        rule_results = evaluate(
            baseline,
            candidate,
            rules,
        )

    except InputError as exc:
        console_reporter.print_error(str(exc))
        sys.exit(exc.exit_code)

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
    json_reporter.write(report, args.output)

    sys.exit(exit_code)
