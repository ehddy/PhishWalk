"""Regression checks for direct one-shot classification and accounting."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from agent.config import AgentConfig
from agent.decision import format_observation_text
from agent.detection import DetectionResult
from agent.browser.dialog import DialogRuntimeState
from agent.graph.builder import build_one_shot_graph
from agent.graph.nodes.one_shot import one_shot_decision_node
from agent.graph.nodes.observe import observe_node
from agent.graph.routing import route_after_one_shot_decision
from agent.graph.runner import _cancel_pending_browser_operation


def _raw_message(total: int) -> AIMessage:
    return AIMessage(
        content="",
        usage_metadata={
            "input_tokens": total - 2,
            "output_tokens": 2,
            "total_tokens": total,
        },
    )


async def main() -> None:
    try:
        AgentConfig(traversal_policy="passive")  # type: ignore[arg-type]
    except ValueError:
        pass
    else:
        raise AssertionError("removed passive policy was still accepted")
    try:
        AgentConfig(traversal_policy="one_shot")
    except ValueError:
        pass
    else:
        raise AssertionError("one_shot accepted non-empty browser actions")

    one_shot_config = AgentConfig(
        traversal_policy="one_shot",
        enabled_actions=(),
    )
    dialog_observation = {
        "type": "alert",
        "message": "Continue to the requested page",
        "default_value": "",
    }
    dialog_text = format_observation_text(
        None,
        target_url="https://example.invalid",
        dialog_observation=dialog_observation,
        config=one_shot_config,
    )
    if "Resolve this dialog" in dialog_text:
        raise AssertionError("one-shot received an impossible dialog action")
    if "No browser interaction is available" not in dialog_text:
        raise AssertionError("one-shot dialog limitation was not explicit")

    with TemporaryDirectory() as directory:
        blocked_task = asyncio.create_task(asyncio.Event().wait())
        dialog = DialogRuntimeState(
            pending_dialog=SimpleNamespace(),
            observation=dialog_observation,
            pending_operation=SimpleNamespace(
                kind="navigation",
                task=blocked_task,
            ),
        )
        dialog_runtime_context = SimpleNamespace(
            active_page=SimpleNamespace(),
            output_directory=Path(directory),
            observation_count=0,
            dialog=dialog,
            agent_config=one_shot_config,
        )
        update = await observe_node(
            {"target_url": "https://example.invalid"},
            SimpleNamespace(context=dialog_runtime_context),
        )
        if update.get("dialog_observation") != dialog_observation:
            raise AssertionError("native dialog was not retained as evidence")
        if dialog_runtime_context.observation_count != 1:
            raise AssertionError("native dialog did not count as one observation")
        await _cancel_pending_browser_operation(dialog_runtime_context)
        if not blocked_task.done() or dialog.pending_operation is not None:
            raise AssertionError("blocked navigation task was not cleaned up")

    model = MagicMock()
    model.get_lc_namespace.return_value = ["test"]
    structured_model = MagicMock()
    structured_model.ainvoke = AsyncMock(
        side_effect=[
            {
                "parsed": None,
                "raw": _raw_message(10),
                "parsing_error": ValueError("missing is_phishing"),
            },
            {
                "parsed": DetectionResult(
                    url="https://example.invalid",
                    is_phishing=False,
                    reason="No coherent phishing evidence is visible.",
                ),
                "raw": _raw_message(20),
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
                traversal_policy="one_shot",
                enabled_actions=(),
                max_validation_retries=2,
            ),
        )
    )

    with TemporaryDirectory() as directory:
        screenshot = Path(directory) / "observation.png"
        screenshot.write_bytes(b"image")
        state = {
            "target_url": "https://example.invalid",
            "current_observation": {
                "url": "https://example.invalid",
                "title": "Example",
                "screenshot_path": screenshot,
                "annotated_screenshot_path": screenshot,
                "elements": [],
                "visible_text": "Example page",
            },
        }
        invalid = await one_shot_decision_node(state, runtime)
        if invalid["model_call_count"] != 1:
            raise AssertionError("invalid logical invocation was not counted")
        if invalid["validation_retry_count"] != 1:
            raise AssertionError("invalid one-shot output was not retried")
        if route_after_one_shot_decision({**state, **invalid}, runtime) != (
            "one_shot_decision"
        ):
            raise AssertionError("recoverable validation error did not retry")

        recovered = await one_shot_decision_node(
            {**state, **invalid}, runtime
        )
        if recovered["model_call_count"] != 2:
            raise AssertionError("logical invocation count did not increase")
        if recovered["validation_retry_count"] != 0:
            raise AssertionError("validation retry count was not reset")
        if recovered.get("detection_result") is None:
            raise AssertionError("valid one-shot verdict was not retained")
        if route_after_one_shot_decision(
            {**state, **invalid, **recovered}, runtime
        ) != "end":
            raise AssertionError("valid one-shot verdict did not end the graph")
        if any(
            item["action_plan_step"] is not None
            for item in recovered["model_call_token_usage"]
        ):
            raise AssertionError("one-shot usage was linked to an ActionPlan")
        if recovered["total_token_usage"]["openai/test-model"][
            "total_tokens"
        ] != 30:
            raise AssertionError("one-shot retry tokens were not accumulated")

    if model.with_structured_output.call_args.args[0] is not DetectionResult:
        raise AssertionError("one-shot exposed a schema other than DetectionResult")
    if structured_model.with_retry.call_count != 2:
        raise AssertionError("one provider-retry wrapper was not used per invocation")

    provider_attempts = 0

    class RetryingStructuredModel:
        def with_retry(self, **_kwargs: object) -> "RetryingStructuredModel":
            return self

        async def ainvoke(self, _messages: object) -> dict:
            nonlocal provider_attempts
            # Simulate two provider attempts hidden inside one returned runnable
            # invocation. Agent accounting must still record one logical call.
            provider_attempts += 2
            return {
                "parsed": DetectionResult(
                    url="https://example.invalid",
                    is_phishing=False,
                    reason="No coherent phishing evidence is visible.",
                ),
                "raw": _raw_message(10),
                "parsing_error": None,
            }

    retrying_model = MagicMock()
    retrying_model.get_lc_namespace.return_value = ["test"]
    retrying_model.with_structured_output.return_value = RetryingStructuredModel()
    retrying_runtime = SimpleNamespace(
        context=SimpleNamespace(
            model=retrying_model,
            model_provider="openai",
            model_name="test-model",
            agent_config=AgentConfig(
                traversal_policy="one_shot",
                enabled_actions=(),
            ),
        )
    )
    with TemporaryDirectory() as directory:
        retry_screenshot = Path(directory) / "observation.png"
        retry_screenshot.write_bytes(b"image")
        retry_state = {
            **state,
            "current_observation": {
                **state["current_observation"],
                "screenshot_path": retry_screenshot,
                "annotated_screenshot_path": retry_screenshot,
            },
        }
        provider_retry_update = await one_shot_decision_node(
            retry_state, retrying_runtime
        )
    if provider_attempts != 2 or provider_retry_update["model_call_count"] != 1:
        raise AssertionError("provider attempts leaked into logical call accounting")

    graph_model = MagicMock()
    graph_model.get_lc_namespace.return_value = ["test"]
    graph_structured_model = MagicMock()
    graph_structured_model.ainvoke = AsyncMock(
        return_value={
            "parsed": DetectionResult(
                url="https://example.invalid",
                is_phishing=False,
                reason="No coherent phishing evidence is visible.",
            ),
            "raw": _raw_message(10),
            "parsing_error": None,
        }
    )
    graph_structured_model.with_retry.return_value = graph_structured_model
    graph_model.with_structured_output.return_value = graph_structured_model
    with TemporaryDirectory() as directory:
        runtime_context = SimpleNamespace(
            active_page=SimpleNamespace(),
            output_directory=Path(directory),
            observation_count=0,
            dialog=DialogRuntimeState(),
            model=graph_model,
            model_provider="openai",
            model_name="test-model",
            agent_config=AgentConfig(
                traversal_policy="one_shot",
                enabled_actions=(),
            ),
        )

        async def collect_once(_page: object, output_directory: Path) -> dict:
            screenshot = output_directory / "observation.png"
            screenshot.write_bytes(b"image")
            return {
                "url": "https://example.invalid",
                "title": "Example",
                "screenshot_path": screenshot,
                "annotated_screenshot_path": screenshot,
                "elements": [],
                "visible_text": "Example page",
            }

        with patch(
            "agent.graph.nodes.observe.collect_page_observation",
            side_effect=collect_once,
        ):
            final_state = await build_one_shot_graph().ainvoke(
                {"target_url": "https://example.invalid"},
                context=runtime_context,
            )
        if runtime_context.observation_count != 1:
            raise AssertionError("normal one-shot run did not observe exactly once")
        if final_state.get("model_call_count") != 1:
            raise AssertionError("normal one-shot run did not invoke the model once")
        for field in ("action_plan_step_count", "interaction_plan_count"):
            if final_state.get(field, 0) != 0:
                raise AssertionError(f"one-shot unexpectedly changed {field}")
    print("one-shot checks passed")


if __name__ == "__main__":
    asyncio.run(main())
