"""Serializable observations of browser-native JavaScript dialogs."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from playwright.async_api import Dialog
from typing_extensions import TypedDict


DialogType = Literal["alert", "confirm", "prompt", "beforeunload"]
BrowserOperationKind = Literal["action", "navigation"]


class DialogObservation(TypedDict):
    """Information exposed to the model when a browser dialog is pending."""

    type: DialogType
    message: str
    default_value: str


@dataclass(frozen=True)
class PendingBrowserOperation:
    """Browser operation blocked until the pending dialog is handled."""

    kind: BrowserOperationKind
    task: asyncio.Task[Any]


@dataclass
class DialogRuntimeState:
    """Non-serializable runtime state for one pending browser dialog."""

    pending_dialog: Dialog | None = None
    observation: DialogObservation | None = None
    detected: asyncio.Event = field(default_factory=asyncio.Event)
    pending_operation: PendingBrowserOperation | None = None

    def record(self, dialog: Dialog) -> None:
        """Store a pending dialog and notify the browser-operation coordinator."""
        self.pending_dialog = dialog
        self.observation = create_dialog_observation(dialog)
        self.detected.set()

    def clear(self) -> None:
        """Clear the handled dialog while preserving its blocked operation."""
        self.pending_dialog = None
        self.observation = None
        self.detected.clear()


def create_dialog_observation(dialog: Dialog) -> DialogObservation:
    """Convert a live Playwright dialog into serializable model evidence."""
    dialog_type = dialog.type
    if dialog_type not in {"alert", "confirm", "prompt", "beforeunload"}:
        raise ValueError(f"unsupported browser dialog type: {dialog_type}")

    return {
        "type": cast(DialogType, dialog_type),
        "message": dialog.message,
        "default_value": dialog.default_value,
    }
