"""Mouse movement traversal for interaction-dependent browser pages."""

from playwright.async_api import Page

from agent.action import ElementTarget, PointerTarget
from agent.tools.evidence_collection.observation import PageObservation
from agent.tools.traversal.element_resolver import (
    resolve_observed_element,
    resolve_viewport_position,
)


async def move_mouse(
    page: Page,
    target: PointerTarget,
    observation: PageObservation | None = None,
) -> tuple[float, float]:
    """Move smoothly to a model-selected target and return its pixel position."""
    if isinstance(target, ElementTarget):
        if observation is None:
            raise RuntimeError("element-targeted mouse movement requires an observation")

        resolved_element = await resolve_observed_element(
            page,
            observation,
            target.element_id,
        )
        current = resolved_element.current
        target_x = current["x"] + current["width"] / 2
        target_y = current["y"] + current["height"] / 2
    else:
        target_x, target_y = resolve_viewport_position(page, target)

    await page.mouse.move(target_x, target_y, steps=12)
    return target_x, target_y
