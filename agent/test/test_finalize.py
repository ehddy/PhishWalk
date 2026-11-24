"""Test mandatory finalization and token accounting without a live model."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage

from agent.action import ActionPlan, FinishAction
from agent.config import AgentConfig
from agent.detection import DetectionResult
from agent.experiment.run_result import (
    count_completed_browser_actions,
    infer_termination_reason,
)
from agent.graph.nodes.finalize import finalize_node


MODEL_IDENTIFIER = "openai/test-model"


async def main() -> None:
    model = MagicMock()
    model.get_lc_namespace.return_value = ["test"]
    structured_model = MagicMock()
    structured_model.ainvoke = AsyncMock(
        return_value={
            "parsed": DetectionResult(
                url="https://example.invalid",
                is_phishing=False,
                reason="Available evidence is insufficient to establish phishing.",
            ),
            "raw": AIMessage(
                content="",
                usage_metadata={
                    "input_tokens": 50,
                    "output_tokens": 10,
                    "total_tokens": 60,
                },
            ),
            "parsing_error": None,
        }
    )
    structured_model.with_retry.return_value = structured_model
    model.with_structured_output.return_value = structured_model

    runtime = SimpleNamespace(
        context=SimpleNamespace(
            model=model,
            model_provider="openai",
            model_name="test-model",
            agent_config=AgentConfig(max_action_plan_steps=5),
        )
    )
    state = {
        "target_url": "https://example.invalid",
        "dialog_observation": {
            "type": "alert",
            "message": "Verification pending",
            "default_value": "",
        },
        "action_plan_step_count": 5,
        "interaction_plan_count": 5,
        "model_call_count": 5,
        "model_call_token_usage": [
            {
                "model_call_index": 5,
                "action_plan_step": 5,
                "usage_by_model": {
                    MODEL_IDENTIFIER: {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "total_tokens": 120,
                    }
                },
            }
        ],
        "total_token_usage": {
            MODEL_IDENTIFIER: {
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
            }
        },
    }

    update = await finalize_node(state, runtime)

    schema = model.with_structured_output.call_args.args[0]
    if schema is not DetectionResult:
        raise AssertionError("finalization did not require DetectionResult")
    if update["detection_result"].is_phishing:
        raise AssertionError("unexpected final verdict")

    final_call_usage = update["model_call_token_usage"][-1]
    if final_call_usage["model_call_index"] != 6:
        raise AssertionError("finalization usage has the wrong call index")
    if final_call_usage["action_plan_step"] is not None:
        raise AssertionError("finalization was associated with an ActionPlan step")
    if final_call_usage["usage_by_model"][MODEL_IDENTIFIER]["total_tokens"] != 60:
        raise AssertionError("finalization usage was not recorded")
    if update["model_call_count"] != 6:
        raise AssertionError("finalization model call was not counted")

    total_usage = update["total_token_usage"][MODEL_IDENTIFIER]
    expected_total = {
        "input_tokens": 150,
        "output_tokens": 30,
        "total_tokens": 180,
    }
    if total_usage != expected_total:
        raise AssertionError(f"unexpected cumulative usage: {total_usage}")

    sent_messages = structured_model.ainvoke.call_args.args[0]
    if "no further browser actions are allowed" not in str(sent_messages).lower():
        raise AssertionError("finalization instruction was not sent")

    if infer_termination_reason([]) != "max_action_plan_steps":
        raise AssertionError("budget finalization reason was not inferred")
    if (
        infer_termination_reason([], validation_retries_exhausted=True)
        != "validation_retries"
    ):
        raise AssertionError("validation-retry finalization was not inferred")
    finish_plan = ActionPlan(
        actions=[
            FinishAction(
                action="finish",
                result=DetectionResult(
                    url="https://example.invalid",
                    is_phishing=False,
                    reason="Synthetic explicit finish result.",
                ),
            )
        ]
    )
    finish_history = [
        {
            "action_plan_step": 1,
            "action_plan": finish_plan,
            "completed_actions": 1,
            "succeeded": True,
            "error": None,
        }
    ]
    if infer_termination_reason(finish_history) != "finish":
        raise AssertionError("explicit finish reason was not inferred")
    if count_completed_browser_actions(finish_history) != 0:
        raise AssertionError("finish was counted as a browser action")

    print(f"Final verdict: {update['detection_result'].model_dump()}")
    print(f"Final call usage: {final_call_usage}")
    print(f"Total usage: {total_usage}")


if __name__ == "__main__":
    asyncio.run(main())
