"""Keyboard Enter traversal for the currently focused browser element."""

from playwright.async_api import Page


async def press_enter(page: Page) -> None:
    """Press Enter on the element that currently has browser focus."""
    await page.keyboard.press("Enter")
