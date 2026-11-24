"""Run a short observe-decide-act loop with one configured model."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from agent.change_observation import compare_observations
from agent.decision import decide_action_plan
from agent.model import ModelConfig, create_chat_model
from agent.graph.state import InteractionRecord
from agent.tools.evidence_collection.observation import (
    collect_page_observation,
)
from agent.tools.traversal.executor import execute_action_plan


TARGET_URL = (
    "http://localhost/d87ae279a9c2d5c6725af89ee483c1a2/oneee/"
    # "https://www.ielp-mining.cc/"
)
OUTPUT_DIRECTORY = Path("artifacts/decision")
POST_ACTION_SETTLE_SECONDS = 1
MAX_STEPS = 5


async def main() -> None:
    model_config = ModelConfig.from_env()
    model = create_chat_model(model_config)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        try:
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

            current_observation = await collect_page_observation(
                page,
                OUTPUT_DIRECTORY / "observation_000",
            )
            print(
                "Model: "
                f"{model_config.provider}/{model_config.model}"
            )
            print(
                "Initial annotated screenshot: "
                f"{current_observation['annotated_screenshot_path'].resolve()}"
            )

            current_page = page
            change_observation = None
            interaction_history: list[InteractionRecord] = []
            last_error = None

            for step in range(1, MAX_STEPS + 1):
                print(f"\n=== Step {step} ===")
                decision_result = await decide_action_plan(
                    model,
                    current_observation,
                    last_error,
                    target_url=TARGET_URL,
                    change_observation=change_observation,
                    interaction_history=interaction_history,
                )
                plan = decision_result.action_plan

                print(f"Plan summary: {plan.plan_summary}")
                print("Planned actions:")
                for index, action in enumerate(plan.actions, start=1):
                    print(f"- {index}: {action.model_dump()}")

                result = await execute_action_plan(
                    current_page,
                    current_observation,
                    plan,
                )

                print(f"Completed actions: {result.completed_actions}")
                print(f"Execution error: {result.error or 'None'}")

                interaction_record: InteractionRecord = {
                    "action_plan_step": step,
                    "action_plan": plan,
                    "completed_actions": result.completed_actions,
                    "succeeded": (
                        result.error is None
                        and result.completed_actions == len(plan.actions)
                    ),
                    "error": result.error,
                }

                if result.detection_result is not None:
                    interaction_history.append(interaction_record)
                    print(
                        "Detection result: "
                        f"{result.detection_result.model_dump()}"
                    )
                    break

                await asyncio.sleep(POST_ACTION_SETTLE_SECONDS)
                next_observation = await collect_page_observation(
                    result.active_page,
                    OUTPUT_DIRECTORY / f"observation_{step:03d}",
                )
                change_observation = compare_observations(
                    current_observation,
                    next_observation,
                )
                interaction_record["change_observation"] = change_observation
                interaction_history.append(interaction_record)

                print(f"URL before: {current_observation['url']}")
                print(f"URL after: {next_observation['url']}")
                print("Change observation:")
                for name, value in change_observation.items():
                    print(f"- {name}: {value}")
                print(
                    "Annotated screenshot: "
                    f"{next_observation['annotated_screenshot_path'].resolve()}"
                )

                current_page = result.active_page
                current_observation = next_observation
                last_error = result.error
            else:
                raise AssertionError(
                    f"model did not finish within {MAX_STEPS} steps"
                )
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
