"""Example for collecting interactive elements from a real webpage."""

import asyncio
from pprint import pprint

from playwright.async_api import async_playwright

from agent.tools.evidence_collection.interactive_elements import (
    collect_interactive_elements,
)


TARGET_URL = "http://localhost/611c6991bcd1957f259f6c74f732859d/well/index.html"


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={
                "width": 1280,
                "height": 720,
            }
        )

        await page.goto(
            TARGET_URL,
            wait_until="load",
        )

        elements = await collect_interactive_elements(page)

        print(f"URL: {page.url}")
        print(f"Collected elements: {len(elements)}")
        pprint(elements)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
