"""Back-navigation traversal for browser history and popup pages."""

from dataclasses import dataclass

from playwright.async_api import Page


@dataclass(frozen=True)
class GoBackResult:
    """Browser page state after one back-navigation action."""

    source_page: Page
    source_url: str
    active_page: Page
    active_url: str
    closed_source_page: bool


async def go_back(page: Page) -> GoBackResult:
    """Navigate back in history or close a history-less popup page."""
    if page.is_closed():
        raise RuntimeError("cannot go back from a closed page")

    source_url = page.url
    history_length = await page.evaluate("window.history.length")
    opener = await page.opener()

    if history_length > 1:
        await page.go_back(wait_until="domcontentloaded")
        active_page = page
        closed_source_page = False
    elif opener is not None and not opener.is_closed():
        await page.close()
        await opener.bring_to_front()
        active_page = opener
        closed_source_page = True
    else:
        raise RuntimeError("no previous page is available")

    return GoBackResult(
        source_page=page,
        source_url=source_url,
        active_page=active_page,
        active_url=active_page.url,
        closed_source_page=closed_source_page,
    )
