"""Press-and-hold a verification gate and confirm it actually gates on duration."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from agent.tools.evidence_collection.observation import (
    collect_page_observation,
)
from agent.tools.traversal.element_resolver import resolve_observed_element
from agent.tools.traversal.hold import hold_target
from agent.action import ElementTarget


TARGET_URL = "http://127.0.0.1/d822829ec132/"
OUTPUT_DIRECTORY = Path("artifacts/hold")
MAX_RELOAD_ATTEMPTS = 10
HOLD_DURATION_SECONDS = 4  # above the Gate's configured 3000ms default


GATE_HEADING = "Verify your identity"


def _gate_still_showing(observation) -> bool:
    """True while the press-and-hold Gate's own heading is still visible."""
    return GATE_HEADING in observation["visible_text"]


async def _find_hold_button(page, label):
    for attempt in range(MAX_RELOAD_ATTEMPTS):
        await page.goto(TARGET_URL, wait_until="load")
        observation = await collect_page_observation(page, OUTPUT_DIRECTORY / label)
        elements = observation["elements"]
        handle = next(
            (element for element in elements if element["tag"] == "button"),
            None,
        )
        if handle is not None:
            return observation, handle
        print(f"Attempt {attempt}: no button found, reloading")
    raise RuntimeError(
        f"no hold button appeared after {MAX_RELOAD_ATTEMPTS} reloads"
    )


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            device_scale_factor=1,
        )
        page = await context.new_page()

        # Negative control first: an instant down+up must NOT complete the gate.
        # This is the exact failure mode `hold` exists to fix -- a plain click
        # is indistinguishable from mousedown immediately followed by mouseup.
        before_observation, handle = await _find_hold_button(page, "before_negative")
        resolved = await resolve_observed_element(page, before_observation, handle["id"])
        box = await resolved.locator.bounding_box()
        if box is None:
            raise RuntimeError("hold button is not visible")
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        await page.mouse.move(x, y)
        await page.mouse.down()
        await page.mouse.up()
        await page.wait_for_timeout(500)
        negative_observation = await collect_page_observation(
            page, OUTPUT_DIRECTORY / "after_negative"
        )
        if not _gate_still_showing(negative_observation):
            raise AssertionError(
                "an instant click completed the press-and-hold gate; "
                "the Gate's duration check may be broken"
            )
        print("Negative control passed: instant click did not complete the gate.")

        # Positive case: a genuine sustained hold via hold_target must complete it.
        before_observation, handle = await _find_hold_button(page, "before_positive")
        print(
            "Selected handle: "
            f"{handle['id']} <{handle['tag']}> {handle['text']!r}"
        )
        await hold_target(
            page,
            ElementTarget(type="element", element_id=handle["id"]),
            HOLD_DURATION_SECONDS,
            before_observation,
        )
        await page.wait_for_timeout(500)

        after_observation = await collect_page_observation(
            page, OUTPUT_DIRECTORY / "after_positive"
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

        if _gate_still_showing(after_observation):
            raise AssertionError(
                "the press-and-hold gate's own heading is still visible after a "
                "sustained hold; the gate did not register as completed"
            )
        print("Positive case passed: sustained hold completed the gate.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
