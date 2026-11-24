"""Drag a slider handle and capture observations before and after the action."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from agent.action import ElementTarget, PositionTarget
from agent.tools.evidence_collection.observation import (
    collect_page_observation,
)
from agent.tools.traversal.drag import drag_pointer


TARGET_URL = "http://127.0.0.1:8080/kit13/"
OUTPUT_DIRECTORY = Path("artifacts/drag")
MAX_RELOAD_ATTEMPTS = 10


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

        before_observation = None
        for attempt in range(MAX_RELOAD_ATTEMPTS):
            await page.goto(
                TARGET_URL,
                wait_until="load",
            )
            observation = await collect_page_observation(
                page,
                OUTPUT_DIRECTORY / "before",
            )
            if "slide" in observation["visible_text"].lower():
                before_observation = observation
                break
            print(f"Attempt {attempt}: slide-to-verify gate not shown, reloading")

        if before_observation is None:
            raise RuntimeError(
                "the slide-to-verify gate did not appear after "
                f"{MAX_RELOAD_ATTEMPTS} reloads; this kit randomizes its gate"
            )

        elements = before_observation["elements"]
        if not elements:
            raise RuntimeError("no interactive elements were found")

        handle = next(
            (element for element in elements if element["tag"] == "button"),
            elements[0],
        )
        print(
            "Selected handle: "
            f"{handle['id']} <{handle['tag']}> {handle['text']!r}"
        )

        viewport = page.viewport_size
        if viewport is None:
            raise RuntimeError("drag test requires a fixed viewport")
        await drag_pointer(
            page,
            ElementTarget(type="element", element_id=handle["id"]),
            PositionTarget(
                type="viewport",
                x=0.9,
                y=(handle["y"] + handle["height"] / 2) / viewport["height"],
            ),
            before_observation,
        )
        await page.wait_for_timeout(800)

        after_observation = await collect_page_observation(
            page,
            OUTPUT_DIRECTORY / "after",
        )

        print(
            "Before annotated screenshot: "
            f"{before_observation['annotated_screenshot_path'].resolve()}"
        )
        print(
            "After annotated screenshot: "
            f"{after_observation['annotated_screenshot_path'].resolve()}"
        )
        print(f"URL before: {before_observation['url']}")
        print(f"URL after: {after_observation['url']}")

        if after_observation["visible_text"] == before_observation["visible_text"]:
            raise AssertionError(
                "the page did not change after dragging; the slider may not "
                "have registered as completed"
            )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
