from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(candidate: str, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_release_contract",
            "check",
            "--baseline",
            str(ROOT / "examples" / "baseline.json"),
            "--candidate",
            str(ROOT / "examples" / candidate),
            "--policy",
            str(ROOT / "examples" / "policy.yaml"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_good_candidate_approves(tmp_path):
    output = tmp_path / "good.json"
    result = _run("good_candidate.json", output)

    assert result.returncode == 0
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["verdict"] == "APPROVE"


def test_bad_candidate_blocks(tmp_path):
    output = tmp_path / "bad.json"
    result = _run("bad_candidate.json", output)

    assert result.returncode == 1
    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["verdict"] == "BLOCK"
    assert any(
        violation["metric"] == "canary_leaks"
        for violation in data["violations"]
    )


def test_missing_policy_returns_exit_code_2(tmp_path):
    output = tmp_path / "missing.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_release_contract",
            "check",
            "--baseline",
            str(ROOT / "examples" / "baseline.json"),
            "--candidate",
            str(ROOT / "examples" / "good_candidate.json"),
            "--policy",
            str(ROOT / "examples" / "does-not-exist.yaml"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert not output.exists()
