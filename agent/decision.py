"""Model decision boundary for PhishWalk browser actions."""

import base64
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Literal

from langchain.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ImageContentBlock,
    SystemMessage,
    TextContentBlock,
)
from openrouter.errors import ResponseValidationError, TooManyRequestsResponseError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from agent.action import (
    ActionPlan,
    BrowserAction,
    ClickAction,
    DragAction,
    FillAction,
    FinishAction,
    GoBackAction,
    HandleDialogAction,
    HoldAction,
    MouseMoveAction,
    PressEnterAction,
    ScrollAction,
    WaitAction,
)
from agent.browser.dialog import DialogObservation
from agent.change_observation import ChangeObservation
from agent.config import ActionName, AgentConfig, DEFAULT_AGENT_CONFIG
from agent.detection import DetectionResult
from agent.interaction_history import format_interaction_history
from agent.prompts import build_system_prompt
from agent.graph.state import InteractionRecord
from agent.tools.evidence_collection.observation import PageObservation


VALIDATION_ERROR_MAX_CHARS = 2_000

# Transient OpenRouter-side failures worth retrying on one model call:
# TooManyRequestsResponseError is a 429 (rate limit); ResponseValidationError
# is the SDK failing to parse an error-shaped response body (observed in
# practice when OpenRouter's own upstream provider for a model -- notably
# community-hosted open-weight models like Qwen, which route across several
# third-party backends with uneven uptime -- reports "provider_unavailable").
# Neither is a PhishWalk bug; both typically clear on retry.
_RETRYABLE_PROVIDER_ERRORS = (TooManyRequestsResponseError, ResponseValidationError)

_ACTION_MODELS: dict[ActionName, type[BrowserAction]] = {
    "click": ClickAction,
    "fill": FillAction,
    "press_enter": PressEnterAction,
    "mouse_move": MouseMoveAction,
    "drag": DragAction,
    "hold": HoldAction,
    "scroll": ScrollAction,
    "wait": WaitAction,
    "go_back": GoBackAction,
}


@dataclass(frozen=True)
class DecisionResult:
    """Action-plan outcome and its original model response."""

    action_plan: ActionPlan | None
    raw_message: AIMessage
    validation_error: str | None = None


@dataclass(frozen=True)
class FinalDecisionResult:
    """Validated final verdict and its original model response."""

    detection_result: DetectionResult
    raw_message: AIMessage


@dataclass(frozen=True)
class OneShotDecisionResult:
    """One-shot verdict outcome, including a recoverable schema error."""

    detection_result: DetectionResult | None
    raw_message: AIMessage
    validation_error: str | None = None


