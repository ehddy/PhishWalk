"""Playwright browser-session lifecycle for PhishWalk."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from playwright.async_api import Page, async_playwright

from agent.browser.config import BrowserConfig


@asynccontextmanager
async def open_browser_session(
    config: BrowserConfig,
) -> AsyncIterator[Page]:
    """Open one configured Chromium page and close its resources afterward."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=config.headless)
        try:
            context = await browser.new_context(
                # Always on: PhishWalk targets sites with invalid/mismatched
                # TLS certificates, and always hides the automation signal
                # for controlled cloaking experiments.
                ignore_https_errors=True,
                user_agent=config.user_agent,
                locale=config.locale,
                timezone_id=config.timezone_id,
                viewport={
                    "width": config.viewport[0],
                    "height": config.viewport[1],
                },
            )
            await context.add_init_script(
                """
                Object.defineProperty(Navigator.prototype, "webdriver", {
                    get: () => false,
                });
                """
            )
            page = await context.new_page()
            yield page
        finally:
            await browser.close()
