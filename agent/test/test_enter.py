"""Fill one observed form element, press Enter, and capture the result."""

import asyncio
import random
from pathlib import Path

from playwright.async_api import async_playwright

from agent.tools.evidence_collection.interactive_elements import (
    INTERACTIVE_ELEMENT_SELECTOR,
)
from agent.tools.evidence_collection.observation import (
    collect_page_observation,
)
from agent.tools.traversal.fill import (
    NON_FILLABLE_INPUT_TYPES,
    fill_element,
)
from agent.tools.traversal.press_enter import press_enter


TARGET_URL = "http://localhost/c7f4cfed11d4aafe3925df93def42d02/fb3/"
OUTPUT_DIRECTORY = Path("artifacts/enter")
RANDOM_SEED = 13

SYNTHETIC_VALUES = {
    "email": "test-user@example.invalid",
    "password": "SyntheticPassword123!",
    "number": "42",
    "tel": "0000000000",
    "url": "https://example.invalid",
    "date": "2000-01-01",
    "datetime-local": "2000-01-01T00:00",
    "month": "2000-01",
    "week": "2000-W01",
    "time": "00:00",
    "color": "#663399",
    "range": "50",
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

        before_observation = await collect_page_observation(
            page,
            OUTPUT_DIRECTORY / "before",
        )

        fillable_elements = [
            element
            for element in before_observation["elements"]
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

        print(
            "Selected element: "
            f"{selected_element['id']} "
            f"<{selected_element['tag']}> "
            f"type={input_type!r} "
            f"{selected_element['text']!r}"
        )

        await fill_element(
            page,
            before_observation,
            selected_element["id"],
            value,
        )

        target = page.locator(INTERACTIVE_ELEMENT_SELECTOR).nth(
            selected_element["dom_index"]
        )
        actual_value = await target.input_value()
        if actual_value != value:
            raise AssertionError("the element value did not match the test value")

        await press_enter(page)
        await page.wait_for_timeout(2000)

        after_observation = await collect_page_observation(
            page,
            OUTPUT_DIRECTORY / "after_enter",
        )

        print(f"Synthetic value: {value!r}")
        print(f"Actual value before Enter: {actual_value!r}")
        print(f"URL before Enter: {before_observation['url']}")
        print(f"URL after Enter: {after_observation['url']}")
        print(
            "Before annotated screenshot: "
            f"{before_observation['annotated_screenshot_path'].resolve()}"
        )
        print(
            "After-Enter annotated screenshot: "
            f"{after_observation['annotated_screenshot_path'].resolve()}"
        )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
