# AI Release Contract Power

Reusable Kiro Power for deterministic AI release-readiness decisions.

## What it provides

The release-quality-gate skill guides an agent to:

- compare candidate AI evaluation results against a known-good baseline
- apply an explicit YAML release policy
- identify blocking critical/high-severity regressions
- preserve non-compensating release semantics
- fail closed when required critical metrics are missing

## Package structure

ai-release-contract/
  plugin.json
  skills/
    release-quality-gate/
      SKILL.md

## Install in Kiro

1. Open the Powers panel.
2. Choose Add Custom Power.
3. Choose Import power from a folder or Import power from GitHub.
4. Select this Power directory.
5. Install.

## Example use

Evaluate:
- examples/baseline.json
- examples/bad_candidate.json
- examples/policy.yaml

Expected verdict: BLOCK.

## Project

https://github.com/MilJav11/ai-release-contract
