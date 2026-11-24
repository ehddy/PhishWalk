"""Vertical scroll traversal for the current browser page."""

import asyncio
from typing import Literal

from playwright.async_api import Page

SMALL_SCROLL_VIEWPORT_MULTIPLIER = 0.5
LARGE_SCROLL_VIEWPORT_MULTIPLIER = 2.0
SCROLL_SETTLE_DELAY_SECONDS = 0.5


async def scroll_page(
    page: Page,
    direction: Literal["up", "down"],
    amount: Literal["small", "large"],
) -> None:
    """Scroll a fraction of the viewport height in the requested direction."""
    if direction not in {"up", "down"}:
        raise ValueError("direction must be 'up' or 'down'")
    if amount not in {"small", "large"}:
        raise ValueError("amount must be 'small' or 'large'")

    viewport = page.viewport_size
    if viewport is None:
        raise RuntimeError("page viewport is unavailable")

    multiplier = (
        SMALL_SCROLL_VIEWPORT_MULTIPLIER
        if amount == "small"
        else LARGE_SCROLL_VIEWPORT_MULTIPLIER
    )
    distance = round(viewport["height"] * multiplier)
    delta_y = distance if direction == "down" else -distance

    await page.mouse.move(viewport["width"] / 2, viewport["height"] / 2)
    await page.mouse.wheel(0, delta_y)
    await asyncio.sleep(SCROLL_SETTLE_DELAY_SECONDS)
