"""Traversal support for browser-native JavaScript dialogs."""

from typing import Literal

from playwright.async_api import Dialog


async def handle_dialog(
    dialog: Dialog,
    decision: Literal["accept", "dismiss"],
    prompt_text: str | None = None,
) -> None:
    """Accept or dismiss a pending dialog using the model's decision."""
    if decision == "dismiss":
        if prompt_text is not None:
            raise ValueError("prompt_text cannot be used when dismissing a dialog")
        await dialog.dismiss()
        return

    if prompt_text is not None and dialog.type != "prompt":
        raise ValueError("prompt_text can only be used with a prompt dialog")

    if prompt_text is None:
        await dialog.accept()
    else:
        await dialog.accept(prompt_text=prompt_text)
