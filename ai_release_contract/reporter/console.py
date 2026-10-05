"""Rich console reporter."""

from __future__ import annotations

from collections import Counter

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ai_release_contract.models import (
    BLOCKING_SEVERITIES,
    Report,
    Severity,
    Verdict,
    Violation,
)


_console = Console()
_error_console = Console(stderr=True)

_SEVERITY_STYLES = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.WARNING: "yellow",
    Severity.INFO: "cyan",
}


def _is_blocking(violation: Violation) -> bool:
    return (
        violation.is_critical_gate_violation
        or violation.severity in BLOCKING_SEVERITIES
    )


def _format_value(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:g}"


def _render_violation_table(
    title: str,
    violations: tuple[Violation, ...],
    *,
    muted: bool = False,
) -> None:
    table = Table(title=title)

    table.add_column("Severity")
    table.add_column("Metric")
    table.add_column("Candidate")
    table.add_column("Threshold")
    table.add_column("Reason")

    for violation in violations:
        style = _SEVERITY_STYLES[violation.severity]
        if muted:
            style = f"dim {style}"

        table.add_row(
            Text(violation.severity.value, style=style),
            violation.metric,
            _format_value(violation.candidate_value),
            _format_value(violation.threshold),
            violation.reason,
        )

    _console.print(table)


def render(report: Report) -> None:
    """Render a human-readable release report."""

    if report.verdict == Verdict.APPROVE:
        verdict_text = Text("APPROVE", style="bold green on dark_green")
    else:
        verdict_text = Text("BLOCK", style="bold white on red")

    _console.print(
        Panel(
            verdict_text,
            title="AI RELEASE CONTRACT VERDICT",
            expand=False,
        )
    )

    counts = Counter(v.severity for v in report.violations)

    summary = Table(title="Run Summary", show_header=False)
    summary.add_column("Field")
    summary.add_column("Value")

    summary.add_row(
        "Baseline",
        f"{report.baseline.model} / {report.baseline.run_id}",
    )
    summary.add_row(
        "Candidate",
        f"{report.candidate.model} / {report.candidate.run_id}",
    )
    summary.add_row("Rules evaluated", str(len(report.rule_results)))
    summary.add_row(
        "Violations",
        (
            f"{counts[Severity.CRITICAL]} critical, "
            f"{counts[Severity.HIGH]} high, "
            f"{counts[Severity.WARNING]} warning, "
            f"{counts[Severity.INFO]} info"
        ),
    )

    _console.print(summary)

    blocking = tuple(v for v in report.violations if _is_blocking(v))
    non_blocking = tuple(v for v in report.violations if not _is_blocking(v))

    if report.verdict == Verdict.BLOCK and blocking:
        _render_violation_table("Blocking Violations", blocking)

    if non_blocking:
        _render_violation_table(
            "Non-blocking Violations",
            non_blocking,
            muted=True,
        )


def print_error(msg: str) -> None:
    """Print an input/configuration error to stderr."""

    _error_console.print(f"[bold red]ERROR:[/bold red] {msg}")
