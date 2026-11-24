"""Click one random element, navigate back, and capture all three states."""

import asyncio
import random
from pathlib import Path

from playwright.async_api import async_playwright

from agent.action import ElementTarget
from agent.tools.evidence_collection.observation import (
    collect_page_observation,
)
from agent.tools.traversal.click import click_target
from agent.tools.traversal.go_back import go_back


TARGET_URL = "https://naver.com"
OUTPUT_DIRECTORY = Path("artifacts/go_back")
RANDOM_SEED = 20


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

        elements = initial_observation["elements"]
        if not elements:
            raise RuntimeError("no interactive elements were found")

        selected_element = random.Random(RANDOM_SEED).choice(elements)

        print(
            "Selected element: "
            f"{selected_element['id']} "
            f"<{selected_element['tag']}> "
            f"{selected_element['text']!r}"
        )

        click_result = await click_target(
            page,
            ElementTarget(
                type="element",
                element_id=selected_element["id"],
            ),
            initial_observation,
        )
        page = click_result.active_page
        await page.wait_for_timeout(2000)

        clicked_observation = await collect_page_observation(
            page,
            OUTPUT_DIRECTORY / "after_click",
        )

        go_back_result = await go_back(page)
        page = go_back_result.active_page
        await page.wait_for_timeout(1000)

        returned_observation = await collect_page_observation(
            page,
            OUTPUT_DIRECTORY / "after_go_back",
        )

        print(f"Initial URL: {initial_observation['url']}")
        print(f"Clicked URL: {clicked_observation['url']}")
        print(f"Returned URL: {returned_observation['url']}")
        print(
            "Initial annotated screenshot: "
            f"{initial_observation['annotated_screenshot_path'].resolve()}"
        )
        print(
            "After-click annotated screenshot: "
            f"{clicked_observation['annotated_screenshot_path'].resolve()}"
        )
        print(
            "After-go-back annotated screenshot: "
            f"{returned_observation['annotated_screenshot_path'].resolve()}"
        )

        if returned_observation["url"] != initial_observation["url"]:
            raise AssertionError("go_back did not return to the initial URL")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
