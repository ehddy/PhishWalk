"""Test run manifests, per-target elapsed time, and progress output."""

import asyncio
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from agent.browser.config import BrowserConfig
from agent.config import AgentConfig
from agent.experiment.batch_runner import run_batch
from agent.experiment.run_result import TargetRunResult
from agent.model import ModelConfig


async def _fake_run_target(**arguments: object) -> TargetRunResult:
    target_index = int(arguments["target_index"])
    target_url = str(arguments["target_url"])
    return TargetRunResult(
        target_id=f"target-{target_index}",
        target_url=target_url,
        final_url=target_url,
        status="completed",
        is_phishing=False,
        reason="Synthetic test result.",
        model_call_count=1,
        action_plan_step_count=1,
        interaction_plan_count=1,
        completed_browser_action_count=1,
        artifact_directory=f"target-{target_index}",
    )


async def _slow_run_target(**arguments: object) -> TargetRunResult:
    await asyncio.sleep(1)
    raise AssertionError("target timeout did not interrupt the run")


async def main() -> None:
    with TemporaryDirectory() as directory:
        temporary_root = Path(directory)
        target_file = temporary_root / "pilot-targets.txt"
        target_file.write_text(
            "# test targets\nhttps://one.example/\nhttps://two.example/\n",
            encoding="utf-8",
        )

        output = StringIO()
        with (
            patch(
                "agent.experiment.batch_runner.run_target",
                side_effect=_fake_run_target,
            ),
            redirect_stdout(output),
        ):
            run_directory = await run_batch(
                target_file=target_file,
                artifact_root=temporary_root / "artifacts",
                model=MagicMock(),
                model_config=ModelConfig(
                    provider="openai",
                    model="test-model",
                    temperature=0.0,
                ),
                agent_config=AgentConfig(
                    traversal_policy="generic",
                    max_action_plan_steps=3,
                    max_validation_retries=2,
                    target_timeout_seconds=30,
                    enabled_actions=("click", "scroll"),
                ),
                browser_config=BrowserConfig(
                    headless=True,
                    locale="en-US",
                    timezone_id="UTC",
                    viewport=(1280, 720),
                ),
            )

        manifest = json.loads(
            (run_directory / "run_manifest.json").read_text(encoding="utf-8")
        )
        if manifest["model"] != {
            "provider": "openai",
            "name": "test-model",
            "temperature": 0.0,
        }:
            raise AssertionError("model configuration was not recorded")
        if manifest["agent"] != {
            "traversal_policy": "generic",
            "max_interactive_elements": 100,
            "max_visible_text_chars": 4000,
            "max_change_text_items": 50,
            "max_change_element_items": 50,
            "max_action_plan_steps": 3,
            "max_validation_retries": 2,
            "target_timeout_seconds": 30,
            "enabled_actions": ["click", "scroll"],
        }:
            raise AssertionError("agent configuration was not recorded")
        if manifest["targets"]["count"] != 2:
            raise AssertionError("target count was not recorded")
        if not manifest["targets"]["sha256"].startswith("sha256:"):
            raise AssertionError("target hash was not recorded")
        if not manifest["prompt"]["sha256"].startswith("sha256:"):
            raise AssertionError("prompt hash was not recorded")
        if "api_key" in json.dumps(manifest).lower():
            raise AssertionError("manifest contains credential-related fields")

        results = json.loads(
            (run_directory / "results.json").read_text(encoding="utf-8")
        )
        if len(results) != 2:
            raise AssertionError("unexpected number of persisted results")
        if any(result["elapsed_seconds"] is None for result in results):
            raise AssertionError("per-target elapsed time was not recorded")
        if any(result["completed_browser_action_count"] != 1 for result in results):
            raise AssertionError("completed browser action count was not recorded")
        if any("confidence" in result for result in results):
            raise AssertionError("removed confidence field was persisted")

        progress_output = output.getvalue()
        if "Run artifacts:" not in progress_output:
            raise AssertionError("run directory was not printed at startup")
        if "[1/2] completed" not in progress_output:
            raise AssertionError("first target progress was not printed")
        if "[2/2] completed" not in progress_output:
            raise AssertionError("second target progress was not printed")

        timeout_target_file = temporary_root / "timeout-target.txt"
        timeout_target_file.write_text(
            "https://slow.example/\n",
            encoding="utf-8",
        )
        with patch(
            "agent.experiment.batch_runner.run_target",
            side_effect=_slow_run_target,
        ):
            timeout_run_directory = await run_batch(
                target_file=timeout_target_file,
                artifact_root=temporary_root / "timeout-artifacts",
                model=MagicMock(),
                model_config=ModelConfig(
                    provider="openai",
                    model="test-model",
                    temperature=0.0,
                ),
                agent_config=AgentConfig(target_timeout_seconds=0.01),
                browser_config=BrowserConfig(headless=True),
            )

        timeout_results = json.loads(
            (timeout_run_directory / "results.json").read_text(encoding="utf-8")
        )
        timeout_result = timeout_results[0]
        if timeout_result["status"] != "failed":
            raise AssertionError("timed-out target was not marked as failed")
        if "TargetTimeoutError" not in timeout_result["error"]:
            raise AssertionError("target timeout error was not recorded")

    print("run metadata checks passed")


if __name__ == "__main__":
    asyncio.run(main())
