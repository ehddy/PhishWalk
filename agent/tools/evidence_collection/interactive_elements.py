"""Collection of visible interactive elements from the current viewport."""

from playwright.async_api import Page
from typing_extensions import TypedDict


INTERACTIVE_ELEMENT_SELECTOR = "body *"


class InteractiveElement(TypedDict):
    """Description and viewport position of an interactive element."""

    id: str
    dom_index: int
    tag: str
    input_type: str | None
    text: str
    x: float
    y: float
    width: float
    height: float


async def collect_interactive_elements(
    page: Page,
) -> list[InteractiveElement]:
    """Return basic descriptions of visible interactive elements in the viewport."""
    elements = page.locator(INTERACTIVE_ELEMENT_SELECTOR)
    evaluated_elements = await elements.evaluate_all(
        """(nodes) => {
            const interactiveTags = new Set([
                "button",
                "a",
                "input",
                "select",
                "summary",
                "textarea",
            ]);
            const interactiveRoles = new Set([
                "button",
                "link",
                "checkbox",
                "combobox",
                "menuitemcheckbox",
                "menuitemradio",
                "option",
                "radio",
                "switch",
                "menuitem",
                "tab",
                "treeitem",
            ]);
            const textAttributes = [
                "aria-label",
                "placeholder",
                "value",
                "title",
            ];
            const collected = [];

            for (const [domIndex, node] of nodes.entries()) {
                const tag = node.tagName.toLowerCase();
                const role = (node.getAttribute("role") || "").toLowerCase();
                const style = window.getComputedStyle(node);
                const parentStyle = node.parentElement
                    ? window.getComputedStyle(node.parentElement)
                    : null;
                const hasEventAttribute = [...node.attributes].some(
                    (attribute) => attribute.name.toLowerCase().startsWith("on")
                );
                const hasPointerCursor = (
                    style.cursor === "pointer" &&
                    parentStyle?.cursor !== "pointer"
                );
                const isFocusable = (
                    node.tabIndex >= 0 &&
                    role !== "dialog"
                );
                const isAssociatedLabel = (
                    tag === "label" &&
                    (
                        node.hasAttribute("for") ||
                        node.querySelector("input, select, textarea") !== null
                    )
                );
                const hasInteractiveAriaState = (
                    node.hasAttribute("aria-haspopup") ||
                    node.hasAttribute("aria-expanded")
                );
                const isInteractive = (
                    interactiveTags.has(tag) ||
                    interactiveRoles.has(role) ||
                    isFocusable ||
                    isAssociatedLabel ||
                    hasInteractiveAriaState ||
                    hasEventAttribute ||
                    hasPointerCursor
                );

                if (!isInteractive) {
                    continue;
                }

                const rect = node.getBoundingClientRect();
                const visibleLeft = Math.max(0, rect.left);
                const visibleTop = Math.max(0, rect.top);
                const visibleRight = Math.min(window.innerWidth, rect.right);
                const visibleBottom = Math.min(window.innerHeight, rect.bottom);

                if (
                    style.display === "none" ||
                    style.visibility === "hidden" ||
                    visibleRight <= visibleLeft ||
                    visibleBottom <= visibleTop
                ) {
                    continue;
                }

                const centerX = (visibleLeft + visibleRight) / 2;
                const centerY = (visibleTop + visibleBottom) / 2;
                const topmostElement = node.ownerDocument.elementFromPoint(
                    centerX,
                    centerY,
                );
                const isUnobscured = (
                    topmostElement !== null &&
                    (topmostElement === node || node.contains(topmostElement))
                );

                if (!isUnobscured) {
                    continue;
                }

                let text = (node.innerText || node.textContent || "").trim();
                if (!text) {
                    for (const attribute of textAttributes) {
                        text = (node.getAttribute(attribute) || "").trim();
                        if (text) {
                            break;
                        }
                    }
                }

                collected.push({
                    dom_index: domIndex,
                    tag,
                    input_type: tag === "input"
                        ? (node.getAttribute("type") || "text").trim().toLowerCase()
                        : null,
                    text,
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                });
            }

            return collected;
        }"""
    )

    return [
        {
            "id": f"e{index}",
            "dom_index": element["dom_index"],
            "tag": element["tag"],
            "input_type": element["input_type"],
            "text": element["text"],
            "x": element["x"],
            "y": element["y"],
            "width": element["width"],
            "height": element["height"],
        }
        for index, element in enumerate(evaluated_elements, start=1)
    ]
