"""Conditional routing decisions for the PhishWalk graph."""

from typing import Literal

from langgraph.runtime import Runtime

from agent.graph.runtime import PhishWalkRuntime
from agent.graph.state import PhishWalkState


def route_after_one_shot_decision(
    state: PhishWalkState,
    runtime: Runtime[PhishWalkRuntime],
) -> Literal["one_shot_decision", "end"]:
    """Retry invalid one-shot output within its validation budget."""
    phishwalk_runtime = runtime.context
    if phishwalk_runtime is None:
        raise RuntimeError("PhishWalk runtime context is unavailable")
    if state.get("detection_result") is not None:
        return "end"
    if (
        state.get("validation_retry_count", 0)
        > phishwalk_runtime.agent_config.max_validation_retries
    ):
        return "end"
    return "one_shot_decision"


def route_after_decision(
    state: PhishWalkState,
    runtime: Runtime[PhishWalkRuntime],
) -> Literal["act", "decision", "final_observe"]:
    """Execute valid plans, retry invalid decisions, or finalize at the limit."""
    phishwalk_runtime = runtime.context
    if phishwalk_runtime is None:
        raise RuntimeError("PhishWalk runtime context is unavailable")

    if state.get("action_plan") is not None:
        return "act"

    if (
        state.get("action_plan_step_count", 0)
        >= phishwalk_runtime.agent_config.max_action_plan_steps
        or state.get("validation_retry_count", 0)
        > phishwalk_runtime.agent_config.max_validation_retries
    ):
        return "final_observe"

    return "decision"


def route_after_act(
    state: PhishWalkState,
    runtime: Runtime[PhishWalkRuntime],
) -> Literal["observe", "final_observe", "end"]:
    """End completed runs and send exhausted runs to final observation."""
    phishwalk_runtime = runtime.context
    if phishwalk_runtime is None:
        raise RuntimeError("PhishWalk runtime context is unavailable")

    if state.get("detection_result") is not None:
        return "end"

    if (
        state.get("action_plan_step_count", 0)
        >= phishwalk_runtime.agent_config.max_action_plan_steps
    ):
        return "final_observe"

    return "observe"
