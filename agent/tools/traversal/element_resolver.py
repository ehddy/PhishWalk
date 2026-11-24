"""Resolve an observed element or normalized position against the current page."""

from dataclasses import dataclass

from playwright.async_api import Locator, Page

from agent.action import PointerTarget
from agent.tools.evidence_collection.interactive_elements import (
    INTERACTIVE_ELEMENT_SELECTOR,
    InteractiveElement,
    collect_interactive_elements,
)
from agent.tools.evidence_collection.observation import PageObservation


@dataclass(frozen=True)
class ResolvedElement:
    """An observed element matched to its current Playwright locator."""

    observed: InteractiveElement
    current: InteractiveElement
    locator: Locator


async def resolve_observed_element(
    page: Page,
    observation: PageObservation,
    element_id: str,
) -> ResolvedElement:
    """Resolve an element ID after verifying that the element has not changed."""
    observed_element = next(
        (
            element
            for element in observation["elements"]
            if element["id"] == element_id
        ),
        None,
    )

    if observed_element is None:
        raise ValueError(f"unknown element id: {element_id}")

    current_elements = await collect_interactive_elements(page)
    current_element = next(
        (
            element
            for element in current_elements
            if element["dom_index"] == observed_element["dom_index"]
        ),
        None,
    )

    if current_element is None:
        raise RuntimeError(f"element is no longer interactable: {element_id}")

    if (
        current_element["tag"] != observed_element["tag"]
        or current_element["input_type"] != observed_element["input_type"]
        or current_element["text"] != observed_element["text"]
    ):
        raise RuntimeError(f"element changed after observation: {element_id}")

    locator = page.locator(INTERACTIVE_ELEMENT_SELECTOR).nth(
        observed_element["dom_index"]
    )

    return ResolvedElement(
        observed=observed_element,
        current=current_element,
        locator=locator,
    )


def resolve_viewport_position(page: Page, target: PointerTarget) -> tuple[int, int]:
    """Clamp a normalized pointer target to an integer pixel position."""
    viewport = page.viewport_size
    if viewport is None:
        raise RuntimeError("position-targeted action requires a fixed viewport")

    x = min(round(target.x * viewport["width"]), viewport["width"] - 1)
    y = min(round(target.y * viewport["height"]), viewport["height"] - 1)
    return x, y
