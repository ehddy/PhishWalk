"""Screenshot collection for the current browser viewport."""

from pathlib import Path

from playwright.async_api import Page


async def capture_viewport_screenshot(
    page: Page,
    output_path: str | Path,
) -> Path:
    """Capture the current viewport and return the screenshot path."""
    screenshot_path = Path(output_path)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    await page.screenshot(path=str(screenshot_path), full_page=False)

    return screenshot_path
