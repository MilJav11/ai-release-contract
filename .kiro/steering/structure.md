# Project Structure

## Directory Layout

```
ai-release-contract/
├── ai_release_contract/          # Main package
│   ├── __init__.py
│   ├── __main__.py               # Entry point: python -m ai_release_contract
│   ├── cli.py                    # Argument parsing and orchestration only
│   ├── models.py                 # All dataclasses and enums
│   ├── loader.py                 # File I/O, JSON/YAML parsing, schema validation
│   ├── engine.py                 # Pure comparison logic, violation accumulation
│   ├── verdict.py                # Deterministic APPROVE/BLOCK decision
│   ├── exceptions.py             # InputError (exit code 2) and typed subclasses
│   └── reporter/
│       ├── __init__.py
│       ├── console.py            # Rich-based console output
│       └── json_report.py        # JSON report serialisation and atomic disk write
│
├── examples/
│   ├── baseline.json             # Known-good reference metrics
│   ├── good_candidate.json       # Candidate that should APPROVE
│   ├── bad_candidate.json        # Candidate that should BLOCK
│   └── policy.yaml               # Exercises all directions, thresholds, and severities
│
├── tests/
│   ├── conftest.py               # Shared fixtures and Hypothesis strategies/profiles
│   ├── test_loader.py            # Unit + property tests for loader
│   ├── test_engine.py            # Unit + property tests for engine
│   ├── test_verdict.py           # Unit + property tests for verdict
│   ├── test_reporter.py          # Unit tests for JSON report schema
│   ├── test_cli_examples.py      # End-to-end tests using subprocess against example files
│   └── test_properties.py        # Cross-cutting Hypothesis property tests
│
├── .kiro/                        # Kiro IDE configuration — committed to version control
│   ├── steering/                 # These steering files
│   └── specs/                    # Spec-driven feature definitions
│
├── pyproject.toml                # Project metadata, dependencies, build config
└── README.md                     # One-paragraph description and quick-start example
```

## Module Responsibility Boundaries

Each module has a single, non-overlapping responsibility. Do not blur these lines.

| Module | Responsibility |
|--------|---------------|
| `models.py` | Data shapes only — frozen dataclasses and enums. No I/O, no logic. |
| `exceptions.py` | `InputError` definition only. No logic. |
| `loader.py` | All file I/O, JSON/YAML parsing, and schema/semantic validation. Raises `InputError` on any problem. Returns clean model objects. |
| `engine.py` | Pure metric comparison function. No I/O, no global state. Given `(baseline, candidate, rules)` → returns `tuple[RuleResult, ...]`. Raises `InputError` if a policy rule references a metric absent from baseline. |
| `verdict.py` | Determines `APPROVE` or `BLOCK` from a tuple of `RuleResult` objects. No I/O, no external state. |
| `reporter/console.py` | Renders a `Report` to the terminal using Rich. No business logic. |
| `reporter/json_report.py` | Serialises a `Report` to JSON and writes atomically to disk. No business logic. |
| `cli.py` | Wires the above modules together. Handles `InputError` and calls `sys.exit`. Contains no business logic of its own. |

## Key Architecture Rules

- **Business logic lives in `engine.py` and `verdict.py` only.** CLI and reporters are pure I/O and presentation.
- **`engine.py` is a pure function.** `evaluate(baseline, candidate, rules)` reads no files and produces the same output for the same inputs every time.
- **`loader.py` owns file parsing and self-contained validation.** This includes file I/O, JSON/YAML parsing, schema validation, numeric type validation (booleans, non-finite values), and per-rule semantic field validation (unknown enums, direction/threshold conflicts, invalid threshold values). By the time `loader.py` returns, all individual inputs are structurally and semantically clean.
- **`engine.py` owns the cross-input invariant.** Before any rule comparison proceeds, `engine.evaluate()` checks that every metric referenced by a policy rule exists in the baseline and raises `InputError` (exit code 2) if any is absent. This check requires both the policy and the baseline to be present simultaneously, so it belongs in the engine rather than the loader.
- **`EvalInput.metrics` is stored as `types.MappingProxyType`** to prevent mutation after load.
- **All core model types are `@dataclass(frozen=True)`** to support equality comparison required by determinism property tests.
- **JSON report is written atomically** (write to temp file, then `os.replace`) so a BLOCK result never leaves a corrupt report on disk.

## Data Flow

```
cli.py
  │
  ├─→ loader.load_eval_input()  ──→  EvalInput (baseline)
  ├─→ loader.load_eval_input()  ──→  EvalInput (candidate)
  ├─→ loader.load_policy()      ──→  tuple[PolicyRule, ...]
  │
  ├─→ engine.evaluate()         ──→  tuple[RuleResult, ...]
  ├─→ verdict.determine_verdict()  ──→  (Verdict, tuple[Violation, ...])
  │
  ├─→ reporter/console.render()     (stdout)
  ├─→ reporter/json_report.write()  (disk)
  │
  └─→ sys.exit(0 | 1)
```

Any `InputError` raised during loading or engine baseline-check is caught in `cli.py` and causes `sys.exit(2)`.
