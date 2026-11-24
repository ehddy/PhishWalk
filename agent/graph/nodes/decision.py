"""Decision node boundary for the PhishWalk graph."""

from langchain_core.messages import UsageMetadata
from langgraph.runtime import Runtime
from typing_extensions import NotRequired, TypedDict

from agent.action import ActionPlan
from agent.decision import decide_action_plan
from agent.graph.runtime import PhishWalkRuntime
from agent.graph.state import ModelCallTokenUsage, PhishWalkState, ValidationFailure


class DecisionNodeUpdate(TypedDict):
    """State fields updated by one model call."""

    action_plan: ActionPlan | None
    model_call_count: int
    validation_retry_count: int
    model_call_token_usage: list[ModelCallTokenUsage]
    total_token_usage: dict[str, UsageMetadata]
    last_error: NotRequired[str]
    validation_failures: NotRequired[list[ValidationFailure]]


def _merge_usage_metadata(
    current: UsageMetadata,
    new: UsageMetadata,
) -> UsageMetadata:
    """Add the standard input, output, and total token counts."""
    return {
        "input_tokens": current["input_tokens"] + new["input_tokens"],
        "output_tokens": current["output_tokens"] + new["output_tokens"],
        "total_tokens": current["total_tokens"] + new["total_tokens"],
    }


async def decision_node(
    state: PhishWalkState,
    runtime: Runtime[PhishWalkRuntime],
) -> DecisionNodeUpdate:
    """Produce the next action plan and update model token usage."""
    phishwalk_runtime = runtime.context
    if phishwalk_runtime is None:
        raise RuntimeError("PhishWalk runtime context is unavailable")

    observation = state.get("current_observation")
    dialog_observation = state.get("dialog_observation")
    if observation is None and dialog_observation is None:
        raise RuntimeError("page and dialog observations are unavailable")

    decision_result = await decide_action_plan(
        phishwalk_runtime.model,
        observation,
        state.get("last_error"),
        target_url=state["target_url"],
        dialog_observation=dialog_observation,
        change_observation=state.get("change_observation"),
        interaction_history=state.get("interaction_history"),
        observation_error=state.get("observation_error"),
        config=phishwalk_runtime.agent_config,
    )

    raw_message = decision_result.raw_message
    raw_usage = raw_message.usage_metadata
    usage: UsageMetadata | None = (
        {
            "input_tokens": raw_usage["input_tokens"],
            "output_tokens": raw_usage["output_tokens"],
            "total_tokens": raw_usage["total_tokens"],
        }
        if raw_usage is not None
        else None
    )
    model_identifier = (
        f"{phishwalk_runtime.model_provider}/"
        f"{phishwalk_runtime.model_name}"
    )

    usage_by_model = {model_identifier: usage} if usage is not None else {}
    model_call_count = state.get("model_call_count", 0) + 1
    action_plan_step = (
        state.get("action_plan_step_count", 0) + 1
        if decision_result.action_plan is not None
        else None
    )
    call_usage: ModelCallTokenUsage = {
        "model_call_index": model_call_count,
        "action_plan_step": action_plan_step,
        "usage_by_model": usage_by_model,
    }
    model_call_token_usage = [
        *state.get("model_call_token_usage", []),
        call_usage,
    ]

    total_token_usage = dict(state.get("total_token_usage", {}))
    if usage is not None:
        current_total = total_token_usage.get(model_identifier)
        total_token_usage[model_identifier] = (
            _merge_usage_metadata(current_total, usage)
            if current_total is not None
            else usage
        )

    update: DecisionNodeUpdate = {
        "action_plan": decision_result.action_plan,
        "model_call_count": model_call_count,
        "validation_retry_count": 0,
        "model_call_token_usage": model_call_token_usage,
        "total_token_usage": total_token_usage,
    }

    validation_error = decision_result.validation_error
    if validation_error is not None:
        validation_failure: ValidationFailure = {
            "model_call_index": model_call_count,
            "error": validation_error,
        }
        update.update(
            {
                "validation_retry_count": (
                    state.get("validation_retry_count", 0) + 1
                ),
                "last_error": validation_error,
                "validation_failures": [
                    *state.get("validation_failures", []),
                    validation_failure,
                ],
            }
        )
    elif decision_result.action_plan is None:
        raise RuntimeError("validated decision is missing its action plan")

    return update
