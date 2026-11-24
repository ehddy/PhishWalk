"""Execution results for PhishWalk browser action plans."""

from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Dialog, Page

from agent.action import (
    ActionPlan,
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
from agent.detection import DetectionResult
from agent.tools.evidence_collection.observation import PageObservation
from agent.tools.traversal.click import click_target
from agent.tools.traversal.drag import drag_pointer
from agent.tools.traversal.fill import fill_element
from agent.tools.traversal.go_back import go_back
from agent.tools.traversal.handle_dialog import handle_dialog
from agent.tools.traversal.hold import hold_target
from agent.tools.traversal.mouse_move import move_mouse
from agent.tools.traversal.press_enter import press_enter
from agent.tools.traversal.scroll import scroll_page
from agent.tools.traversal.wait import wait_on_page


@dataclass(frozen=True)
class ActionExecutionResult:
    """Outcome of executing part or all of a browser action plan."""

    active_page: Page
    completed_actions: int
    requires_observation: bool
    error: str | None
    detection_result: DetectionResult | None


async def execute_action_plan(
    page: Page,
    observation: PageObservation | None,
    plan: ActionPlan,
    *,
    pending_dialog: Dialog | None = None,
) -> ActionExecutionResult:
    """Execute a validated action plan in order without leaking expected errors."""
    active_page = page
    completed_actions = 0
    detection_result = None

    for action in plan.actions:
        try:
            if isinstance(action, ClickAction):
                click_result = await click_target(
                    active_page,
                    action.target,
                    observation,
                )
                active_page = click_result.active_page
            elif isinstance(action, FillAction):
                if observation is None:
                    raise RuntimeError("fill requires a page observation")
                await fill_element(
                    active_page,
                    observation,
                    action.element_id,
                    action.value,
                )
            elif isinstance(action, PressEnterAction):
                await press_enter(active_page)
            elif isinstance(action, MouseMoveAction):
                await move_mouse(
                    active_page,
                    action.target,
                    observation,
                )
            elif isinstance(action, DragAction):
                await drag_pointer(
                    active_page,
                    action.start,
                    action.end,
                    observation,
                )
            elif isinstance(action, HoldAction):
                await hold_target(
                    active_page,
                    action.target,
                    action.duration_seconds,
                    observation,
                )
            elif isinstance(action, ScrollAction):
                await scroll_page(active_page, action.direction, action.amount)
            elif isinstance(action, WaitAction):
                await wait_on_page(active_page, action.duration_seconds)
            elif isinstance(action, GoBackAction):
                go_back_result = await go_back(active_page)
                active_page = go_back_result.active_page
            elif isinstance(action, HandleDialogAction):
                if pending_dialog is None:
                    raise RuntimeError("no browser dialog is pending")
                await handle_dialog(
                    pending_dialog,
                    action.decision,
                    action.prompt_text,
                )
            elif isinstance(action, FinishAction):
                detection_result = action.result
            else:
                raise TypeError(f"unsupported action type: {type(action).__name__}")

            completed_actions += 1
        except (ValueError, RuntimeError, PlaywrightError) as error:
            return ActionExecutionResult(
                active_page=active_page,
                completed_actions=completed_actions,
                requires_observation=True,
                error=str(error),
                detection_result=None,
            )

    return ActionExecutionResult(
        active_page=active_page,
        completed_actions=completed_actions,
        requires_observation=detection_result is None,
        error=None,
        detection_result=detection_result,
    )
