"""Reproducibility metadata for one PhishWalk experiment run."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from agent.browser.config import BrowserConfig
from agent.config import AgentConfig
from agent.model import ModelConfig
from agent.prompts import build_system_prompt


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _sha256_bytes(value: bytes) -> str:
    """Return a prefixed SHA-256 digest for reproducibility metadata."""
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _git_output(*arguments: str) -> str | None:
    """Return one Git command's stdout, or None outside a valid worktree."""
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def build_run_manifest(
    *,
    started_at: datetime,
    target_file: Path,
    target_count: int,
    model_config: ModelConfig,
    agent_config: AgentConfig,
    browser_config: BrowserConfig,
) -> dict[str, object]:
    """Build a secret-free snapshot of settings that affect one run."""

    system_prompt = build_system_prompt(agent_config.traversal_policy)

    if started_at.tzinfo is None:
        raise ValueError("started_at must include timezone information")
    if target_count < 1:
        raise ValueError("target_count must be at least 1")

    try:
        target_bytes = target_file.read_bytes()
    except OSError as error:
        raise RuntimeError(f"failed to read target file: {target_file}") from error

    git_commit = _git_output("rev-parse", "HEAD")
    utc_started_at = started_at.astimezone(timezone.utc)

    return {
        "schema_version": 1,
        "started_at": utc_started_at.isoformat().replace("+00:00", "Z"),
        "git": {
            "commit": git_commit,
        },
        "prompt": {
            "profile": agent_config.traversal_policy,
            "sha256": _sha256_bytes(system_prompt.encode("utf-8")),
        },
        "model": {
            "provider": model_config.provider,
            "name": model_config.model,
            "temperature": model_config.temperature,
        },
        "agent": {
            "traversal_policy": agent_config.traversal_policy,
            "max_interactive_elements": (
                agent_config.max_interactive_elements
            ),
            "max_visible_text_chars": agent_config.max_visible_text_chars,
            "max_change_text_items": agent_config.max_change_text_items,
            "max_change_element_items": (
                agent_config.max_change_element_items
            ),
            "max_action_plan_steps": agent_config.max_action_plan_steps,
            "max_validation_retries": agent_config.max_validation_retries,
            "target_timeout_seconds": agent_config.target_timeout_seconds,
            "enabled_actions": list(agent_config.enabled_actions),
        },
        "browser": {
            "headless": browser_config.headless,
            "user_agent": browser_config.user_agent,
            "locale": browser_config.locale,
            "timezone_id": browser_config.timezone_id,
            "viewport": {
                "width": browser_config.viewport[0],
                "height": browser_config.viewport[1],
            },
        },
        "targets": {
            "file_name": target_file.name,
            "sha256": _sha256_bytes(target_bytes),
            "count": target_count,
        },
    }


def write_run_manifest(
    run_directory: Path,
    *,
    started_at: datetime,
    target_file: Path,
    target_count: int,
    model_config: ModelConfig,
    agent_config: AgentConfig,
    browser_config: BrowserConfig,
) -> Path:
    """Write one run's reproducibility metadata to run_manifest.json."""
    if not run_directory.is_dir():
        raise FileNotFoundError(f"run directory does not exist: {run_directory}")

    manifest = build_run_manifest(
        started_at=started_at,
        target_file=target_file,
        target_count=target_count,
        model_config=model_config,
        agent_config=agent_config,
        browser_config=browser_config,
    )
    manifest_path = run_directory / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path
