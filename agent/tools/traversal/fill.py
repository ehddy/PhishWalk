"""Fill traversal for an element from the current page observation."""

from playwright.async_api import Page

from agent.tools.evidence_collection.observation import PageObservation
from agent.tools.traversal.element_resolver import resolve_observed_element


NON_FILLABLE_INPUT_TYPES = {
    "checkbox",
    "radio",
    "submit",
    "button",
    "file",
}


async def fill_element(
    page: Page,
    observation: PageObservation,
    element_id: str,
    value: str,
) -> None:
    """Fill an observed input or textarea after verifying its identity."""
    resolved_element = await resolve_observed_element(
        page,
        observation,
        element_id,
    )
    observed_element = resolved_element.observed

    if observed_element["tag"] not in {"input", "textarea"}:
        raise ValueError(f"element cannot be filled: {element_id}")

    if observed_element["input_type"] in NON_FILLABLE_INPUT_TYPES:
        raise ValueError(
            f"input type cannot be filled: {observed_element['input_type']}"
        )

    target = resolved_element.locator

    if not await target.is_editable():
        raise RuntimeError(f"element is not editable: {element_id}")

    await target.fill(value)
