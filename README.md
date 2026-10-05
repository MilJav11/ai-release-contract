# AI Release Contract

A deterministic, local-first release policy gate for AI systems.

AI Release Contract compares evaluation metrics from a known-good baseline and a candidate AI version against an explicit YAML release policy and returns a reproducible `APPROVE` or `BLOCK` decision.

It does not call an LLM. It consumes externally produced evaluation metrics and acts as a deterministic release gate.

## Why

A candidate AI version can improve one metric while silently regressing another.

The release decision follows:

```
baseline metrics
       +
candidate metrics
       +
release policy
       |
       v
comparison engine
       |
       v
APPROVE / BLOCK
```

Blocking failures cannot be compensated for by unrelated improvements.

## Quick start

Requires Python 3.12+.

Install:

```
python -m venv .venv
pip install -e ".[dev]"
```

Good candidate:

```
python -m ai_release_contract check --baseline examples/baseline.json --candidate examples/good_candidate.json --policy examples/policy.yaml --output release_report.json
```

Expected:

```
APPROVE
exit code 0
```

Bad candidate:

```
python -m ai_release_contract check --baseline examples/baseline.json --candidate examples/bad_candidate.json --policy examples/policy.yaml --output release_report.json
```

Expected:

```
BLOCK
exit code 1
```

Blocking metrics include:

- `task_success_rate`
- `hallucination_rate`
- `canary_leaks`

## Testing

Validated on Python 3.12.10.

```
96 tests passed
```

The suite includes unit tests, end-to-end CLI tests, and Hypothesis property-based tests.

## Kiro University Challenge 2026

This repository demonstrates:

1. Specs - `.kiro/specs/ai-release-contract/`
2. Steering - `.kiro/steering/`
3. Hooks - `.kiro/hooks/pytest-on-save.json`
4. Property-based testing - `tests/test_properties.py`
5. Powers - `powers/ai-release-contract/`
6. MCP - `.kiro/settings/mcp.json` and `ai_release_contract/mcp_server.py`
7. Custom Agent - `.kiro/agents/release-qa.json`

## MCP

The MCP server exposes:

- `check_release`
- `compare_metrics`
- `explain_blockers`

Kiro successfully connected to it as a workspace MCP server with all three tools.

## Kiro Power

Reusable Power:

`powers/ai-release-contract/`

It contains:

- `plugin.json`
- `README.md`
- `skills/release-quality-gate/SKILL.md`

## Challenge evidence

Detailed lesson evidence:

`docs/challenge-evidence.md`

## Repository

https://github.com/MilJav11/ai-release-contract
