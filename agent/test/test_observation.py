"""Collect and save one complete page observation."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from agent.tools.evidence_collection.observation import (
    collect_page_observation,
)


TARGET_URL = "http://localhost/3984785d4778276ea6eddf56f503e8b1/cron/index.html"
OUTPUT_DIRECTORY = Path("artifacts/observation")


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

        observation = await collect_page_observation(
            page,
            OUTPUT_DIRECTORY,
        )

        print(f"Page title: {observation['title']}")
        print(f"Collected elements: {len(observation['elements'])}")
        print(f"Raw screenshot: {observation['screenshot_path'].resolve()}")
        print(
            "Annotated screenshot: "
            f"{observation['annotated_screenshot_path'].resolve()}"
        )
        print("Visible text:")
        print(observation["visible_text"])

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
