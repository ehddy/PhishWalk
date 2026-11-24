"""Execute a short browser action plan and capture the resulting page."""

import asyncio
import random
from pathlib import Path

from playwright.async_api import async_playwright

from agent.action import ActionPlan
from agent.change_observation import compare_observations
from agent.tools.evidence_collection.observation import (
    collect_page_observation,
)
from agent.tools.traversal.executor import execute_action_plan
from agent.tools.traversal.fill import NON_FILLABLE_INPUT_TYPES


TARGET_URL = "http://localhost/abbd2c88f93809815bb31c6a0d75e0b0/CommunityAmerica/index.html"
OUTPUT_DIRECTORY = Path("artifacts/executor")
RANDOM_SEED = 13

SYNTHETIC_VALUES = {
    "email": "test-user@example.invalid",
    "password": "SyntheticPassword123!",
    "number": "42",
    "tel": "0000000000",
    "url": "https://example.invalid",
}
DEFAULT_SYNTHETIC_VALUE = "synthetic-test-value"


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={
                "width": 1280,
                "height": 720,
            },
            device_scale_factor=1,
        )
        page = await context.new_page()

        await page.goto(
            TARGET_URL,
            wait_until="load",
        )

        initial_observation = await collect_page_observation(
            page,
            OUTPUT_DIRECTORY / "initial",
        )
        await page.evaluate(
            """
            () => {
                window.__phishwalkMouseEvents = [];
                document.addEventListener("mousemove", (event) => {
                    window.__phishwalkMouseEvents.push({
                        x: event.clientX,
                        y: event.clientY,
                    });
                });
            }
            """
        )

        movement_plan = ActionPlan.model_validate(
            {
                "plan_summary": (
                    "Move the pointer to reveal any behavior gated by mouse "
                    "activity."
                ),
                "actions": [
                    {
                        "action": "mouse_move",
                        "target": {
                            "type": "viewport",
                            "x": 0.5,
                            "y": 0.5,
                        },
                    },
                ]
            }
        )
        movement_result = await execute_action_plan(
            page,
            initial_observation,
            movement_plan,
        )

        if movement_result.error is not None:
            raise AssertionError(
                f"mouse movement returned an error: {movement_result.error}"
            )
        if movement_result.completed_actions != len(movement_plan.actions):
            raise AssertionError("executor did not complete the mouse movement")

        mouse_events = await page.evaluate("window.__phishwalkMouseEvents")
        if not mouse_events:
            raise AssertionError("executor emitted no mousemove events")
        if mouse_events[-1] != {"x": 640, "y": 360}:
            raise AssertionError(
                f"unexpected final mouse position: {mouse_events[-1]}"
            )

        movement_observation = await collect_page_observation(
            movement_result.active_page,
            OUTPUT_DIRECTORY / "after_mouse_move",
        )

        fillable_elements = [
            element
            for element in movement_observation["elements"]
            if element["tag"] == "textarea"
            or (
                element["tag"] == "input"
                and element["input_type"] not in NON_FILLABLE_INPUT_TYPES
            )
        ]

        if not fillable_elements:
            raise RuntimeError("no fillable elements were found")

        selected_element = random.Random(RANDOM_SEED).choice(
            fillable_elements
        )
        input_type = selected_element["input_type"]
        value = SYNTHETIC_VALUES.get(
            input_type,
            DEFAULT_SYNTHETIC_VALUE,
        )

        interaction_plan = ActionPlan.model_validate(
            {
                "plan_summary": (
                    "Submit synthetic data through a visible form and wait "
                    "for the page response."
                ),
                "actions": [
                    {
                        "action": "fill",
                        "element_id": selected_element["id"],
                        "value": value,
                    },
                    {
                        "action": "press_enter",
                    },
                    {
                        "action": "wait",
                        "duration_seconds": 5,
                    },
                ]
            }
        )

        print(
            "Selected element: "
            f"{selected_element['id']} "
            f"<{selected_element['tag']}> "
            f"type={input_type!r} "
            f"{selected_element['text']!r}"
        )
        print(f"Movement plan: {movement_plan.model_dump()}")
        print(f"Interaction plan: {interaction_plan.model_dump()}")

        result = await execute_action_plan(
            movement_result.active_page,
            movement_observation,
            interaction_plan,
        )

        if result.error is not None:
            raise AssertionError(f"executor returned an error: {result.error}")
        if result.completed_actions != len(interaction_plan.actions):
            raise AssertionError("executor did not complete every planned action")
        if not result.requires_observation:
            raise AssertionError("browser actions should require a new observation")
        if result.detection_result is not None:
            raise AssertionError("browser actions unexpectedly returned a detection")

        after_observation = await collect_page_observation(
            result.active_page,
            OUTPUT_DIRECTORY / "after",
        )
        change_observation = compare_observations(
            movement_observation,
            after_observation,
        )

        print(f"Completed actions: {result.completed_actions}")
        print(f"Requires observation: {result.requires_observation}")
        print(f"URL before: {initial_observation['url']}")
        print(f"URL after: {after_observation['url']}")
        print("Change observation:")
        for name, value in change_observation.items():
            print(f"- {name}: {value}")
        print(
            "Initial annotated screenshot: "
            f"{initial_observation['annotated_screenshot_path'].resolve()}"
        )
        print(
            "After-mouse-move annotated screenshot: "
            f"{movement_observation['annotated_screenshot_path'].resolve()}"
        )
        print(
            "After annotated screenshot: "
            f"{after_observation['annotated_screenshot_path'].resolve()}"
        )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
