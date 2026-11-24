"""Single-target execution boundary for the PhishWalk graph."""

import asyncio
from contextlib import suppress
from pathlib import Path
from typing import cast

from langchain.chat_models import BaseChatModel
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from agent.browser.config import BrowserConfig
from agent.browser.dialog import PendingBrowserOperation
from agent.browser.session import open_browser_session
from agent.config import AgentConfig
from agent.experiment.paths import create_target_directory
from agent.experiment.run_result import (
    TargetRunResult,
    build_action_plan_steps,
    count_completed_browser_actions,
    infer_termination_reason,
)
from agent.graph.builder import build_one_shot_graph, build_phishwalk_graph
from agent.graph.runtime import PhishWalkRuntime
from agent.graph.state import PhishWalkState
from agent.model import ModelConfig


NAVIGATION_TIMEOUT_MILLISECONDS = 60_000
INITIAL_RENDER_TIMEOUT_MILLISECONDS = 15_000
INITIAL_RENDER_SETTLE_MILLISECONDS = 1_000


async def _cancel_pending_browser_operation(
    runtime: PhishWalkRuntime,
) -> None:
    """Cancel a browser operation left blocked by an unhandled native dialog."""
    pending_operation = runtime.dialog.pending_operation
    if pending_operation is None:
        return
    if not pending_operation.task.done():
        pending_operation.task.cancel()
    with suppress(asyncio.CancelledError, Exception):
        await pending_operation.task
    runtime.dialog.pending_operation = None


async def _navigate_and_wait_for_initial_render(page: Page, target_url: str) -> None:
    """Navigate and wait for bounded, meaningful initial page rendering."""
    await page.goto(
        target_url,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT_MILLISECONDS,
    )

    try:
        await page.wait_for_function(
            """() => {
                const body = document.body;
                if (!body) return false;
                if ((body.innerText || "").trim().length > 0) return true;

                const candidates = body.querySelectorAll(
                    "img, svg, canvas, video, input, button, select, " +
                    "textarea, a, [role]"
                );
                return Array.from(candidates).some((element) => {
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return (
                        style.display !== "none" &&
                        style.visibility !== "hidden" &&
                        Number.parseFloat(style.opacity) > 0 &&
                        rect.width > 0 &&
                        rect.height > 0
                    );
                });
            }""",
            timeout=INITIAL_RENDER_TIMEOUT_MILLISECONDS,
        )
    except PlaywrightTimeoutError as error:
        raise RuntimeError(
            "initial page did not render meaningful content within "
            f"{INITIAL_RENDER_TIMEOUT_MILLISECONDS // 1000} seconds"
        ) from error

    await page.wait_for_timeout(INITIAL_RENDER_SETTLE_MILLISECONDS)


async def run_target(
    *,
    target_url: str,
    target_index: int,
    run_directory: Path,
    model: BaseChatModel,
    model_config: ModelConfig,
    agent_config: AgentConfig,
    browser_config: BrowserConfig,
) -> TargetRunResult:
    """Run PhishWalk for one URL and return its persisted result record."""
    target_directory = create_target_directory(
        run_directory,
        target_index,
        target_url,
    )
    target_id = target_directory.name
    phishwalk_runtime: PhishWalkRuntime | None = None

    try:
        async with open_browser_session(browser_config) as page:
            phishwalk_runtime = PhishWalkRuntime(
                active_page=page,
                output_directory=target_directory,
                model=model,
                model_provider=model_config.provider,
                model_name=model_config.model,
                agent_config=agent_config,
            )
            dialog_listener = phishwalk_runtime.dialog.record
            page.context.on("dialog", dialog_listener)

            navigation_task = asyncio.create_task(
                _navigate_and_wait_for_initial_render(page, target_url)
            )
            dialog_task = asyncio.create_task(
                phishwalk_runtime.dialog.detected.wait()
            )
            try:
                done, _ = await asyncio.wait(
                    {navigation_task, dialog_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if dialog_task in done:
                    phishwalk_runtime.dialog.pending_operation = (
                        PendingBrowserOperation(
                            kind="navigation",
                            task=navigation_task,
                        )
                    )
                else:
                    dialog_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await dialog_task
                    await navigation_task

                graph = (
                    build_one_shot_graph()
                    if agent_config.traversal_policy == "one_shot"
                    else build_phishwalk_graph()
                )
                final_state = cast(
                    PhishWalkState,
                    await graph.ainvoke(
                        {"target_url": target_url},
                        context=phishwalk_runtime,
                    ),
                )
                final_url = phishwalk_runtime.active_page.url
            finally:
                if agent_config.traversal_policy == "one_shot":
                    await _cancel_pending_browser_operation(phishwalk_runtime)
                page.context.remove_listener("dialog", dialog_listener)
    except Exception as error:
        return TargetRunResult(
            target_id=target_id,
            target_url=target_url,
            status="failed",
            error=f"{type(error).__name__}: {error}",
            observation_count=(
                phishwalk_runtime.observation_count
                if phishwalk_runtime is not None
                else 0
            ),
            artifact_directory=target_id,
        )

    detection_result = final_state.get("detection_result")
    interaction_history = final_state.get("interaction_history", [])
    validation_retries_exhausted = (
        final_state.get("validation_retry_count", 0)
        > agent_config.max_validation_retries
    )
    if detection_result is None:
        return TargetRunResult(
            target_id=target_id,
            target_url=target_url,
            final_url=final_url,
            status="failed",
            error=(
                "RuntimeError: graph completed without a final detection result"
            ),
            observation_count=phishwalk_runtime.observation_count,
            model_call_count=final_state.get("model_call_count", 0),
            action_plan_step_count=final_state.get(
                "action_plan_step_count", 0
            ),
            interaction_plan_count=final_state.get(
                "interaction_plan_count", 0
            ),
            completed_browser_action_count=count_completed_browser_actions(
                interaction_history
            ),
            action_plan_steps=build_action_plan_steps(interaction_history),
            validation_failures=final_state.get("validation_failures", []),
            model_call_token_usage=final_state.get(
                "model_call_token_usage", []
            ),
            total_token_usage=final_state.get("total_token_usage", {}),
            artifact_directory=target_id,
        )

    return TargetRunResult(
        target_id=target_id,
        target_url=target_url,
        final_url=final_url,
        status="completed",
        is_phishing=detection_result.is_phishing,
        reason=detection_result.reason,
        termination_reason=(
            "one_shot"
            if agent_config.traversal_policy == "one_shot"
            else infer_termination_reason(
                interaction_history,
                validation_retries_exhausted=validation_retries_exhausted,
            )
        ),
        observation_count=phishwalk_runtime.observation_count,
        model_call_count=final_state.get("model_call_count", 0),
        action_plan_step_count=final_state.get("action_plan_step_count", 0),
        interaction_plan_count=final_state.get("interaction_plan_count", 0),
        completed_browser_action_count=count_completed_browser_actions(
            interaction_history
        ),
        action_plan_steps=build_action_plan_steps(interaction_history),
        validation_failures=final_state.get("validation_failures", []),
        model_call_token_usage=final_state.get("model_call_token_usage", []),
        total_token_usage=final_state.get("total_token_usage", {}),
        artifact_directory=target_id,
    )
