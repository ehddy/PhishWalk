"""Mandatory final-verdict node for exhausted interaction budgets."""

from langchain_core.messages import UsageMetadata
from langgraph.runtime import Runtime
from typing_extensions import TypedDict

from agent.decision import decide_final_result
from agent.detection import DetectionResult
from agent.graph.runtime import PhishWalkRuntime
from agent.graph.state import ModelCallTokenUsage, PhishWalkState


class FinalizeNodeUpdate(TypedDict):
    """State fields updated by the mandatory final-verdict call."""

    detection_result: DetectionResult
    model_call_count: int
    model_call_token_usage: list[ModelCallTokenUsage]
    total_token_usage: dict[str, UsageMetadata]


async def finalize_node(
    state: PhishWalkState,
    runtime: Runtime[PhishWalkRuntime],
) -> FinalizeNodeUpdate:
    """Produce a final verdict and include its model usage in run totals."""
    phishwalk_runtime = runtime.context
    if phishwalk_runtime is None:
        raise RuntimeError("PhishWalk runtime context is unavailable")

    observation = state.get("current_observation")
    dialog_observation = state.get("dialog_observation")
    if observation is None and dialog_observation is None:
        raise RuntimeError("page and dialog observations are unavailable")

    final_result = await decide_final_result(
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

    raw_usage = final_result.raw_message.usage_metadata
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
    final_call_usage: ModelCallTokenUsage = {
        "model_call_index": model_call_count,
        "action_plan_step": None,
        "usage_by_model": usage_by_model,
    }
    model_call_token_usage = [
        *state.get("model_call_token_usage", []),
        final_call_usage,
    ]

    total_token_usage = dict(state.get("total_token_usage", {}))
    if usage is not None:
        current_total = total_token_usage.get(model_identifier)
        total_token_usage[model_identifier] = (
            {
                "input_tokens": current_total["input_tokens"]
                + usage["input_tokens"],
                "output_tokens": current_total["output_tokens"]
                + usage["output_tokens"],
                "total_tokens": current_total["total_tokens"]
                + usage["total_tokens"],
            }
            if current_total is not None
            else usage
        )

    return {
        "detection_result": final_result.detection_result,
        "model_call_count": model_call_count,
        "model_call_token_usage": model_call_token_usage,
        "total_token_usage": total_token_usage,
    }
