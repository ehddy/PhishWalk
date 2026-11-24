"""Observation node boundary for the PhishWalk graph."""

import asyncio
from contextlib import suppress

from langgraph.runtime import Runtime
from playwright.async_api import Error as PlaywrightError
from typing_extensions import NotRequired, TypedDict

from agent.browser.dialog import DialogObservation
from agent.change_observation import ChangeObservation, compare_observations
from agent.experiment.paths import create_observation_directory
from agent.graph.runtime import PhishWalkRuntime
from agent.graph.state import InteractionRecord, PhishWalkState
from agent.tools.evidence_collection.observation import (
    PageObservation,
    collect_page_observation,
)


class ObserveNodeUpdate(TypedDict):
    """State fields updated after collecting one page observation."""

    current_observation: NotRequired[PageObservation]
    dialog_observation: NotRequired[DialogObservation]
    change_observation: NotRequired[ChangeObservation]
    interaction_history: NotRequired[list[InteractionRecord]]
    observation_error: NotRequired[str | None]


async def observe_node(
    state: PhishWalkState,
    runtime: Runtime[PhishWalkRuntime],
) -> ObserveNodeUpdate:
    """Collect the active page observation and return its state update."""
    phishwalk_runtime = runtime.context
    if phishwalk_runtime is None:
        raise RuntimeError("PhishWalk runtime context is unavailable")

    if phishwalk_runtime.dialog.pending_dialog is not None:
        observation = state.get("current_observation")
        dialog_observation = phishwalk_runtime.dialog.observation
        if dialog_observation is None:
            raise RuntimeError("pending dialog observation is unavailable")
        if (
            phishwalk_runtime.agent_config.traversal_policy == "one_shot"
            and observation is None
            and phishwalk_runtime.observation_count == 0
        ):
            # A native dialog can block the first screenshot. In One-shot the
            # dialog itself is the single observable initial browser state.
            phishwalk_runtime.observation_count = 1

        update: ObserveNodeUpdate = {
            "dialog_observation": dialog_observation,
        }
        if observation is not None:
            update["current_observation"] = observation
        return update

    observation_index = phishwalk_runtime.observation_count
    phishwalk_runtime.observation_count += 1
    observation_directory = create_observation_directory(
        phishwalk_runtime.output_directory,
        observation_index,
    )
    phishwalk_runtime.dialog.detected.clear()
    observation_task = asyncio.create_task(
        collect_page_observation(
            phishwalk_runtime.active_page,
            observation_directory,
        )
    )
    dialog_task = asyncio.create_task(
        phishwalk_runtime.dialog.detected.wait()
    )
    done, _ = await asyncio.wait(
        {observation_task, dialog_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if dialog_task in done:
        observation_task.cancel()
        with suppress(asyncio.CancelledError):
            await observation_task

        dialog_observation = phishwalk_runtime.dialog.observation
        if dialog_observation is None:
            raise RuntimeError("detected dialog observation is unavailable")

        update: ObserveNodeUpdate = {
            "dialog_observation": dialog_observation,
        }
        previous_observation = state.get("current_observation")
        if previous_observation is not None:
            update["current_observation"] = previous_observation
        return update

    dialog_task.cancel()
    with suppress(asyncio.CancelledError):
        await dialog_task

    previous_observation = state.get("current_observation")

    try:
        observation = await observation_task
    except PlaywrightError as error:
        if previous_observation is None:
            raise

        interaction_history = state.get("interaction_history", [])
        update: ObserveNodeUpdate = {
            "current_observation": previous_observation,
            "observation_error": str(error),
        }
        if interaction_history:
            latest_record: InteractionRecord = {
                **interaction_history[-1],
                "observation_error": str(error),
            }
            update["interaction_history"] = [
                *interaction_history[:-1],
                latest_record,
            ]
        return update

    update: ObserveNodeUpdate = {
        "current_observation": observation,
        "observation_error": None,
    }

    if previous_observation is None:
        return update

    change_observation = compare_observations(
        previous_observation,
        observation,
    )
    update["change_observation"] = change_observation

    interaction_history = state.get("interaction_history", [])
    if interaction_history:
        latest_record: InteractionRecord = {
            **interaction_history[-1],
            "change_observation": change_observation,
        }
        update["interaction_history"] = [
            *interaction_history[:-1],
            latest_record,
        ]

    return update
