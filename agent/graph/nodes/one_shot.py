"""Direct one-shot classification node without browser actions."""

from langchain_core.messages import UsageMetadata
from langgraph.runtime import Runtime
from typing_extensions import NotRequired, TypedDict

from agent.decision import decide_one_shot_result
from agent.detection import DetectionResult
from agent.graph.runtime import PhishWalkRuntime
from agent.graph.state import ModelCallTokenUsage, PhishWalkState, ValidationFailure


class OneShotNodeUpdate(TypedDict):
    """State fields updated by one logical one-shot model invocation."""

    detection_result: NotRequired[DetectionResult]
    model_call_count: int
    validation_retry_count: int
    model_call_token_usage: list[ModelCallTokenUsage]
    total_token_usage: dict[str, UsageMetadata]
    last_error: NotRequired[str]
    validation_failures: NotRequired[list[ValidationFailure]]


async def one_shot_decision_node(
    state: PhishWalkState,
    runtime: Runtime[PhishWalkRuntime],
) -> OneShotNodeUpdate:
    """Classify the initial observation and account for one logical call."""
    phishwalk_runtime = runtime.context
    if phishwalk_runtime is None:
        raise RuntimeError("PhishWalk runtime context is unavailable")

    observation = state.get("current_observation")
    dialog_observation = state.get("dialog_observation")
    if observation is None and dialog_observation is None:
        raise RuntimeError("page and dialog observations are unavailable")

    decision = await decide_one_shot_result(
        phishwalk_runtime.model,
        observation,
        state.get("last_error"),
        target_url=state["target_url"],
        dialog_observation=dialog_observation,
        observation_error=state.get("observation_error"),
        config=phishwalk_runtime.agent_config,
    )
    raw_usage = decision.raw_message.usage_metadata
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
        f"{phishwalk_runtime.model_provider}/{phishwalk_runtime.model_name}"
    )
    model_call_count = state.get("model_call_count", 0) + 1
    call_usage: ModelCallTokenUsage = {
        "model_call_index": model_call_count,
        "action_plan_step": None,
        "usage_by_model": (
            {model_identifier: usage} if usage is not None else {}
        ),
    }
    total_token_usage = dict(state.get("total_token_usage", {}))
    if usage is not None:
        current = total_token_usage.get(model_identifier)
        total_token_usage[model_identifier] = (
            {
                "input_tokens": current["input_tokens"] + usage["input_tokens"],
                "output_tokens": current["output_tokens"] + usage["output_tokens"],
                "total_tokens": current["total_tokens"] + usage["total_tokens"],
            }
            if current is not None
            else usage
        )

    update: OneShotNodeUpdate = {
        "model_call_count": model_call_count,
        "validation_retry_count": 0,
        "model_call_token_usage": [
            *state.get("model_call_token_usage", []),
            call_usage,
        ],
        "total_token_usage": total_token_usage,
    }
    if decision.validation_error is not None:
        failure: ValidationFailure = {
            "model_call_index": model_call_count,
            "error": decision.validation_error,
        }
        update.update(
            {
                "validation_retry_count": (
                    state.get("validation_retry_count", 0) + 1
                ),
                "last_error": decision.validation_error,
                "validation_failures": [
                    *state.get("validation_failures", []),
                    failure,
                ],
            }
        )
    elif decision.detection_result is not None:
        update["detection_result"] = decision.detection_result
    else:
        raise RuntimeError("validated one-shot decision is missing its result")
    return update
