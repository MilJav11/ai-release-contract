# Kiro University Challenge 2026 — Evidence

## Project

AI Release Contract is a deterministic, local-first release policy gate for AI systems.

It compares evaluation metrics from a known-good baseline and a candidate against a declarative YAML release policy, then produces an APPROVE or BLOCK verdict, machine-readable JSON report, console output, and CI-friendly exit code.

Public repository:
https://github.com/MilJav11/ai-release-contract

## Lesson 1 — Spec-driven development

Used Kiro Specs to define the project before implementation.

Relevant files:
- `.kiro/specs/ai-release-contract/requirements.md`
- `.kiro/specs/ai-release-contract/design.md`
- `.kiro/specs/ai-release-contract/tasks.md`

The spec defines requirements, architecture, correctness properties, implementation tasks, exit-code semantics, validation rules, and deterministic release behavior.

## Lesson 2 — Steering documents

Created project-specific steering that constrains Kiro's implementation decisions and establishes architectural boundaries.

Relevant files:
- `.kiro/steering/product.md`
- `.kiro/steering/tech.md`
- `.kiro/steering/structure.md`
- `.kiro/steering/release-contract.md`

The steering defines product scope, Python stack, module responsibilities, deterministic/fail-closed behavior, validation ownership, and release invariants.

## Lesson 3 — Hooks

Created a workspace PostFileSave hook that automatically runs the deterministic pytest suite whenever a Python file is saved.

Relevant file:
- `.kiro/hooks/pytest-on-save.json`

Demonstration:
- saved a Python file in Kiro
- hook automatically executed `python -m pytest -q`
- test suite completed successfully with 96 passing tests

## Lesson 4 — Property-based testing

Used Hypothesis to test correctness invariants across generated input spaces rather than only fixed examples.

Relevant file:
- `tests/test_properties.py`

Required properties demonstrated:
- Property 4: missing required critical-gate metric blocks release
- Property 7: any blocking violation forces BLOCK regardless of improvements
- Property 8: APPROVE iff there are zero blocking violations
- Property 9: identical inputs produce identical outputs

Validation:
- Python 3.12.10
- 96 tests passing

## Lesson 5 — Powers

Created and packaged a reusable Kiro Power for deterministic AI release-readiness reviews.

Relevant files:
- `powers/ai-release-contract/plugin.json`
- `powers/ai-release-contract/skills/release-quality-gate/SKILL.md`
- `powers/ai-release-contract/README.md`

Demonstration:
- imported the Power into Kiro from the local project folder
- Kiro displayed `ai-release-contract` under Installed Powers
- Kiro recognized the `release-quality-gate` skill and its description

## Lesson 6 — Model Context Protocol (MCP)

Implemented a local MCP server backed by the project's deterministic release engine.

Relevant files:
- `.kiro/settings/mcp.json`
- `ai_release_contract/mcp_server.py`
- `scripts/mcp_smoke.py`

MCP tools:
- `check_release`
- `compare_metrics`
- `explain_blockers`

Demonstration:
- MCP smoke client discovered all three tools
- `check_release` returned BLOCK for the bad candidate
- `explain_blockers` returned `canary_leaks`, `hallucination_rate`, and `task_success_rate`
- Kiro displayed the server as `Connected (3 tools)` and listed all three tools

## Lesson 7 — Custom agents

Created a specialized workspace custom agent for AI release-quality reviews.

Relevant file:
- `.kiro/agents/release-qa.json`

The agent:
- loads project steering
- includes workspace MCP configuration
- includes installed Powers
- is constrained to deterministic release evidence
- is instructed not to invent metrics or override blocking violations

Demonstration:
- Kiro loaded `release-qa` in the Workspace section of the agent picker

## Bonus — Package a Kiro Power

The reusable Power is packaged in the public repository with a plugin manifest, skill, and documentation.

Public Power package:
https://github.com/MilJav11/ai-release-contract/tree/main/powers/ai-release-contract

Files:
- `plugin.json`
- `skills/release-quality-gate/SKILL.md`
- `README.md`

## Functional validation

The project was validated on Python 3.12.10.

Full suite:
96 tests passed.

Example good candidate:
- verdict: APPROVE
- exit code: 0

Example bad candidate:
- verdict: BLOCK
- exit code: 1
- blocking metrics include task success, hallucination rate, and canary leakage

The MCP integration independently returned the same deterministic BLOCK result.
