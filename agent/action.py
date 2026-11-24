"""Structured action decisions produced by the PhishWalk model."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.detection import DetectionResult


class BrowserAction(BaseModel):
    """Base validation shared by all browser actions."""

    model_config = ConfigDict(extra="forbid")


class FillAction(BrowserAction):
    """Fill an observed form field with synthetic, non-sensitive test data."""

    action: Literal["fill"] = Field(
        description="Select the fill action.",
    )
    element_id: str = Field(
        description="Target form-field ID from the current observation.",
    )
    value: str = Field(
        description="Synthetic, non-sensitive value to enter.",
    )


class PressEnterAction(BrowserAction):
    """Press Enter to trigger the currently focused element or form."""

    action: Literal["press_enter"] = Field(
        description="Select the press_enter action.",
    )


class ElementTarget(BaseModel):
    """Identify an observed element as a pointer-action target."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["element"] = Field(
        description='Required discriminator. Must be exactly "element".',
    )
    element_id: str = Field(
        min_length=1,
        description="Target element ID from the current observation.",
    )


class PositionTarget(BaseModel):
    """Identify a normalized viewport position as a pointer-action target."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["viewport"] = Field(
        description=(
            'Required discriminator. Must be exactly "viewport". '
            'Do not use "coordinate", "position", or "viewport_position".'
        ),
    )

    x: float = Field(
        ge=0.0,
        le=1.0,
        description="Horizontal viewport position from 0.0 (left) to 1.0 (right).",
    )
    y: float = Field(
        ge=0.0,
        le=1.0,
        description="Vertical viewport position from 0.0 (top) to 1.0 (bottom).",
    )


PointerTarget = Annotated[
    ElementTarget | PositionTarget,
    Field(discriminator="type"),
]


class ClickAction(BrowserAction):
    """Click a model-selected element or viewport position."""

    action: Literal["click"] = Field(
        description="Select the click action.",
    )
    target: PointerTarget = Field(
        description="Element or normalized viewport position to click.",
    )


class MouseMoveAction(BrowserAction):
    """Move the mouse to a model-selected element or viewport position."""

    action: Literal["mouse_move"] = Field(
        description="Select the mouse_move action.",
    )
    target: PointerTarget = Field(
        description="Element or normalized viewport position to move toward.",
    )


class DragAction(BrowserAction):
    """Drag from a model-selected pointer target to a viewport position."""

    action: Literal["drag"] = Field(
        description="Select the drag action.",
    )
    start: PointerTarget = Field(
        description=(
            'Drag start. Must contain type="element" with element_id, or '
            'type="viewport" with normalized x and y.'
        ),
    )
    end: PositionTarget = Field(
        description=(
            'Drag end. Must contain type="viewport" with normalized x and y.'
        ),
    )


class HoldAction(BrowserAction):
    """Press and hold a model-selected element or viewport position."""

    action: Literal["hold"] = Field(
        description="Select the hold action.",
    )
    target: PointerTarget = Field(
        description="Element or normalized viewport position to press and hold.",
    )
    duration_seconds: int = Field(
        ge=1,
        le=10,
        description="Number of seconds to hold the primary pointer down, from 1 to 10.",
    )


class ScrollAction(BrowserAction):
    """Scroll vertically to inspect content outside the current viewport."""

    action: Literal["scroll"] = Field(
        description="Select the scroll action.",
    )
    direction: Literal["up", "down"] = Field(
        description="Vertical direction in which to scroll the page.",
    )
    amount: Literal["small", "large"] = Field(
        description=(
            "Scroll distance: small for a brief nudge to read nearby content, "
            "large for a bigger jump past boilerplate toward new content."
        ),
    )


class WaitAction(BrowserAction):
    """Wait briefly to observe delayed or time-dependent page behavior."""

    action: Literal["wait"] = Field(
        description="Select the wait action.",
    )
    duration_seconds: int = Field(
        ge=1,
        le=30,
        description="Number of seconds to wait, from 1 through 30.",
    )


class GoBackAction(BrowserAction):
    """Return to the previous page or originating browser tab."""

    action: Literal["go_back"] = Field(
        description="Select the go_back action.",
    )


class HandleDialogAction(BrowserAction):
    """Accept or dismiss the currently pending browser-native dialog."""

    action: Literal["handle_dialog"] = Field(
        description="Select the handle_dialog action.",
    )
    decision: Literal["accept", "dismiss"] = Field(
        description="Accept or dismiss the pending dialog.",
    )
    prompt_text: str | None = Field(
        default=None,
        max_length=300,
        description=(
            "Optional synthetic, non-sensitive text supplied when accepting "
            "a prompt dialog. Use null for other dialog types."
        ),
    )


class FinishAction(BrowserAction):
    """Stop interacting and return the final phishing verdict."""

    action: Literal["finish"] = Field(
        description="Select the finish action.",
    )
    result: DetectionResult = Field(
        description="Final verdict grounded in the observed evidence.",
    )


ActionDecision = Annotated[
    ClickAction
    | FillAction
    | PressEnterAction
    | MouseMoveAction
    | DragAction
    | HoldAction
    | ScrollAction
    | WaitAction
    | GoBackAction
    | HandleDialogAction
    | FinishAction,
    Field(discriminator="action"),
]


class ActionPlan(BaseModel):
    """A brief plan summary followed by one to four browser actions."""

    model_config = ConfigDict(extra="forbid")

    plan_summary: str | None = Field(
        default=None,
        min_length=1,
        max_length=600,
        description=(
            "Brief evidence-grounded explanation of non-finish actions. "
            "Use null when the only action is finish."
        ),
    )
    actions: list[ActionDecision] = Field(
        min_length=1,
        max_length=4,
        description="One to four browser actions to execute in order.",
    )

    @model_validator(mode="after")
    def validate_action_order(self) -> Self:
        """Reject plans that could continue after the observed page changes."""
        if any(isinstance(action, FinishAction) for action in self.actions):
            if len(self.actions) != 1:
                raise ValueError("finish must be the only action in a plan")

        if any(isinstance(action, HandleDialogAction) for action in self.actions):
            if len(self.actions) != 1:
                raise ValueError("handle_dialog must be the only action in a plan")

        if len(self.actions) > 1 and isinstance(self.actions[-1], FillAction):
            raise ValueError("fill cannot be the final action in a multi-action plan")

        return self
