# Product Overview

## What It Is

**AI Release Contract** is a deterministic, local-first release policy gate for AI systems. It is a focused CLI engineering tool — not a platform, dashboard, or AI content generator.

It does **not** call an LLM at runtime. It does **not** perform evaluation. It consumes evaluation outputs produced by external evaluation pipelines and applies a declarative policy to reach a binary verdict.

## Runtime Workflow

```
baseline evaluation metrics (JSON)
+ candidate evaluation metrics (JSON)
+ declarative release policy (YAML)
→ deterministic comparison
→ APPROVE or BLOCK
→ Rich console output + JSON report + process exit code
```

## Target Users

- AI QA engineers
- AI reliability engineers
- Release engineers
- Teams shipping LLM, RAG, or agent systems who need a hard gate in CI/CD

## Core Value

Prevent silent quality, security, and performance regressions from being released. Composite scores and aggregate metrics can hide single-dimension failures — this tool does not allow that.

## Critical Design Rules

- **Critical and high severity violations block the release.** Warning and info violations are reported but never block.
- **Improvements in passing metrics never compensate for a blocking failure.** There is no aggregate score. Each rule is evaluated independently.
- **Missing required critical metrics fail closed.** A metric marked `is_critical_gate: true` that is absent from the candidate immediately produces a BLOCK — silence is treated as failure.
- **Malformed or semantically invalid inputs exit with code 2** before any evaluation occurs.
- **The tool stays a focused CLI.** No dashboards, no servers, no authentication, no persistence layer.

## What This Tool Does Not Do

- Does not run LLM evaluations
- Does not call any external API or LLM at runtime
- Does not score or rank candidates
- Does not aggregate or weight metrics against each other
- Does not require a database, frontend, or network access
