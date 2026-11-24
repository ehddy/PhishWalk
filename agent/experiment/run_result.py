"""Persisted result schemas for PhishWalk experiment runs."""

from typing import Literal

from langchain_core.messages import UsageMetadata
from pydantic import BaseModel, ConfigDict, Field

from agent.action import ActionPlan
from agent.browser.dialog import DialogObservation
from agent.graph.state import (
    InteractionRecord,
    ModelCallTokenUsage,
    ValidationFailure,
)


TerminationReason = Literal[
    "one_shot",
    "finish",
    "max_action_plan_steps",
    "validation_retries",
]


class ActionPlanStep(BaseModel):
    """Compact log of one attempted ActionPlan and its outcome."""

    model_config = ConfigDict(extra="forbid")

    action_plan_step: int
    action_plan: ActionPlan
    completed_actions: int = Field(ge=0)
    succeeded: bool
    error: str | None = None
    observation_error: str | None = None
    dialog_observation: DialogObservation | None = None


def _to_action_plan_step(record: InteractionRecord) -> ActionPlanStep:
    """Drop page-diff noise, keeping only what action ran and whether it worked."""
    return ActionPlanStep(
        action_plan_step=record["action_plan_step"],
        action_plan=record["action_plan"],
        completed_actions=record["completed_actions"],
        succeeded=record["succeeded"],
        error=record["error"],
        observation_error=record.get("observation_error"),
        dialog_observation=record.get("dialog_observation"),
    )


def build_action_plan_steps(
    history: list[InteractionRecord],
) -> list[ActionPlanStep]:
    """Convert interaction history into compact ActionPlan step logs."""
    return [_to_action_plan_step(record) for record in history]


def count_completed_browser_actions(history: list[InteractionRecord]) -> int:
    """Count completed browser primitives while excluding the finish decision."""
    return sum(
        record["completed_actions"]
        for record in history
        if not any(
            action.action == "finish"
            for action in record["action_plan"].actions
        )
    )


def infer_termination_reason(
    history: list[InteractionRecord],
    *,
    validation_retries_exhausted: bool = False,
) -> TerminationReason:
    """Distinguish an explicit finish action from budget finalization."""
    for record in history:
        if not record.get("succeeded", False):
            continue
        action_plan = record["action_plan"]
        if any(action.action == "finish" for action in action_plan.actions):
            return "finish"
    if validation_retries_exhausted:
        return "validation_retries"
    return "max_action_plan_steps"


class TargetRunResult(BaseModel):
    """One target's summary record in a run-level results file."""

    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(min_length=1)
    target_url: str = Field(min_length=1)
    final_url: str | None = None
    status: Literal["completed", "failed"]
    is_phishing: bool | None = None
    reason: str | None = None
    error: str | None = None
    termination_reason: TerminationReason | None = None
    elapsed_seconds: float | None = Field(default=None, ge=0)
    observation_count: int = Field(default=0, ge=0)
    model_call_count: int = Field(default=0, ge=0)
    action_plan_step_count: int = Field(default=0, ge=0)
    interaction_plan_count: int = Field(default=0, ge=0)
    completed_browser_action_count: int = Field(default=0, ge=0)
    action_plan_steps: list[ActionPlanStep] = Field(default_factory=list)
    validation_failures: list[ValidationFailure] = Field(default_factory=list)
    model_call_token_usage: list[ModelCallTokenUsage] = Field(default_factory=list)
    total_token_usage: dict[str, UsageMetadata] = Field(default_factory=dict)
    artifact_directory: str = Field(min_length=1)
