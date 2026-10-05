"""
Unit tests for ai_release_contract.loader.

Covers load_eval_input and load_policy with parametrised pytest tests.
Valid inputs must parse cleanly; invalid inputs must raise InputError(exit_code=2).
"""

from __future__ import annotations

import json
import math
import types
from pathlib import Path

import pytest
import yaml

from ai_release_contract.exceptions import InputError
from ai_release_contract.loader import load_eval_input, load_policy
from ai_release_contract.models import Direction, EvalInput, PolicyRule, Severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_json(tmp_path: Path, name: str, content: object) -> str:
    """Write *content* as JSON and return the file path as a string."""
    p = tmp_path / name
    p.write_text(json.dumps(content), encoding="utf-8")
    return str(p)


def write_raw(tmp_path: Path, name: str, content: str) -> str:
    """Write raw text to a file and return the path as a string."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def write_yaml(tmp_path: Path, name: str, content: object) -> str:
    """Serialise *content* to YAML and return the file path as a string."""
    p = tmp_path / name
    p.write_text(yaml.dump(content), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# load_eval_input – valid cases
# ---------------------------------------------------------------------------


class TestLoadEvalInputValid:
    """Tests that verify valid inputs parse correctly."""

    def test_valid_full_input_returns_eval_input(self, tmp_path: Path) -> None:
        """A well-formed JSON file produces an EvalInput with matching fields."""
        data = {"model": "gpt-4o", "run_id": "run-001", "metrics": {"accuracy": 0.95, "latency": 120.5}}
        path = write_json(tmp_path, "eval.json", data)
        result = load_eval_input(path, "baseline")

        assert isinstance(result, EvalInput)
        assert result.model == "gpt-4o"
        assert result.run_id == "run-001"
        assert result.metrics["accuracy"] == pytest.approx(0.95)
        assert result.metrics["latency"] == pytest.approx(120.5)

    def test_integer_metric_value_accepted_as_float(self, tmp_path: Path) -> None:
        """Integer metric values are accepted and converted to float."""
        data = {"model": "m", "run_id": "r", "metrics": {"score": 42}}
        path = write_json(tmp_path, "eval.json", data)
        result = load_eval_input(path, "candidate")

        assert result.metrics["score"] == 42.0
        assert isinstance(result.metrics["score"], float)

    def test_metrics_is_mapping_proxy_type(self, tmp_path: Path) -> None:
        """The returned EvalInput.metrics must be a MappingProxyType (immutable)."""
        data = {"model": "m", "run_id": "r", "metrics": {"f1": 0.88}}
        path = write_json(tmp_path, "eval.json", data)
        result = load_eval_input(path, "baseline")

        assert isinstance(result.metrics, types.MappingProxyType)

    def test_metrics_immutable_raises_on_assignment(self, tmp_path: Path) -> None:
        """Assigning to the MappingProxyType raises TypeError."""
        data = {"model": "m", "run_id": "r", "metrics": {"f1": 0.88}}
        path = write_json(tmp_path, "eval.json", data)
        result = load_eval_input(path, "baseline")

        with pytest.raises(TypeError):
            result.metrics["f1"] = 0.99  # type: ignore[index]

    def test_empty_metrics_dict_accepted(self, tmp_path: Path) -> None:
        """An empty metrics dict is valid (no metric values to reject)."""
        data = {"model": "m", "run_id": "r", "metrics": {}}
        path = write_json(tmp_path, "eval.json", data)
        result = load_eval_input(path, "baseline")

        assert result.metrics == {}


# ---------------------------------------------------------------------------
# load_eval_input – invalid cases
# ---------------------------------------------------------------------------


class TestLoadEvalInputInvalid:
    """Tests that verify invalid inputs raise InputError with exit_code=2."""

    def test_missing_file_raises_input_error(self, tmp_path: Path) -> None:
        """A non-existent file path raises InputError."""
        path = str(tmp_path / "nonexistent.json")
        with pytest.raises(InputError) as exc_info:
            load_eval_input(path, "baseline")
        assert exc_info.value.exit_code == 2
        assert path in str(exc_info.value)

    def test_non_json_content_raises_input_error(self, tmp_path: Path) -> None:
        """A file containing non-JSON content raises InputError."""
        path = write_raw(tmp_path, "eval.json", "this is not json }{")
        with pytest.raises(InputError) as exc_info:
            load_eval_input(path, "baseline")
        assert exc_info.value.exit_code == 2
        assert path in str(exc_info.value)

    @pytest.mark.parametrize("missing_field", ["model", "run_id", "metrics"])
    def test_missing_required_field_raises_input_error(
        self, tmp_path: Path, missing_field: str
    ) -> None:
        """A JSON file missing any required top-level field raises InputError."""
        data: dict = {"model": "m", "run_id": "r", "metrics": {"acc": 0.9}}
        del data[missing_field]
        path = write_json(tmp_path, "eval.json", data)

        with pytest.raises(InputError) as exc_info:
            load_eval_input(path, "baseline")
        assert exc_info.value.exit_code == 2
        assert missing_field in str(exc_info.value)
        assert path in str(exc_info.value)

    def test_model_not_string_raises_input_error(self, tmp_path: Path) -> None:
        """'model' field with a non-string value raises InputError."""
        data = {"model": 123, "run_id": "r", "metrics": {"acc": 0.9}}
        path = write_json(tmp_path, "eval.json", data)

        with pytest.raises(InputError) as exc_info:
            load_eval_input(path, "baseline")
        assert exc_info.value.exit_code == 2
        assert "model" in str(exc_info.value)

    def test_metrics_not_dict_raises_input_error(self, tmp_path: Path) -> None:
        """'metrics' field that is not a dict raises InputError."""
        data = {"model": "m", "run_id": "r", "metrics": [1, 2, 3]}
        path = write_json(tmp_path, "eval.json", data)

        with pytest.raises(InputError) as exc_info:
            load_eval_input(path, "baseline")
        assert exc_info.value.exit_code == 2
        assert "metrics" in str(exc_info.value)

    def test_non_numeric_metric_value_raises_input_error(self, tmp_path: Path) -> None:
        """A string metric value raises InputError."""
        data = {"model": "m", "run_id": "r", "metrics": {"score": "high"}}
        path = write_json(tmp_path, "eval.json", data)

        with pytest.raises(InputError) as exc_info:
            load_eval_input(path, "baseline")
        assert exc_info.value.exit_code == 2
        assert "score" in str(exc_info.value)

    @pytest.mark.parametrize("bool_value", [True, False])
    def test_boolean_metric_value_raises_input_error(
        self, tmp_path: Path, bool_value: bool
    ) -> None:
        """Boolean metric values raise InputError even though bool subclasses int."""
        # JSON True/False must be rejected
        data = {"model": "m", "run_id": "r", "metrics": {"flag": bool_value}}
        path = write_json(tmp_path, "eval.json", data)

        with pytest.raises(InputError) as exc_info:
            load_eval_input(path, "baseline")
        assert exc_info.value.exit_code == 2
        assert "flag" in str(exc_info.value)

    @pytest.mark.parametrize(
        "non_finite",
        [
            pytest.param(float("nan"), id="nan"),
            pytest.param(float("inf"), id="inf"),
            pytest.param(float("-inf"), id="-inf"),
        ],
    )
    def test_non_finite_metric_value_raises_input_error(
        self, tmp_path: Path, non_finite: float
    ) -> None:
        """Non-finite metric values (nan, inf, -inf) raise InputError.

        JSON doesn't support these natively, so we write them via a raw
        manipulation of the Python dict passed through json.dumps with
        allow_nan=True.
        """
        raw = json.dumps(
            {"model": "m", "run_id": "r", "metrics": {"x": non_finite}},
            allow_nan=True,
        )
        path = write_raw(tmp_path, "eval.json", raw)

        with pytest.raises(InputError) as exc_info:
            load_eval_input(path, "baseline")
        assert exc_info.value.exit_code == 2
        assert "x" in str(exc_info.value)

    def test_error_message_contains_role_and_path(self, tmp_path: Path) -> None:
        """Error messages must include both the role label and the file path."""
        path = str(tmp_path / "missing.json")
        with pytest.raises(InputError) as exc_info:
            load_eval_input(path, "candidate")
        msg = str(exc_info.value)
        assert "candidate" in msg
        assert path in msg


# ---------------------------------------------------------------------------
# load_policy – valid cases
# ---------------------------------------------------------------------------


MINIMAL_RULE = {
    "metric": "accuracy",
    "direction": "higher_is_better",
    "severity": "critical",
}


class TestLoadPolicyValid:
    """Tests that verify valid policy files parse correctly."""

    def test_valid_full_policy_returns_tuple_of_policy_rules(self, tmp_path: Path) -> None:
        """A well-formed YAML policy file produces a tuple[PolicyRule, ...]."""
        policy = {
            "rules": [
                {
                    "metric": "accuracy",
                    "direction": "higher_is_better",
                    "severity": "critical",
                    "is_critical_gate": True,
                    "min_value": 0.8,
                    "max_regression_pct": 5.0,
                }
            ]
        }
        path = write_yaml(tmp_path, "policy.yaml", policy)
        result = load_policy(path)

        assert isinstance(result, tuple)
        assert len(result) == 1
        rule = result[0]
        assert isinstance(rule, PolicyRule)
        assert rule.metric == "accuracy"
        assert rule.direction == Direction.HIGHER_IS_BETTER
        assert rule.severity == Severity.CRITICAL
        assert rule.is_critical_gate is True
        assert rule.min_value == pytest.approx(0.8)
        assert rule.max_regression_pct == pytest.approx(5.0)

    def test_is_critical_gate_defaults_to_false(self, tmp_path: Path) -> None:
        """is_critical_gate defaults to False when absent from the rule."""
        policy = {"rules": [MINIMAL_RULE]}
        path = write_yaml(tmp_path, "policy.yaml", policy)
        result = load_policy(path)

        assert result[0].is_critical_gate is False

    def test_all_optional_fields_absent_parses_correctly(self, tmp_path: Path) -> None:
        """A rule with only metric/direction/severity (no optionals) is valid."""
        policy = {"rules": [MINIMAL_RULE]}
        path = write_yaml(tmp_path, "policy.yaml", policy)
        result = load_policy(path)

        rule = result[0]
        assert rule.metric == "accuracy"
        assert rule.direction == Direction.HIGHER_IS_BETTER
        assert rule.severity == Severity.CRITICAL
        assert rule.is_critical_gate is False
        assert rule.min_value is None
        assert rule.max_value is None
        assert rule.max_regression_pct is None

    def test_lower_is_better_with_max_value(self, tmp_path: Path) -> None:
        """lower_is_better direction with max_value is valid."""
        policy = {
            "rules": [
                {
                    "metric": "latency",
                    "direction": "lower_is_better",
                    "severity": "high",
                    "max_value": 500.0,
                }
            ]
        }
        path = write_yaml(tmp_path, "policy.yaml", policy)
        result = load_policy(path)

        assert result[0].max_value == pytest.approx(500.0)
        assert result[0].min_value is None

    def test_multiple_rules_parsed_in_order(self, tmp_path: Path) -> None:
        """Multiple rules are returned in declaration order."""
        policy = {
            "rules": [
                {"metric": "f1", "direction": "higher_is_better", "severity": "critical"},
                {"metric": "latency", "direction": "lower_is_better", "severity": "warning"},
            ]
        }
        path = write_yaml(tmp_path, "policy.yaml", policy)
        result = load_policy(path)

        assert len(result) == 2
        assert result[0].metric == "f1"
        assert result[1].metric == "latency"

    @pytest.mark.parametrize("severity_value", ["critical", "high", "warning", "info"])
    def test_all_severity_values_accepted(
        self, tmp_path: Path, severity_value: str
    ) -> None:
        """All four valid severity strings parse without error."""
        policy = {
            "rules": [
                {
                    "metric": "score",
                    "direction": "higher_is_better",
                    "severity": severity_value,
                }
            ]
        }
        path = write_yaml(tmp_path, "policy.yaml", policy)
        result = load_policy(path)
        assert result[0].severity == Severity(severity_value)


# ---------------------------------------------------------------------------
# load_policy – invalid cases
# ---------------------------------------------------------------------------


class TestLoadPolicyInvalid:
    """Tests that verify invalid policy files raise InputError with exit_code=2."""

    def test_missing_file_raises_input_error(self, tmp_path: Path) -> None:
        """A non-existent file path raises InputError."""
        path = str(tmp_path / "nonexistent.yaml")
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert exc_info.value.exit_code == 2
        assert path in str(exc_info.value)

    def test_invalid_yaml_raises_input_error(self, tmp_path: Path) -> None:
        """A file with malformed YAML raises InputError."""
        path = write_raw(tmp_path, "policy.yaml", "rules: [}{")
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert exc_info.value.exit_code == 2
        assert path in str(exc_info.value)

    def test_missing_rules_key_raises_input_error(self, tmp_path: Path) -> None:
        """A YAML file without a 'rules' key raises InputError."""
        path = write_yaml(tmp_path, "policy.yaml", {"thresholds": []})
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert exc_info.value.exit_code == 2
        assert "rules" in str(exc_info.value)
        assert path in str(exc_info.value)

    def test_rules_not_list_raises_input_error(self, tmp_path: Path) -> None:
        """'rules' that is not a list raises InputError."""
        path = write_yaml(tmp_path, "policy.yaml", {"rules": "not-a-list"})
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert exc_info.value.exit_code == 2
        assert "rules" in str(exc_info.value)

    @pytest.mark.parametrize(
        "bad_direction",
        ["ascending", "desc", "", None, 42],
        ids=["ascending", "desc", "empty-str", "null", "integer"],
    )
    def test_unknown_direction_raises_input_error(
        self, tmp_path: Path, bad_direction: object
    ) -> None:
        """An unknown direction value raises InputError mentioning the rule index."""
        rule = {"metric": "acc", "direction": bad_direction, "severity": "critical"}
        path = write_yaml(tmp_path, "policy.yaml", {"rules": [rule]})
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert exc_info.value.exit_code == 2
        msg = str(exc_info.value)
        assert "0" in msg  # rule index 0

    @pytest.mark.parametrize(
        "bad_severity",
        ["low", "blocker", "", None, 1],
        ids=["low", "blocker", "empty-str", "null", "integer"],
    )
    def test_unknown_severity_raises_input_error(
        self, tmp_path: Path, bad_severity: object
    ) -> None:
        """An unknown severity value raises InputError mentioning the rule index."""
        rule = {"metric": "acc", "direction": "higher_is_better", "severity": bad_severity}
        path = write_yaml(tmp_path, "policy.yaml", {"rules": [rule]})
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert exc_info.value.exit_code == 2
        assert "0" in str(exc_info.value)

    def test_rule_index_in_error_message_for_second_rule(self, tmp_path: Path) -> None:
        """The error message includes the correct 0-based rule index."""
        policy = {
            "rules": [
                MINIMAL_RULE,  # rule 0 – valid
                {
                    "metric": "latency",
                    "direction": "lower_is_better",
                    "severity": "bad_severity",  # rule 1 – invalid
                },
            ]
        }
        path = write_yaml(tmp_path, "policy.yaml", policy)
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert "1" in str(exc_info.value)  # rule index 1

    @pytest.mark.parametrize(
        "threshold_field,bad_value",
        [
            ("min_value", float("nan")),
            ("min_value", float("inf")),
            ("min_value", float("-inf")),
            ("max_value", float("nan")),
            ("max_value", float("inf")),
        ],
        ids=["min-nan", "min-inf", "min-neg-inf", "max-nan", "max-inf"],
    )
    def test_non_finite_threshold_raises_input_error(
        self, tmp_path: Path, threshold_field: str, bad_value: float
    ) -> None:
        """Non-finite min_value or max_value raises InputError."""
        direction = (
            "higher_is_better" if threshold_field == "min_value" else "lower_is_better"
        )
        rule = {
            "metric": "score",
            "direction": direction,
            "severity": "critical",
            threshold_field: bad_value,
        }
        # yaml.dump serialises inf/nan as .inf/.nan which PyYAML will load back
        path = write_yaml(tmp_path, "policy.yaml", {"rules": [rule]})
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert exc_info.value.exit_code == 2

    def test_negative_max_regression_pct_raises_input_error(self, tmp_path: Path) -> None:
        """A negative max_regression_pct raises InputError."""
        rule = {**MINIMAL_RULE, "max_regression_pct": -5.0}
        path = write_yaml(tmp_path, "policy.yaml", {"rules": [rule]})
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert exc_info.value.exit_code == 2
        assert "max_regression_pct" in str(exc_info.value)

    def test_non_finite_max_regression_pct_raises_input_error(self, tmp_path: Path) -> None:
        """A non-finite max_regression_pct raises InputError."""
        rule = {**MINIMAL_RULE, "max_regression_pct": float("inf")}
        path = write_yaml(tmp_path, "policy.yaml", {"rules": [rule]})
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert exc_info.value.exit_code == 2

    def test_max_value_on_higher_is_better_raises_input_error(self, tmp_path: Path) -> None:
        """max_value is invalid for higher_is_better direction."""
        rule = {
            "metric": "accuracy",
            "direction": "higher_is_better",
            "severity": "critical",
            "max_value": 0.99,
        }
        path = write_yaml(tmp_path, "policy.yaml", {"rules": [rule]})
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert exc_info.value.exit_code == 2
        msg = str(exc_info.value)
        assert "max_value" in msg
        assert "higher_is_better" in msg

    def test_min_value_on_lower_is_better_raises_input_error(self, tmp_path: Path) -> None:
        """min_value is invalid for lower_is_better direction."""
        rule = {
            "metric": "latency",
            "direction": "lower_is_better",
            "severity": "warning",
            "min_value": 10.0,
        }
        path = write_yaml(tmp_path, "policy.yaml", {"rules": [rule]})
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert exc_info.value.exit_code == 2
        msg = str(exc_info.value)
        assert "min_value" in msg
        assert "lower_is_better" in msg

    def test_boolean_threshold_value_raises_input_error(self, tmp_path: Path) -> None:
        """A boolean value for min_value (True) raises InputError."""
        # YAML True is parsed as Python True (a bool, which is also an int)
        # The loader must reject it explicitly.
        rule = {
            "metric": "accuracy",
            "direction": "higher_is_better",
            "severity": "critical",
            "min_value": True,
        }
        path = write_yaml(tmp_path, "policy.yaml", {"rules": [rule]})
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert exc_info.value.exit_code == 2
        assert "min_value" in str(exc_info.value)

    def test_error_message_includes_file_path(self, tmp_path: Path) -> None:
        """File-level error messages must include the policy file path."""
        path = str(tmp_path / "missing_policy.yaml")
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert path in str(exc_info.value)

    def test_error_message_includes_rule_index_for_rule_errors(
        self, tmp_path: Path
    ) -> None:
        """Rule-level error messages include the 0-based rule index."""
        policy = {
            "rules": [
                MINIMAL_RULE,
                MINIMAL_RULE,
                {
                    "metric": "score",
                    "direction": "INVALID",  # bad direction on rule 2
                    "severity": "critical",
                },
            ]
        }
        path = write_yaml(tmp_path, "policy.yaml", policy)
        with pytest.raises(InputError) as exc_info:
            load_policy(path)
        assert "2" in str(exc_info.value)
