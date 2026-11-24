"""Sequential batch execution for PhishWalk target URLs."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from langchain.chat_models import BaseChatModel

from agent.browser.config import BrowserConfig
from agent.config import AgentConfig
from agent.experiment.paths import create_run_directory
from agent.experiment.paths import build_target_directory_name
from agent.experiment.run_result import TargetRunResult
from agent.experiment.run_manifest import write_run_manifest
from agent.experiment.result_writer import (
    append_target_result,
    write_pretty_results,
)
from agent.graph.runner import run_target
from agent.model import ModelConfig


async def run_batch(
    *,
    target_file: Path,
    artifact_root: Path,
    model: BaseChatModel,
    model_config: ModelConfig,
    agent_config: AgentConfig,
    browser_config: BrowserConfig,
) -> Path:
    """Run PhishWalk sequentially for URLs listed in one text file."""
    try:
        target_lines = target_file.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise RuntimeError(f"failed to read target file: {target_file}") from error

    target_urls = [
        line.strip()
        for line in target_lines
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not target_urls:
        raise ValueError(f"target file contains no URLs: {target_file}")

    started_at = datetime.now(timezone.utc)
    run_directory = create_run_directory(artifact_root, started_at=started_at)
    write_run_manifest(
        run_directory,
        started_at=started_at,
        target_file=target_file,
        target_count=len(target_urls),
        model_config=model_config,
        agent_config=agent_config,
        browser_config=browser_config,
    )
    print(f"Run artifacts: {run_directory.resolve()}", flush=True)

    total_targets = len(target_urls)
    for target_index, target_url in enumerate(target_urls, start=1):
        target_started_at = perf_counter()
        try:
            result = await asyncio.wait_for(
                run_target(
                    target_url=target_url,
                    target_index=target_index,
                    run_directory=run_directory,
                    model=model,
                    model_config=model_config,
                    agent_config=agent_config,
                    browser_config=browser_config,
                ),
                timeout=agent_config.target_timeout_seconds,
            )
        except TimeoutError:
            target_id = build_target_directory_name(target_index, target_url)
            timeout_seconds = agent_config.target_timeout_seconds
            result = TargetRunResult(
                target_id=target_id,
                target_url=target_url,
                status="failed",
                error=(
                    "TargetTimeoutError: exceeded "
                    f"{timeout_seconds:g} seconds"
                ),
                artifact_directory=target_id,
            )
        elapsed_seconds = round(perf_counter() - target_started_at, 3)
        result = result.model_copy(
            update={"elapsed_seconds": elapsed_seconds},
        )
        append_target_result(run_directory, result)
        print(
            f"[{target_index}/{total_targets}] "
            f"{result.status} {elapsed_seconds:.3f}s {target_url}",
            flush=True,
        )

    write_pretty_results(run_directory)
    return run_directory
