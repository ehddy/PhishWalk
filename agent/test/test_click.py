"""Test element- and position-targeted clicks on a controlled page."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from agent.action import ElementTarget, PositionTarget
from agent.tools.evidence_collection.observation import collect_page_observation
from agent.tools.traversal.click import click_target


OUTPUT_DIRECTORY = Path("artifacts/click")
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            device_scale_factor=1,
        )
        page = await context.new_page()
        await page.set_content(
            """
            <style>
                body { margin: 0; font-family: sans-serif; }
                #element-target {
                    position: absolute;
                    left: 100px;
                    top: 80px;
                    width: 180px;
                    height: 44px;
                }
                #position-target {
                    position: absolute;
                    left: 70%;
                    top: 60%;
                    width: 20%;
                    height: 10%;
                }
            </style>
            <button id="element-target" type="button">Element target</button>
            <button id="position-target" type="button">Position target</button>
            <script>
                window.__elementClicks = 0;
                window.__positionClicks = 0;
                document.querySelector("#element-target").addEventListener(
                    "click",
                    () => { window.__elementClicks += 1; },
                );
                document.querySelector("#position-target").addEventListener(
                    "click",
                    () => {
                        window.__positionClicks += 1;
                        window.open("about:blank", "_blank");
                    },
                );
            </script>
            """
        )

        before_observation = await collect_page_observation(
            page,
            OUTPUT_DIRECTORY / "before",
        )
        element = next(
            item
            for item in before_observation["elements"]
            if item["text"] == "Element target"
        )

        element_result = await click_target(
            page,
            ElementTarget(type="element", element_id=element["id"]),
            before_observation,
        )
        element_clicks = await page.evaluate("window.__elementClicks")
        if element_clicks != 1 or element_result.opened_pages:
            raise AssertionError("element-targeted click failed")

        position_result = await click_target(
            page,
            PositionTarget(type="viewport", x=0.8, y=0.65),
        )
        position_clicks = await page.evaluate("window.__positionClicks")
        if position_clicks != 1:
            raise AssertionError("position-targeted click failed")
        if len(position_result.opened_pages) != 1:
            raise AssertionError("position-targeted popup detection failed")
        if position_result.active_page is not position_result.opened_pages[0]:
            raise AssertionError("opened popup was not selected as the active page")

        after_observation = await collect_page_observation(
            page,
            OUTPUT_DIRECTORY / "after",
        )
        print(f"Element clicks: {element_clicks}")
        print(f"Position clicks: {position_clicks}")
        print(f"Opened pages: {len(position_result.opened_pages)}")
        print(
            "Before annotated screenshot: "
            f"{before_observation['annotated_screenshot_path'].resolve()}"
        )
        print(
            "After annotated screenshot: "
            f"{after_observation['annotated_screenshot_path'].resolve()}"
        )
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
