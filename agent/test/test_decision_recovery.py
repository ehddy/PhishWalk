"""Test recovery from invalid structured action plans without a live model."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage

from agent.action import ActionPlan, WaitAction
from agent.config import AgentConfig
from agent.decision import _build_action_plan_schema
from agent.graph.builder import build_phishwalk_graph
from agent.graph.nodes.decision import decision_node
from agent.graph.routing import route_after_decision


MODEL_IDENTIFIER = "openai/test-model"


def _raw_message(input_tokens: int, output_tokens: int) -> AIMessage:
    return AIMessage(
        content="",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


async def main() -> None:
    default_schema = _build_action_plan_schema(AgentConfig().enabled_actions)
    default_schema_json = json.dumps(default_schema.model_json_schema())
    if '"go_back"' in default_schema_json:
        raise AssertionError("go_back was exposed by the default action schema")
    if '"press_enter"' in default_schema_json:
        raise AssertionError("press_enter was exposed by the default action schema")
    if '"finish"' not in default_schema_json:
        raise AssertionError("finish was missing from the default action schema")

    expanded_schema = _build_action_plan_schema(
        AgentConfig(
            enabled_actions=("click", "press_enter", "go_back"),
        ).enabled_actions
    )
    expanded_schema_json = json.dumps(expanded_schema.model_json_schema())
    if '"go_back"' not in expanded_schema_json:
        raise AssertionError("configured go_back action was not exposed")
    if '"press_enter"' not in expanded_schema_json:
        raise AssertionError("configured press_enter action was not exposed")

    model = MagicMock()
    model.get_lc_namespace.return_value = ["test"]
    structured_model = MagicMock()
    structured_model.ainvoke = AsyncMock(
        side_effect=[
            {
                "parsed": None,
                "raw": _raw_message(10, 2),
                "parsing_error": ValueError(
                    "finish must be the only action in a plan"
                ),
            },
            {
                "parsed": ActionPlan(
                    actions=[WaitAction(action="wait", duration_seconds=1)]
                ),
                "raw": _raw_message(20, 3),
                "parsing_error": None,
            },
        ]
    )
    structured_model.with_retry.return_value = structured_model
    model.with_structured_output.return_value = structured_model

    runtime = SimpleNamespace(
        context=SimpleNamespace(
            model=model,
            model_provider="openai",
            model_name="test-model",
            agent_config=AgentConfig(
                max_action_plan_steps=2,
                max_validation_retries=2,
            ),
        )
    )

    with TemporaryDirectory() as directory:
        screenshot_path = Path(directory) / "observation.png"
        screenshot_path.write_bytes(b"test image")
        observation = {
            "url": "https://example.invalid",
            "title": "Example Account",
            "screenshot_path": screenshot_path,
            "annotated_screenshot_path": screenshot_path,
            "elements": [],
            "visible_text": "Example page",
        }
        state = {
            "target_url": "https://example.invalid",
            "current_observation": observation,
        }

        invalid_update = await decision_node(state, runtime)
        first_messages = structured_model.ainvoke.call_args_list[0].args[0]
        if "Example Account" not in str(first_messages):
            raise AssertionError("page title was not supplied to the model")
        if invalid_update["action_plan"] is not None:
            raise AssertionError("invalid plan was treated as executable")
        if invalid_update.get("action_plan_step_count", 0) != 0:
            raise AssertionError("invalid plan consumed an ActionPlan step")
        if invalid_update["model_call_count"] != 1:
            raise AssertionError("invalid decision call was not counted")
        if invalid_update["validation_retry_count"] != 1:
            raise AssertionError("validation retry was not counted")
        validation_failure = invalid_update["validation_failures"][-1]
        if validation_failure["model_call_index"] != 1:
            raise AssertionError("validation failure has the wrong call index")
        if "finish must be the only action" not in validation_failure["error"]:
            raise AssertionError("validation error was not preserved")
        if route_after_decision({**state, **invalid_update}, runtime) != "decision":
            raise AssertionError("invalid plan was not routed back to decision")

        recovered_state = {**state, **invalid_update}
        valid_update = await decision_node(recovered_state, runtime)
        if valid_update["action_plan"] is None:
            raise AssertionError("corrected action plan was not accepted")
        if route_after_decision(
            {**recovered_state, **valid_update}, runtime
        ) != "act":
            raise AssertionError("valid plan was not routed to act")
        if valid_update["validation_retry_count"] != 0:
            raise AssertionError("validation retry count was not reset")

        retry_messages = structured_model.ainvoke.call_args_list[1].args[0]
        if "finish must be the only action" not in str(retry_messages):
            raise AssertionError("validation error was not returned to the model")

        token_usage = valid_update["model_call_token_usage"]
        if [item["model_call_index"] for item in token_usage] != [1, 2]:
            raise AssertionError("model call indices were not preserved")
        if [item["action_plan_step"] for item in token_usage] != [None, 1]:
            raise AssertionError("token usage was associated with the wrong plans")
        total_usage = valid_update["total_token_usage"][MODEL_IDENTIFIER]
        if total_usage["total_tokens"] != 35:
            raise AssertionError("decision retry tokens were not accumulated")

        exhausted_state = {
            **recovered_state,
            "action_plan": None,
            "validation_retry_count": 3,
        }
        if route_after_decision(exhausted_state, runtime) != "final_observe":
            raise AssertionError("exhausted validation retries did not finalize")

        budget_state = {
            **recovered_state,
            "action_plan": None,
            "action_plan_step_count": 2,
        }
        if route_after_decision(budget_state, runtime) != "final_observe":
            raise AssertionError("exhausted ActionPlan budget did not finalize")

    build_phishwalk_graph()
    print("decision recovery checks passed")


if __name__ == "__main__":
    asyncio.run(main())
