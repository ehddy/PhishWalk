"""Structured result of observing the current web page."""

import asyncio
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from typing_extensions import TypedDict

from agent.tools.evidence_collection.annotated_screenshot import (
    annotate_interactive_elements,
)
from agent.tools.evidence_collection.interactive_elements import (
    InteractiveElement,
    collect_interactive_elements,
)
from agent.tools.evidence_collection.screenshot import capture_viewport_screenshot
from agent.tools.evidence_collection.visible_text import collect_visible_text

ELEMENT_SETTLE_TIMEOUT_SECONDS = 1.5
ELEMENT_SETTLE_POLL_SECONDS = 0.2
OBSERVATION_RETRY_ATTEMPTS = 3
OBSERVATION_RETRY_DELAY_SECONDS = 0.3


async def _collect_settled_interactive_elements(
    page: Page,
) -> list[InteractiveElement]:
    """Poll briefly for elements revealed by an in-progress page transition."""
    elapsed = 0.0
    while True:
        elements = await collect_interactive_elements(page)
        if elements or elapsed >= ELEMENT_SETTLE_TIMEOUT_SECONDS:
            return elements
        await asyncio.sleep(ELEMENT_SETTLE_POLL_SECONDS)
        elapsed += ELEMENT_SETTLE_POLL_SECONDS


class PageObservation(TypedDict):
    """Artifacts and interactive elements captured from one page state."""

    url: str
    title: str
    screenshot_path: Path
    annotated_screenshot_path: Path
    elements: list[InteractiveElement]
    visible_text: str


async def _collect_page_observation_once(
    page: Page,
    observation_directory: Path,
) -> PageObservation:
    """Capture the current page state in a single, unretried attempt."""
    screenshot_path = observation_directory / "screenshot.png"
    annotated_screenshot_path = observation_directory / "annotated_screenshot.png"

    elements = await _collect_settled_interactive_elements(page)
    visible_text = await collect_visible_text(page)
    title = await page.title()
    await capture_viewport_screenshot(page, screenshot_path)
    annotate_interactive_elements(
        screenshot_path,
        elements,
        annotated_screenshot_path,
    )

    return {
        "url": page.url,
        "title": title,
        "screenshot_path": screenshot_path,
        "annotated_screenshot_path": annotated_screenshot_path,
        "elements": elements,
        "visible_text": visible_text,
    }


async def collect_page_observation(
    page: Page,
    output_directory: str | Path,
) -> PageObservation:
    """Capture the current page state, retrying past transient page races."""
    observation_directory = Path(output_directory)

    last_error: PlaywrightError | None = None
    for attempt in range(OBSERVATION_RETRY_ATTEMPTS):
        try:
            return await _collect_page_observation_once(page, observation_directory)
        except PlaywrightError as error:
            last_error = error
            if attempt < OBSERVATION_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(OBSERVATION_RETRY_DELAY_SECONDS)

    assert last_error is not None
    raise last_error
