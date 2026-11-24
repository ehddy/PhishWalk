"""Click traversal for a model-selected element or viewport position."""

import asyncio
from dataclasses import dataclass

from playwright.async_api import Page

from agent.action import ElementTarget, PointerTarget
from agent.tools.evidence_collection.observation import PageObservation
from agent.tools.traversal.element_resolver import (
    resolve_observed_element,
    resolve_viewport_position,
)


POPUP_DETECTION_TIMEOUT_SECONDS = 0.3
ELEMENT_CLICK_TIMEOUT_MILLISECONDS = 10_000


@dataclass(frozen=True)
class ClickResult:
    """Browser pages available after one click action."""

    source_page: Page
    source_url: str
    active_page: Page
    active_url: str
    opened_pages: tuple[Page, ...]
    all_pages: tuple[Page, ...]


async def click_target(
    page: Page,
    target: PointerTarget,
    observation: PageObservation | None = None,
) -> ClickResult:
    """Click the selected target and return the resulting browser pages."""
    if isinstance(target, ElementTarget):
        if observation is None:
            raise RuntimeError("element-targeted click requires a page observation")
        resolved_element = await resolve_observed_element(
            page,
            observation,
            target.element_id,
        )
        target_locator = resolved_element.locator
        target_element_id = target.element_id
        target_position = None
    else:
        target_locator = None
        target_element_id = None
        target_position = resolve_viewport_position(page, target)

    source_url = page.url
    context = page.context
    pages_before_click = tuple(context.pages)

    opened_pages: list[Page] = []
    popup_detected = asyncio.Event()

    def record_opened_page(opened_page: Page) -> None:
        if any(opened_page is existing for existing in pages_before_click):
            return
        if any(opened_page is existing for existing in opened_pages):
            return

        opened_pages.append(opened_page)
        popup_detected.set()

    popup_listener = record_opened_page
    context_page_listener = record_opened_page
    page.on("popup", popup_listener)
    context.on("page", context_page_listener)

    try:
        if target_locator is not None:
            if not await target_locator.is_enabled(
                timeout=ELEMENT_CLICK_TIMEOUT_MILLISECONDS,
            ):
                raise RuntimeError(
                    f"target element is disabled: {target_element_id}"
                )
            await target_locator.click(
                timeout=ELEMENT_CLICK_TIMEOUT_MILLISECONDS,
            )
        else:
            assert target_position is not None
            await page.mouse.click(*target_position)

        if not popup_detected.is_set():
            try:
                await asyncio.wait_for(
                    popup_detected.wait(),
                    timeout=POPUP_DETECTION_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                pass

        for candidate in context.pages:
            record_opened_page(candidate)
    finally:
        page.remove_listener("popup", popup_listener)
        context.remove_listener("page", context_page_listener)

    active_page = opened_pages[-1] if opened_pages else page

    return ClickResult(
        source_page=page,
        source_url=source_url,
        active_page=active_page,
        active_url=active_page.url,
        opened_pages=tuple(opened_pages),
        all_pages=tuple(context.pages),
    )
