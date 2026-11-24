"""Test ActionPlan and completed-browser-action accounting."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agent.action import ActionPlan, HandleDialogAction, WaitAction
from agent.browser.dialog import DialogRuntimeState, PendingBrowserOperation
from agent.experiment.run_result import count_completed_browser_actions
from agent.graph.nodes.act import act_node
from agent.tools.traversal.executor import ActionExecutionResult


async def main() -> None:
    page = SimpleNamespace()
    pending_plan = ActionPlan(
        actions=[
            WaitAction(action="wait", duration_seconds=1),
            WaitAction(action="wait", duration_seconds=1),
        ]
    )
    pending_result = ActionExecutionResult(
        active_page=page,
        completed_actions=2,
        requires_observation=True,
        error=None,
        detection_result=None,
    )

    async def complete_pending_action() -> ActionExecutionResult:
        return pending_result

    pending_task = asyncio.create_task(complete_pending_action())
    dialog = DialogRuntimeState(
        pending_dialog=SimpleNamespace(),
        observation={
            "type": "alert",
            "message": "Synthetic dialog",
            "default_value": "",
        },
        pending_operation=PendingBrowserOperation(
            kind="action",
            task=pending_task,
        ),
    )
    runtime = SimpleNamespace(
        context=SimpleNamespace(
            active_page=page,
            dialog=dialog,
        )
    )
    dialog_plan = ActionPlan(
        actions=[
            HandleDialogAction(
                action="handle_dialog",
                decision="accept",
            )
        ]
    )
    dialog_result = ActionExecutionResult(
        active_page=page,
        completed_actions=1,
        requires_observation=True,
        error=None,
        detection_result=None,
    )
    state = {
        "target_url": "https://example.invalid",
        "action_plan": dialog_plan,
        "action_plan_step_count": 1,
        "interaction_plan_count": 1,
        "interaction_history": [
            {
                "action_plan_step": 1,
                "action_plan": pending_plan,
                "completed_actions": 0,
                "succeeded": False,
                "error": None,
            }
        ],
    }

    with patch(
        "agent.graph.nodes.act.execute_action_plan",
        new=AsyncMock(return_value=dialog_result),
    ):
        update = await act_node(state, runtime)

    history = update["interaction_history"]
    if update["action_plan_step_count"] != 2:
        raise AssertionError("handle_dialog did not consume one ActionPlan step")
    if update["interaction_plan_count"] != 2:
        raise AssertionError("handle_dialog did not consume one interaction plan")
    if history[0]["completed_actions"] != 2:
        raise AssertionError("resumed action completions were not recorded")
    if history[1]["completed_actions"] != 1:
        raise AssertionError("dialog action completion was not recorded")
    if count_completed_browser_actions(history) != 3:
        raise AssertionError("completed browser actions were counted incorrectly")

    print("action accounting checks passed")


if __name__ == "__main__":
    asyncio.run(main())
