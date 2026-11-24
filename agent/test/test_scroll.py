"""Scroll one page and compare small vs large scroll amounts."""

import asyncio
from pathlib import Path

from playwright.async_api import Page, async_playwright

from agent.tools.evidence_collection.observation import (
    collect_page_observation,
)
from agent.tools.traversal.scroll import scroll_page


TARGET_URL = "http://127.0.0.1:8080/kit12/"
OUTPUT_DIRECTORY = Path("artifacts/scroll")
MAX_RELOAD_ATTEMPTS = 10


async def read_max_scroll_top(page: Page) -> float:
    """Return the largest scrollTop among all elements, window included.

    This gate scrolls an internal viewer container, not the window itself, so
    window.scrollY alone would never move; scanning every element's scrollTop
    finds whichever container actually scrolled.
    """
    return await page.evaluate(
        """() => Math.max(
            window.scrollY,
            ...Array.from(document.querySelectorAll("*")).map(
                (el) => el.scrollTop
            ),
        )"""
    )


async def wait_for_scrollable_gate(page: Page) -> None:
    """Reload until the multi-page document-review gate appears."""
    for attempt in range(MAX_RELOAD_ATTEMPTS):
        await page.goto(TARGET_URL, wait_until="load")
        observation = await collect_page_observation(
            page,
            OUTPUT_DIRECTORY / "probe",
        )
        if "review" in observation["visible_text"].lower():
            return
        print(f"Attempt {attempt}: document-review gate not shown, reloading")

    raise RuntimeError(
        "the document-review gate did not appear after "
        f"{MAX_RELOAD_ATTEMPTS} reloads; this kit randomizes its gate"
    )


async def scroll_and_measure(page: Page, amount: str) -> int:
    await wait_for_scrollable_gate(page)

    before_observation = await collect_page_observation(
        page,
        OUTPUT_DIRECTORY / f"before_{amount}",
    )
    before_scroll_y = await read_max_scroll_top(page)

    await scroll_page(page, "down", amount)

    after_scroll_y = await read_max_scroll_top(page)
    after_observation = await collect_page_observation(
        page,
        OUTPUT_DIRECTORY / f"after_{amount}",
    )

    print(f"[{amount}] scroll position before: {before_scroll_y}")
    print(f"[{amount}] scroll position after: {after_scroll_y}")
    print(
        f"[{amount}] before annotated screenshot: "
        f"{before_observation['annotated_screenshot_path'].resolve()}"
    )
    print(
        f"[{amount}] after annotated screenshot: "
        f"{after_observation['annotated_screenshot_path'].resolve()}"
    )

    if after_scroll_y <= before_scroll_y:
        raise AssertionError(
            f"the page did not scroll down for amount={amount!r}; "
            "it may not have scrollable content"
        )

    return after_scroll_y - before_scroll_y


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

        small_delta = await scroll_and_measure(page, "small")
        large_delta = await scroll_and_measure(page, "large")

        print(f"Small scroll delta: {small_delta}")
        print(f"Large scroll delta: {large_delta}")

        if large_delta <= small_delta:
            raise AssertionError(
                "large scroll did not move further than small scroll "
                f"(small={small_delta}, large={large_delta})"
            )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
