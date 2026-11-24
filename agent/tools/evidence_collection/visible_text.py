"""Visible text collection for the current browser viewport."""

from playwright.async_api import Page


async def collect_visible_text(
    page: Page,
    max_chars: int = 4000,
) -> str:
    """Return rendered text that overlaps the current viewport."""
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")

    visible_text = await page.evaluate(
        r"""
        () => {
            if (!document.body) {
                return "";
            }

            const chunks = [];
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
            );

            while (walker.nextNode()) {
                const node = walker.currentNode;
                const parent = node.parentElement;

                if (!parent || parent.closest("script, style, noscript")) {
                    continue;
                }

                if (parent.closest('[aria-hidden="true"]')) {
                    continue;
                }

                const style = window.getComputedStyle(parent);
                if (
                    style.display === "none"
                    || style.visibility === "hidden"
                    || Number(style.opacity) === 0
                ) {
                    continue;
                }

                const text = (node.textContent || "")
                    .replace(/\s+/g, " ")
                    .trim();

                if (!text) {
                    continue;
                }

                const range = document.createRange();
                range.selectNodeContents(node);

                const overlapsViewport = Array.from(range.getClientRects()).some(
                    (rect) => (
                        rect.bottom > 0
                        && rect.right > 0
                        && rect.top < window.innerHeight
                        && rect.left < window.innerWidth
                    ),
                );

                if (overlapsViewport) {
                    chunks.push(text);
                }
            }

            return chunks.join("\n");
        }
        """
    )

    return str(visible_text)[:max_chars]
