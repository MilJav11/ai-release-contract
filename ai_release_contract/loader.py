"""
Loader functions for AI Release Contract.

Provides:
  load_eval_input(path, role) -> EvalInput
  load_policy(path)          -> tuple[PolicyRule, ...]
"""

from __future__ import annotations

import json
import math

import yaml

from ai_release_contract.exceptions import InputError
from ai_release_contract.models import Direction, EvalInput, PolicyRule, Severity


# ---------------------------------------------------------------------------
# load_eval_input
# ---------------------------------------------------------------------------


def load_eval_input(path: str, role: str) -> EvalInput:
    """Load and validate a JSON evaluation file (baseline or candidate).

    Parameters
    ----------
    path:
        File-system path to the JSON file.
    role:
        Human-readable label used in error messages (e.g. "baseline", "candidate").

    Raises
    ------
    InputError
        On any I/O, parse, or schema problem (exit_code=2).
    """
    # Step 1: open file
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        raise InputError(f"Cannot read {role} file {path}: {exc}") from exc

    # Step 2: parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(f"Invalid JSON in {role} file '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise InputError(
            f"Invalid JSON in {role} file '{path}': top-level value must be an object"
        )

    # Step 3: validate top-level keys
    for field, expected_type in (("model", str), ("run_id", str), ("metrics", dict)):
        if field not in data:
            raise InputError(
                f"Invalid {role} file '{path}': missing required field '{field}'"
            )
        if not isinstance(data[field], expected_type):
            raise InputError(
                f"Invalid {role} file '{path}': field '{field}' must be a "
                f"{expected_type.__name__}, got {type(data[field]).__name__}"
            )

    metrics_raw: dict = data["metrics"]

    # Step 4: validate each metric value
    for key, value in metrics_raw.items():
        # 4a: reject booleans first (bool is a subclass of int in Python)
        if isinstance(value, bool):
            raise InputError(
                f"Invalid {role} file '{path}': metric '{key}' has boolean value "
                f"{value!r}; metric values must be numbers"
            )
        # 4b: must be int or float
        if not isinstance(value, (int, float)):
            raise InputError(
                f"Invalid {role} file '{path}': metric '{key}' has non-numeric value "
                f"{value!r} ({type(value).__name__})"
            )
        # 4c: must be finite
        if not math.isfinite(value):
            raise InputError(
                f"Invalid {role} file '{path}': metric '{key}' has non-finite value "
                f"{value!r}"
            )

    # Step 5: return EvalInput (metrics converted to float for uniformity)
    metrics: dict[str, float] = {k: float(v) for k, v in metrics_raw.items()}
    return EvalInput(model=data["model"], run_id=data["run_id"], metrics=metrics)


# ---------------------------------------------------------------------------
# load_policy
# ---------------------------------------------------------------------------


def load_policy(path: str) -> tuple[PolicyRule, ...]:
    """Load and validate a YAML policy file.

    Parameters
    ----------
    path:
        File-system path to the YAML file.

    Raises
    ------
    InputError
        On any I/O, parse, or schema problem (exit_code=2).
    """
    # Step 1: open file
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        raise InputError(f"Cannot read policy file '{path}': {exc}") from exc

    # Step 2: parse YAML
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise InputError(f"Invalid YAML in policy file '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise InputError(
            f"Invalid policy file '{path}': top-level value must be a mapping"
        )

    # Step 3: validate top-level 'rules' key
    if "rules" not in data:
        raise InputError(f"Invalid policy file '{path}': missing required key 'rules'")
    if not isinstance(data["rules"], list):
        raise InputError(
            f"Invalid policy file '{path}': 'rules' must be a list, "
            f"got {type(data['rules']).__name__}"
        )

    rules_raw: list = data["rules"]
    rules: list[PolicyRule] = []

    for i, item in enumerate(rules_raw):
        if not isinstance(item, dict):
            raise InputError(
                f"Rule {i}: each rule must be a mapping, got {type(item).__name__}"
            )

        # 4a: metric — non-empty string
        metric = item.get("metric")
        if not isinstance(metric, str) or not metric:
            raise InputError(
                f"Rule {i}: 'metric' must be a non-empty string, got {metric!r}"
            )

        # 4b: direction
        direction_raw = item.get("direction")
        try:
            direction = Direction(direction_raw)
        except (ValueError, KeyError):
            raise InputError(
                f"Rule {i}: unknown direction '{direction_raw}'"
            ) from None

        # 4c: severity
        severity_raw = item.get("severity")
        try:
            severity = Severity(severity_raw)
        except (ValueError, KeyError):
            raise InputError(
                f"Rule {i}: unknown severity '{severity_raw}'"
            ) from None

        # 4d: optional numeric fields
        min_value: float | None = None
        max_value: float | None = None
        max_regression_pct: float | None = None

        for field_name in ("min_value", "max_value"):
            if field_name in item:
                v = item[field_name]
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise InputError(
                        f"Rule {i}: '{field_name}' must be a number, got {v!r}"
                    )
                fv = float(v)
                if not math.isfinite(fv):
                    raise InputError(
                        f"Rule {i}: '{field_name}' must be a finite number, got {v!r}"
                    )
                if field_name == "min_value":
                    min_value = fv
                else:
                    max_value = fv

        if "max_regression_pct" in item:
            v = item["max_regression_pct"]
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise InputError(
                    f"Rule {i}: 'max_regression_pct' must be a number, got {v!r}"
                )
            fv = float(v)
            if not math.isfinite(fv) or fv < 0:
                raise InputError(
                    f"Rule {i}: 'max_regression_pct' must be a finite non-negative "
                    f"number, got {v!r}"
                )
            max_regression_pct = fv

        # 4e: direction-threshold consistency
        if direction == Direction.HIGHER_IS_BETTER and "max_value" in item:
            raise InputError(
                f"Rule {i}: max_value is not valid for direction higher_is_better"
            )
        if direction == Direction.LOWER_IS_BETTER and "min_value" in item:
            raise InputError(
                f"Rule {i}: min_value is not valid for direction lower_is_better"
            )

        # 4f: optional bool is_critical_gate (default False)
        is_critical_gate_raw = item.get("is_critical_gate", False)
        if not isinstance(is_critical_gate_raw, bool):
            raise InputError(
                f"Rule {i}: 'is_critical_gate' must be a boolean, "
                f"got {is_critical_gate_raw!r}"
            )
        is_critical_gate: bool = is_critical_gate_raw

        rules.append(
            PolicyRule(
                metric=metric,
                direction=direction,
                severity=severity,
                is_critical_gate=is_critical_gate,
                min_value=min_value,
                max_value=max_value,
                max_regression_pct=max_regression_pct,
            )
        )

    return tuple(rules)
