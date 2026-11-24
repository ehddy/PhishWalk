"""Generic pointer-drag traversal."""

from playwright.async_api import Page

from agent.action import ElementTarget, PointerTarget, PositionTarget
from agent.tools.evidence_collection.observation import PageObservation
from agent.tools.traversal.element_resolver import (
    resolve_observed_element,
    resolve_viewport_position,
)

DRAG_STEPS = 20


async def drag_pointer(
    page: Page,
    start: PointerTarget,
    end: PositionTarget,
    observation: PageObservation | None = None,
) -> None:
    """Drag from a selected pointer target to a normalized viewport position."""
    if isinstance(start, ElementTarget):
        if observation is None:
            raise RuntimeError("element-targeted drag requires a page observation")

        resolved_element = await resolve_observed_element(
            page,
            observation,
            start.element_id,
        )
        start_box = await resolved_element.locator.bounding_box()
        if start_box is None:
            raise RuntimeError(f"drag start is not visible: {start.element_id}")

        start_x = start_box["x"] + start_box["width"] / 2
        start_y = start_box["y"] + start_box["height"] / 2
    else:
        start_x, start_y = resolve_viewport_position(page, start)

    end_x, end_y = resolve_viewport_position(page, end)

    await page.mouse.move(start_x, start_y)
    await page.mouse.down()
    try:
        await page.mouse.move(end_x, end_y, steps=DRAG_STEPS)
    finally:
        await page.mouse.up()
