"""Shared state schemas for the PhishWalk graph."""

from langchain_core.messages import UsageMetadata
from typing_extensions import NotRequired, TypedDict

from agent.action import ActionPlan
from agent.browser.dialog import DialogObservation
from agent.change_observation import ChangeObservation
from agent.detection import DetectionResult
from agent.tools.evidence_collection.observation import PageObservation


class ModelCallTokenUsage(TypedDict):
    """Token usage and ActionPlan association for one model call."""

    model_call_index: int
    action_plan_step: int | None
    usage_by_model: dict[str, UsageMetadata]


class ValidationFailure(TypedDict):
    """One invalid structured model response excluded from ActionPlan steps."""

    model_call_index: int
    error: str


class InteractionRecord(TypedDict):
    """Compact record of one attempted ActionPlan step."""

    action_plan_step: int
    action_plan: ActionPlan
    completed_actions: int
    succeeded: bool
    error: str | None
    change_observation: NotRequired[ChangeObservation]
    observation_error: NotRequired[str]
    dialog_observation: NotRequired[DialogObservation]


class PhishWalkState(TypedDict):
    """State shared between PhishWalk graph nodes."""

    target_url: str
    current_observation: NotRequired[PageObservation]
    dialog_observation: NotRequired[DialogObservation | None]
    change_observation: NotRequired[ChangeObservation]
    action_plan: NotRequired[ActionPlan | None]
    last_error: NotRequired[str | None]
    observation_error: NotRequired[str | None]
    interaction_history: NotRequired[list[InteractionRecord]]
    detection_result: NotRequired[DetectionResult]
    action_plan_step_count: NotRequired[int]
    interaction_plan_count: NotRequired[int]
    model_call_count: NotRequired[int]
    validation_retry_count: NotRequired[int]
    validation_failures: NotRequired[list[ValidationFailure]]
    model_call_token_usage: NotRequired[list[ModelCallTokenUsage]]
    total_token_usage: NotRequired[dict[str, UsageMetadata]]
