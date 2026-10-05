# Tech Stack

## Language and Runtime

- **Python 3.12** — no other Python version is supported
- **Python standard library** wherever practical (argparse, json, math, os, dataclasses, enum, types)

## Dependencies

| Package | Role |
|---------|------|
| `PyYAML` | Parse release policy YAML files |
| `Rich` | Colour-coded console output, verdict banner, violation tables |
| `pytest` | Test runner |
| `Hypothesis` | Property-based testing of correctness invariants |

All dependencies must be pinned to exact versions in `pyproject.toml`.

## Runtime Constraints

This tool is intentionally minimal. The following are **permanently out of scope**:

- No network calls of any kind
- No external LLM APIs
- No database
- No frontend or web server
- No FastAPI or any HTTP framework
- No LangChain or any AI orchestration library
- No authentication
- No non-deterministic sources (clocks, RNG, environment variables) during evaluation

## Packaging

- Entry point: `python -m ai_release_contract check ...`
- `pyproject.toml` defines project metadata and dependencies
- `ai_release_contract/__main__.py` contains a single import and call to `main()`

## Common Commands

### Run the tool against example files

```bash
python -m ai_release_contract check \
  --baseline examples/baseline.json \
  --candidate examples/good_candidate.json \
  --policy examples/policy.yaml
```

```bash
python -m ai_release_contract check \
  --baseline examples/baseline.json \
  --candidate examples/bad_candidate.json \
  --policy examples/policy.yaml
```

### Run the test suite

```bash
pytest tests/
```

### Install dependencies (editable mode)

```bash
pip install -e ".[dev]"
```

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | APPROVE — candidate satisfies all policy rules |
| `1` | BLOCK — one or more blocking violations found |
| `2` | Invalid input or configuration — evaluation did not run |
