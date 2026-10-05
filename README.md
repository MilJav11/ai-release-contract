# AI Release Contract

AI Release Contract is a deterministic, local-first CLI release policy gate for AI systems. It consumes evaluation metrics from a known-good baseline AI run and a candidate AI run — alongside a declarative YAML release policy — and produces a deterministic `APPROVE` or `BLOCK` verdict, a colour-coded Rich console summary, and a machine-readable JSON report. The tool runs entirely offline, has no external dependencies beyond the Python standard library plus PyYAML and Rich, and exits with a well-defined code (`0` = APPROVE, `1` = BLOCK, `2` = invalid config/malformed input) so it can serve as a hard gate in any CI/CD pipeline.

## Quick Start

```bash
pip install -e ".[dev]"

python -m ai_release_contract check \
  --baseline  examples/baseline.json \
  --candidate examples/good_candidate.json \
  --policy    examples/policy.yaml \
  --output    release_report.json
```
