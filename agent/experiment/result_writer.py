"""Persistence helpers for PhishWalk experiment results."""

import json
from pathlib import Path

from agent.experiment.run_result import TargetRunResult


def append_target_result(
    run_directory: Path,
    result: TargetRunResult,
) -> Path:
    """Append one target result to the run-level JSON Lines file."""
    if not run_directory.is_dir():
        raise FileNotFoundError(f"run directory does not exist: {run_directory}")

    results_path = run_directory / "results.jsonl"
    with results_path.open("a", encoding="utf-8") as results_file:
        results_file.write(result.model_dump_json())
        results_file.write("\n")

    return results_path


def write_pretty_results(run_directory: Path) -> Path:
    """Write accumulated JSON Lines results as one readable JSON array."""
    if not run_directory.is_dir():
        raise FileNotFoundError(f"run directory does not exist: {run_directory}")

    jsonl_path = run_directory / "results.jsonl"
    if not jsonl_path.is_file():
        raise FileNotFoundError(f"JSON Lines results do not exist: {jsonl_path}")

    results = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    json_path = run_directory / "results.json"
    json_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return json_path
