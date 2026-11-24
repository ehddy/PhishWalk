"""Wait traversal for time-dependent browser pages."""

from playwright.async_api import Page


MIN_WAIT_SECONDS = 1
MAX_WAIT_SECONDS = 30


async def wait_on_page(
    page: Page,
    duration_seconds: int,
) -> None:
    """Wait on the current page for a bounded number of seconds."""
    if not MIN_WAIT_SECONDS <= duration_seconds <= MAX_WAIT_SECONDS:
        raise ValueError(
            "duration_seconds must be between "
            f"{MIN_WAIT_SECONDS} and {MAX_WAIT_SECONDS}"
        )

    await page.wait_for_timeout(duration_seconds * 1000)