class DialogDecision(BaseModel):
    """A model decision restricted to resolving the pending browser dialog."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept", "dismiss"] = Field(
        description="Accept or dismiss the pending browser dialog.",
    )
    prompt_text: str | None = Field(
        default=None,
        max_length=300,
        description=(
            "Optional synthetic, non-sensitive text for an accepted prompt "
            "dialog. Use null for all other dialog types."
        ),
    )


@lru_cache(maxsize=None)
def _build_action_plan_schema(
    enabled_actions: tuple[ActionName, ...],
) -> type[ActionPlan]:
    """Build an ActionPlan schema exposing only enabled browser actions."""
    action_models = tuple(
        [*(_ACTION_MODELS[name] for name in enabled_actions), FinishAction]
    )
    action_union = action_models[0]
    for action_model in action_models[1:]:
        action_union = action_union | action_model

    configured_action = Annotated[
        action_union,
        Field(discriminator="action"),
    ]
    schema_suffix = "_".join(enabled_actions) or "finish_only"
    return create_model(
        f"ConfiguredActionPlan_{schema_suffix}",
        __base__=ActionPlan,
        actions=(
            list[configured_action],
            Field(
                min_length=1,
                max_length=4,
                description="One to four enabled browser actions in execution order.",
            ),
        ),
    )


def _format_action_plan_error(error: object) -> str:
    """Bound one validation error before storing and returning it to the model."""
    return f"Invalid ActionPlan: {str(error)[:VALIDATION_ERROR_MAX_CHARS]}"


def _format_detection_result_error(error: object) -> str:
    """Bound one detection-result validation error before retrying it."""
    return f"Invalid DetectionResult: {str(error)[:VALIDATION_ERROR_MAX_CHARS]}"


def _build_decision_messages(
    observation: PageObservation | None,
    observation_text: str,
    *,
    system_prompt: str,
) -> list[BaseMessage]:
    """Build provider-neutral text and image messages for one decision."""
    text_block: TextContentBlock = {
        "type": "text",
        "text": observation_text,
    }
    content_blocks: list[TextContentBlock | ImageContentBlock] = [text_block]

    if observation is not None:
        screenshot_path = observation["annotated_screenshot_path"]
        try:
            screenshot_bytes = screenshot_path.read_bytes()
        except OSError as error:
            raise RuntimeError(
                f"failed to read annotated screenshot: {screenshot_path}"
            ) from error

        if not screenshot_bytes:
            raise ValueError(f"annotated screenshot is empty: {screenshot_path}")

        image_block: ImageContentBlock = {
            "type": "image",
            "base64": base64.b64encode(screenshot_bytes).decode("ascii"),
            "mime_type": "image/png",
        }
        content_blocks.append(image_block)

    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content_blocks=content_blocks),
    ]


def _format_change_items(
    items: list[str],
    *,
    max_items: int,
) -> str:
    """Format zero or more change items as a compact bullet list."""
    visible_items = items[:max_items]
    lines = [f"- {item}" for item in visible_items]

    omitted_items = len(items) - len(visible_items)
    if omitted_items:
        lines.append(f"- [Omitted {omitted_items} additional change items]")

    return "\n".join(lines) or "None"


def _format_change_observation(
    change: ChangeObservation,
    config: AgentConfig,
) -> str:
    """Format changes that occurred after the previous browser actions."""
    has_changes = change["url_changed"] or any(
        (
            change["added_text"],
            change["removed_text"],
            change["added_elements"],
            change["removed_elements"],
        )
    )
    if not has_changes:
        return "No meaningful page change was detected."

    if change["url_changed"]:
        url_change = (
            f"Yes\n- Previous: {change['previous_url']}\n"
            f"- Current: {change['current_url']}"
        )
    else:
        url_change = "No"

    added_text = _format_change_items(
        change["added_text"],
        max_items=config.max_change_text_items,
    )
    removed_text = _format_change_items(
        change["removed_text"],
        max_items=config.max_change_text_items,
    )
    added_elements = _format_change_items(
        change["added_elements"],
        max_items=config.max_change_element_items,
    )
    removed_elements = _format_change_items(
        change["removed_elements"],
        max_items=config.max_change_element_items,
    )

    return (
        f"URL changed:\n{url_change}\n\n"
        f"Added text:\n{added_text}\n\n"
        f"Removed text:\n{removed_text}\n\n"
        f"Added interactive elements:\n{added_elements}\n\n"
        f"Removed interactive elements:\n{removed_elements}"
    )


def format_observation_text(
    observation: PageObservation | None,
    last_error: str | None = None,
    *,
    target_url: str,
    dialog_observation: DialogObservation | None = None,
    change_observation: ChangeObservation | None = None,
    interaction_history: list[InteractionRecord] | None = None,
    observation_error: str | None = None,
    config: AgentConfig = DEFAULT_AGENT_CONFIG,
) -> str:
    """Format a bounded textual view of the latest page observation."""
    error_text = last_error or "None"
    observation_error_text = observation_error or "None"
    if observation is None:
        if dialog_observation is None:
            raise ValueError(
                "dialog_observation is required when page observation is unavailable"
            )
        sections = [
            f"Target URL:\n{target_url}\n\n"
            "Page observation:\nUnavailable because a browser dialog is "
            "blocking the initial navigation.\n\n"
            f"Previous action error:\n{error_text}\n\n"
            f"Observation error:\n{observation_error_text}"
        ]
    else:
        visible_text = observation["visible_text"][
            : config.max_visible_text_chars
        ]
        visible_text_omitted = (
            len(observation["visible_text"]) - len(visible_text)
        )
        if visible_text_omitted:
            visible_text += f"\n[Truncated {visible_text_omitted} characters]"

        elements = observation["elements"][: config.max_interactive_elements]
        element_lines: list[str] = []
        for element in elements:
            input_type = element["input_type"]
            type_attribute = f' type="{input_type}"' if input_type else ""
            element_lines.append(
                f'- {element["id"]}: '
                f'<{element["tag"]}{type_attribute}> '
                f'{element["text"]!r}'
            )

        omitted_elements = len(observation["elements"]) - len(elements)
        if omitted_elements:
            element_lines.append(
                f"- [Omitted {omitted_elements} additional elements]"
            )

        elements_text = "\n".join(element_lines) or "None"
        sections = [
            f"Target URL:\n{target_url}\n\n"
            f"Current URL:\n{observation['url']}\n\n"
            f"Page title:\n{observation.get('title') or 'None'}\n\n"
            f"Visible text:\n{visible_text or 'None'}\n\n"
            f"Interactive elements:\n{elements_text}\n\n"
            f"Previous action error:\n{error_text}\n\n"
            f"Observation error:\n{observation_error_text}"
        ]
    if dialog_observation is not None:
        default_value = dialog_observation["default_value"] or "None"
        dialog_instruction = (
            "No browser interaction is available in the one-shot condition. "
            "Classify using only the currently observable evidence."
            if config.traversal_policy == "one_shot"
            else "Resolve this dialog before selecting any other browser action."
        )
        sections.append(
            "Pending browser dialog:\n"
            f"- Type: {dialog_observation['type']}\n"
            f"- Message: {dialog_observation['message']}\n"
            f"- Default value: {default_value}\n"
            f"{dialog_instruction}"
        )
    if change_observation is not None:
        sections.append(
            "Changes after the previous action:\n"
            f"{_format_change_observation(change_observation, config)}"
        )
    if interaction_history:
        sections.append(format_interaction_history(interaction_history))

    return "\n\n".join(sections)


async def decide_action_plan(
    model: BaseChatModel,
    observation: PageObservation | None,
    last_error: str | None = None,
    *,
    target_url: str,
    dialog_observation: DialogObservation | None = None,
    change_observation: ChangeObservation | None = None,
    interaction_history: list[InteractionRecord] | None = None,
    observation_error: str | None = None,
    config: AgentConfig = DEFAULT_AGENT_CONFIG,
) -> DecisionResult:
    """Produce a validated action plan while preserving model metadata."""
    observation_text = format_observation_text(
        observation,
        last_error,
        target_url=target_url,
        dialog_observation=dialog_observation,
        change_observation=change_observation,
        interaction_history=interaction_history,
        observation_error=observation_error,
        config=config,
    )
    model_namespace = model.get_lc_namespace()
    structured_output_method = (
        "json_schema"
        if (
            "langchain_google_genai" in model_namespace
            or "langchain_openrouter" in model_namespace
        )
        else "function_calling"
    )
    output_schema = (
        DialogDecision
        if dialog_observation is not None
        else _build_action_plan_schema(config.enabled_actions)
    )
    structured_model = model.with_structured_output(
        output_schema,
        method=structured_output_method,
        include_raw=True,
    ).with_retry(
        retry_if_exception_type=_RETRYABLE_PROVIDER_ERRORS,
        stop_after_attempt=config.max_provider_error_retries + 1,
    )

    system_prompt = build_system_prompt(config.traversal_policy)

    messages = _build_decision_messages(
        observation,
        observation_text,
        system_prompt=system_prompt,
    )

    response = await structured_model.ainvoke(messages)

    if not isinstance(response, dict):
        raise TypeError("structured model response must be a dictionary")

    raw_message = response.get("raw")
    if not isinstance(raw_message, AIMessage):
        raise TypeError("structured model response is missing its raw AI message")

    parsing_error = response.get("parsing_error")
    if parsing_error is not None:
        return DecisionResult(
            action_plan=None,
            raw_message=raw_message,
            validation_error=_format_action_plan_error(parsing_error),
        )

    try:
        parsed_response = response.get("parsed")
        if dialog_observation is not None:
            dialog_decision = DialogDecision.model_validate(parsed_response)
            prompt_text = (
                dialog_decision.prompt_text
                if dialog_observation["type"] == "prompt"
                and dialog_decision.decision == "accept"
                else None
            )
            action_plan = ActionPlan(
                actions=[
                    HandleDialogAction(
                        action="handle_dialog",
                        decision=dialog_decision.decision,
                        prompt_text=prompt_text,
                    )
                ]
            )
        else:
            parsed_payload = (
                parsed_response.model_dump()
                if isinstance(parsed_response, BaseModel)
                else parsed_response
            )
            configured_plan = output_schema.model_validate(parsed_payload)
            action_plan = ActionPlan.model_validate(configured_plan.model_dump())
    except ValidationError as error:
        return DecisionResult(
            action_plan=None,
            raw_message=raw_message,
            validation_error=_format_action_plan_error(error),
        )

    return DecisionResult(
        action_plan=action_plan,
        raw_message=raw_message,
    )


async def decide_final_result(
    model: BaseChatModel,
    observation: PageObservation | None,
    last_error: str | None = None,
    *,
    target_url: str,
    dialog_observation: DialogObservation | None = None,
    change_observation: ChangeObservation | None = None,
    interaction_history: list[InteractionRecord] | None = None,
    observation_error: str | None = None,
    config: AgentConfig = DEFAULT_AGENT_CONFIG,
) -> FinalDecisionResult:
    """Produce a mandatory verdict when no further actions are allowed."""
    observation_text = format_observation_text(
        observation,
        last_error,
        target_url=target_url,
        dialog_observation=dialog_observation,
        change_observation=change_observation,
        interaction_history=interaction_history,
        observation_error=observation_error,
        config=config,
    )
    observation_text += (
        "\n\nFinalization:\n"
        "No further browser actions are allowed. Return the best-supported final "
        "verdict from the available evidence, and reflect any remaining uncertainty "
        "explicitly in the reason."
    )

    system_prompt = build_system_prompt(config.traversal_policy)

    messages = _build_decision_messages(
        observation,
        observation_text,
        system_prompt=system_prompt,
    )
    model_namespace = model.get_lc_namespace()
    structured_output_method = (
        "json_schema"
        if (
            "langchain_google_genai" in model_namespace
            or "langchain_openrouter" in model_namespace
        )
        else "function_calling"
    )
    structured_model = model.with_structured_output(
        DetectionResult,
        method=structured_output_method,
        include_raw=True,
    ).with_retry(
        retry_if_exception_type=_RETRYABLE_PROVIDER_ERRORS,
        stop_after_attempt=config.max_provider_error_retries + 1,
    )
    response = await structured_model.ainvoke(messages)

    if not isinstance(response, dict):
        raise TypeError("structured model response must be a dictionary")

    parsing_error = response.get("parsing_error")
    if parsing_error is not None:
        raise RuntimeError(
            f"model returned an invalid final verdict: {parsing_error}"
        )

    raw_message = response.get("raw")
    if not isinstance(raw_message, AIMessage):
        raise TypeError("structured model response is missing its raw AI message")

    detection_result = DetectionResult.model_validate(response.get("parsed"))
    return FinalDecisionResult(
        detection_result=detection_result,
        raw_message=raw_message,
    )


async def decide_one_shot_result(
    model: BaseChatModel,
    observation: PageObservation | None,
    last_error: str | None = None,
    *,
    target_url: str,
    dialog_observation: DialogObservation | None = None,
    observation_error: str | None = None,
    config: AgentConfig = DEFAULT_AGENT_CONFIG,
) -> OneShotDecisionResult:
    """Classify one observation without exposing an ActionPlan."""
    observation_text = format_observation_text(
        observation,
        last_error,
        target_url=target_url,
        dialog_observation=dialog_observation,
        observation_error=observation_error,
        config=config,
    )
    model_namespace = model.get_lc_namespace()
    structured_output_method = (
        "json_schema"
        if (
            "langchain_google_genai" in model_namespace
            or "langchain_openrouter" in model_namespace
        )
        else "function_calling"
    )
    structured_model = model.with_structured_output(
        DetectionResult,
        method=structured_output_method,
        include_raw=True,
    ).with_retry(
        retry_if_exception_type=_RETRYABLE_PROVIDER_ERRORS,
        stop_after_attempt=config.max_provider_error_retries + 1,
    )
    messages = _build_decision_messages(
        observation,
        observation_text,
        system_prompt=build_system_prompt(config.traversal_policy),
    )
    response = await structured_model.ainvoke(messages)
    if not isinstance(response, dict):
        raise TypeError("structured model response must be a dictionary")

    raw_message = response.get("raw")
    if not isinstance(raw_message, AIMessage):
        raise TypeError("structured model response is missing its raw AI message")

    parsing_error = response.get("parsing_error")
    if parsing_error is not None:
        return OneShotDecisionResult(
            detection_result=None,
            raw_message=raw_message,
            validation_error=_format_detection_result_error(parsing_error),
        )
    try:
        detection_result = DetectionResult.model_validate(response.get("parsed"))
    except ValidationError as error:
        return OneShotDecisionResult(
            detection_result=None,
            raw_message=raw_message,
            validation_error=_format_detection_result_error(error),
        )
    return OneShotDecisionResult(
        detection_result=detection_result,
        raw_message=raw_message,
    )
