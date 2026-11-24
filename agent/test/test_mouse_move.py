"""Test coordinate- and element-targeted mouse movement."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from agent.action import ElementTarget, PositionTarget
from agent.tools.evidence_collection.observation import collect_page_observation
from agent.tools.traversal.mouse_move import move_mouse


OUTPUT_DIRECTORY = Path("artifacts/mouse_move")
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
                button {
                    position: absolute;
                    left: 100px;
                    top: 80px;
                    width: 180px;
                    height: 44px;
                }
                div {
                    position: absolute;
                    left: 70%;
                    top: 62%;
                    width: 20%;
                    height: 20%;
                    background: #dbeafe;
                    border: 2px dashed #2563eb;
                }
            </style>
            <button type="button">Move here</button>
            <div>Coordinate target</div>
            <script>
                window.__mouseEvents = [];
                document.addEventListener("mousemove", (event) => {
                    window.__mouseEvents.push({x: event.clientX, y: event.clientY});
                });
            </script>
            """
        )

        observation = await collect_page_observation(
            page,
            OUTPUT_DIRECTORY / "before",
        )

        coordinate_position = await move_mouse(
            page,
            PositionTarget(type="viewport", x=0.8, y=0.72),
        )
        coordinate_events = await page.evaluate("window.__mouseEvents")
        expected_coordinate = (
            round(VIEWPORT_WIDTH * 0.8),
            round(VIEWPORT_HEIGHT * 0.72),
        )
        if coordinate_position != expected_coordinate or not coordinate_events:
            raise AssertionError("coordinate-targeted mouse movement failed")

        element = next(
            item for item in observation["elements"] if item["text"] == "Move here"
        )
        await page.evaluate("window.__mouseEvents = []")
        element_position = await move_mouse(
            page,
            ElementTarget(
                type="element",
                element_id=element["id"],
            ),
            observation,
        )
        element_events = await page.evaluate("window.__mouseEvents")
        expected_element = (
            element["x"] + element["width"] / 2,
            element["y"] + element["height"] / 2,
        )
        if element_position != expected_element or not element_events:
            raise AssertionError("element-targeted mouse movement failed")

        after_observation = await collect_page_observation(
            page,
            OUTPUT_DIRECTORY / "after",
        )
        print(f"Coordinate target position: {coordinate_position}")
        print(f"Element target position: {element_position}")
        print(f"Coordinate mouse events: {len(coordinate_events)}")
        print(f"Element mouse events: {len(element_events)}")
        print(
            "Before annotated screenshot: "
            f"{observation['annotated_screenshot_path'].resolve()}"
        )
        print(
            "After annotated screenshot: "
            f"{after_observation['annotated_screenshot_path'].resolve()}"
        )
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
