"""Action-execution node boundary for the PhishWalk graph."""

import asyncio
from contextlib import suppress
from typing import cast

from langgraph.runtime import Runtime
from playwright.async_api import Error as PlaywrightError
from typing_extensions import NotRequired, TypedDict

from agent.action import FinishAction, HandleDialogAction
from agent.browser.dialog import (
    DialogObservation,
    PendingBrowserOperation,
)
from agent.detection import DetectionResult
from agent.graph.runtime import PhishWalkRuntime
from agent.graph.state import InteractionRecord, PhishWalkState
from agent.tools.traversal.executor import (
    ActionExecutionResult,
    execute_action_plan,
)


PENDING_ACTION_TIMEOUT_SECONDS = 10.0


class ActNodeUpdate(TypedDict):
    """State fields updated after executing one action plan."""

    action_plan_step_count: int
    interaction_plan_count: int
    last_error: str | None
    interaction_history: list[InteractionRecord]
    dialog_observation: NotRequired[DialogObservation | None]
    detection_result: NotRequired[DetectionResult]


async def _wait_for_execution_or_dialog(
    execution_task: asyncio.Task[ActionExecutionResult],
    phishwalk_runtime: PhishWalkRuntime,
) -> ActionExecutionResult | None:
    """Return an action result, or preserve its task when a dialog appears."""
    dialog_task = asyncio.create_task(phishwalk_runtime.dialog.detected.wait())
    done, _ = await asyncio.wait(
        {execution_task, dialog_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if execution_task in done:
        dialog_task.cancel()
        with suppress(asyncio.CancelledError):
            await dialog_task
        return await execution_task

    phishwalk_runtime.dialog.pending_operation = PendingBrowserOperation(
        kind="action",
        task=execution_task,
    )
    return None


async def act_node(
    state: PhishWalkState,
    runtime: Runtime[PhishWalkRuntime],
) -> ActNodeUpdate:
    """Execute the current action plan and return its state updates."""
    phishwalk_runtime = runtime.context
    if phishwalk_runtime is None:
        raise RuntimeError("PhishWalk runtime context is unavailable")

    observation = state.get("current_observation")
    action_plan = state.get("action_plan")
    if action_plan is None:
        raise RuntimeError("action plan is unavailable")

    handles_dialog = isinstance(action_plan.actions[0], HandleDialogAction)
    is_interaction = not isinstance(action_plan.actions[0], FinishAction)
    if observation is None and not handles_dialog:
        raise RuntimeError("current observation is unavailable")

    if phishwalk_runtime.dialog.pending_dialog is not None and not handles_dialog:
        error = (
            "A browser dialog is pending; select handle_dialog before any "
            "other browser action."
        )
        next_action_plan_step = state.get("action_plan_step_count", 0) + 1
        next_interaction_plan = state.get("interaction_plan_count", 0) + int(
            is_interaction
        )
        interaction_record: InteractionRecord = {
            "action_plan_step": next_action_plan_step,
            "action_plan": action_plan,
            "completed_actions": 0,
            "succeeded": False,
            "error": error,
        }
        return {
            "action_plan_step_count": next_action_plan_step,
            "interaction_plan_count": next_interaction_plan,
            "last_error": error,
            "interaction_history": [
                *state.get("interaction_history", []),
                interaction_record,
            ],
            "dialog_observation": phishwalk_runtime.dialog.observation,
        }

    dialog_handled = False
    handled_dialog_observation = None
    resumed_action_result: ActionExecutionResult | None = None
    if handles_dialog:
        handled_dialog_observation = phishwalk_runtime.dialog.observation
        execution_result = await execute_action_plan(
            phishwalk_runtime.active_page,
            observation,
            action_plan,
            pending_dialog=phishwalk_runtime.dialog.pending_dialog,
        )
        phishwalk_runtime.active_page = execution_result.active_page

        if execution_result.error is None:
            phishwalk_runtime.dialog.clear()
            dialog_handled = True
            pending_operation = phishwalk_runtime.dialog.pending_operation
            if pending_operation is not None:
                if pending_operation.kind == "action":
                    pending_action_task = cast(
                        asyncio.Task[ActionExecutionResult],
                        pending_operation.task,
                    )
                    try:
                        pending_result = await asyncio.wait_for(
                            pending_action_task,
                            timeout=PENDING_ACTION_TIMEOUT_SECONDS,
                        )
                    except TimeoutError:
                        execution_result = ActionExecutionResult(
                            active_page=phishwalk_runtime.active_page,
                            completed_actions=execution_result.completed_actions,
                            requires_observation=True,
                            error=(
                                "pending action timed out after dialog handling "
                                f"({PENDING_ACTION_TIMEOUT_SECONDS:g} seconds)"
                            ),
                            detection_result=None,
                        )
                    else:
                        resumed_action_result = pending_result
                        phishwalk_runtime.active_page = pending_result.active_page
                        if pending_result.error is not None:
                            execution_result = ActionExecutionResult(
                                active_page=pending_result.active_page,
                                completed_actions=(
                                    execution_result.completed_actions
                                ),
                                requires_observation=True,
                                error=(
                                    "pending action failed after dialog handling: "
                                    f"{pending_result.error}"
                                ),
                                detection_result=None,
                            )
                else:
                    try:
                        await pending_operation.task
                    except PlaywrightError as error:
                        execution_result = ActionExecutionResult(
                            active_page=phishwalk_runtime.active_page,
                            completed_actions=execution_result.completed_actions,
                            requires_observation=True,
                            error=(
                                "pending navigation failed after dialog handling: "
                                f"{error}"
                            ),
                            detection_result=None,
                        )
                phishwalk_runtime.dialog.pending_operation = None
    else:
        phishwalk_runtime.dialog.detected.clear()
        execution_task = asyncio.create_task(
            execute_action_plan(
                phishwalk_runtime.active_page,
                observation,
                action_plan,
            )
        )
        execution_result = await _wait_for_execution_or_dialog(
            execution_task,
            phishwalk_runtime,
        )

        if execution_result is None:
            next_action_plan_step = state.get("action_plan_step_count", 0) + 1
            next_interaction_plan = state.get(
                "interaction_plan_count", 0
            ) + int(is_interaction)
            interaction_record: InteractionRecord = {
                "action_plan_step": next_action_plan_step,
                "action_plan": action_plan,
                "completed_actions": 0,
                "succeeded": False,
                "error": None,
            }
            return {
                "action_plan_step_count": next_action_plan_step,
                "interaction_plan_count": next_interaction_plan,
                "last_error": None,
                "interaction_history": [
                    *state.get("interaction_history", []),
                    interaction_record,
                ],
                "dialog_observation": phishwalk_runtime.dialog.observation,
            }

        phishwalk_runtime.active_page = execution_result.active_page

    next_action_plan_step = state.get("action_plan_step_count", 0) + 1
    next_interaction_plan = state.get("interaction_plan_count", 0) + int(
        is_interaction
    )
    interaction_record: InteractionRecord = {
        "action_plan_step": next_action_plan_step,
        "action_plan": action_plan,
        "completed_actions": execution_result.completed_actions,
        "succeeded": execution_result.error is None,
        "error": execution_result.error,
    }
    if handled_dialog_observation is not None:
        interaction_record["dialog_observation"] = handled_dialog_observation

    previous_history = state.get("interaction_history", [])
    if resumed_action_result is not None and previous_history:
        resumed_record: InteractionRecord = {
            **previous_history[-1],
            "completed_actions": resumed_action_result.completed_actions,
            "succeeded": resumed_action_result.error is None,
            "error": resumed_action_result.error,
        }
        previous_history = [
            *previous_history[:-1],
            resumed_record,
        ]
    interaction_history = [
        *previous_history,
        interaction_record,
    ]

    update: ActNodeUpdate = {
        "action_plan_step_count": next_action_plan_step,
        "interaction_plan_count": next_interaction_plan,
        "last_error": execution_result.error,
        "interaction_history": interaction_history,
    }
    if execution_result.detection_result is not None:
        update["detection_result"] = execution_result.detection_result
    if dialog_handled:
        update["dialog_observation"] = None

    return update
