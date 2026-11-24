"""Hold the primary pointer on a selected target."""

import asyncio

from playwright.async_api import Page

from agent.action import ElementTarget, PointerTarget
from agent.tools.evidence_collection.observation import PageObservation
from agent.tools.traversal.element_resolver import (
    resolve_observed_element,
    resolve_viewport_position,
)


# Allow for browser/protocol timing differences so the effective pointer-down
# interval observed by the page is not shorter than the requested duration.
HOLD_TIMING_TOLERANCE_SECONDS = 0.4


async def hold_target(
    page: Page,
    target: PointerTarget,
    duration_seconds: int,
    observation: PageObservation | None = None,
) -> None:
    """Press and hold the primary pointer on a target for a fixed duration."""
    if isinstance(target, ElementTarget):
        if observation is None:
            raise RuntimeError("element-targeted hold requires a page observation")

        resolved_element = await resolve_observed_element(
            page,
            observation,
            target.element_id,
        )
        box = await resolved_element.locator.bounding_box()
        if box is None:
            raise RuntimeError(f"hold target is not visible: {target.element_id}")

        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
    else:
        x, y = resolve_viewport_position(page, target)

    await page.mouse.move(x, y)
    await page.mouse.down()
    try:
        await asyncio.sleep(duration_seconds + HOLD_TIMING_TOLERANCE_SECONDS)
    finally:
        await page.mouse.up()
