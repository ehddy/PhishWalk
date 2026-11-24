"""Structured differences between consecutive PhishWalk page observations."""

from collections import Counter

from typing_extensions import TypedDict

from agent.tools.evidence_collection.interactive_elements import (
    InteractiveElement,
)
from agent.tools.evidence_collection.observation import PageObservation


class ChangeObservation(TypedDict):
    """Relevant page changes detected after browser actions."""

    previous_url: str
    current_url: str
    url_changed: bool
    added_text: list[str]
    removed_text: list[str]
    added_elements: list[str]
    removed_elements: list[str]


def _normalize_text_lines(text: str) -> list[str]:
    """Return non-empty text lines with repeated whitespace collapsed."""
    return [
        normalized
        for line in text.splitlines()
        if (normalized := " ".join(line.split()))
    ]


def _format_element(element: InteractiveElement) -> str:
    """Return a stable semantic description without observation-local IDs."""
    input_type = element["input_type"]
    type_attribute = f' type="{input_type}"' if input_type else ""
    text = " ".join(element["text"].split())
    return f'<{element["tag"]}{type_attribute}> {text!r}'


def compare_observations(
    before: PageObservation,
    after: PageObservation,
) -> ChangeObservation:
    """Compare two page snapshots and return their semantic differences."""
    before_text = _normalize_text_lines(before["visible_text"])
    after_text = _normalize_text_lines(after["visible_text"])
    before_elements = [_format_element(element) for element in before["elements"]]
    after_elements = [_format_element(element) for element in after["elements"]]

    return {
        "previous_url": before["url"],
        "current_url": after["url"],
        "url_changed": before["url"] != after["url"],
        "added_text": list((Counter(after_text) - Counter(before_text)).elements()),
        "removed_text": list(
            (Counter(before_text) - Counter(after_text)).elements()
        ),
        "added_elements": list(
            (Counter(after_elements) - Counter(before_elements)).elements()
        ),
        "removed_elements": list(
            (Counter(before_elements) - Counter(after_elements)).elements()
        ),
    }
