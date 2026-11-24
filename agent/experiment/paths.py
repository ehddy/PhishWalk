"""Path naming helpers for PhishWalk experiment artifacts."""

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def build_target_directory_name(target_index: int, target_url: str) -> str:
    """Return a stable, filesystem-safe directory name for one target URL."""
    if target_index < 1:
        raise ValueError("target_index must be at least 1")

    hostname = urlsplit(target_url).hostname or "unknown-host"
    hostname_slug = re.sub(r"[^a-z0-9]+", "-", hostname.lower()).strip("-")
    hostname_slug = hostname_slug[:48] or "unknown-host"
    url_hash = hashlib.sha256(target_url.encode("utf-8")).hexdigest()[:8]

    return f"{target_index:06d}_{hostname_slug}_{url_hash}"


def create_run_directory(
    artifact_root: Path,
    started_at: datetime | None = None,
) -> Path:
    """Create and return a timestamped PhishWalk experiment directory."""
    run_time = started_at or datetime.now(timezone.utc)
    if run_time.tzinfo is None:
        raise ValueError("started_at must include timezone information")

    utc_run_time = run_time.astimezone(timezone.utc)
    run_directory = (
        artifact_root
        / "phishwalk"
        / f"run_{utc_run_time:%Y%m%dT%H%M%S%fZ}"
    )
    run_directory.mkdir(parents=True, exist_ok=False)
    return run_directory


def create_target_directory(
    run_directory: Path,
    target_index: int,
    target_url: str,
) -> Path:
    """Create and return the artifact directory for one target URL."""
    target_directory = run_directory / build_target_directory_name(
        target_index,
        target_url,
    )
    target_directory.mkdir(parents=False, exist_ok=False)
    return target_directory


def create_observation_directory(
    target_directory: Path,
    observation_index: int,
) -> Path:
    """Create and return the artifact directory for one page observation."""
    if observation_index < 0:
        raise ValueError("observation_index must be at least 0")
    if not target_directory.is_dir():
        raise FileNotFoundError(
            f"target directory does not exist: {target_directory}"
        )

    observation_directory = (
        target_directory / f"observation_{observation_index:03d}"
    )
    observation_directory.mkdir(parents=False, exist_ok=False)
    return observation_directory
