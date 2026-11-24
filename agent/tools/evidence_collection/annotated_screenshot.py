"""Add interactive-element labels to a screenshot copy."""

from pathlib import Path

from PIL import Image, ImageDraw

from agent.tools.evidence_collection.interactive_elements import InteractiveElement


def annotate_interactive_elements(
    screenshot_path: str | Path,
    elements: list[InteractiveElement],
    output_path: str | Path,
) -> Path:
    """Draw element boundaries and identifiers on a screenshot copy."""
    annotated_path = Path(output_path)
    annotated_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(screenshot_path) as source_image:
        annotated_image = source_image.convert("RGB")

    draw = ImageDraw.Draw(annotated_image)

    for element in elements:
        left = int(element["x"])
        top = int(element["y"])
        right = int(element["x"] + element["width"])
        bottom = int(element["y"] + element["height"])

        draw.rectangle(
            (left, top, right, bottom),
            outline="red",
            width=3,
        )

        label = element["id"]
        label_box = draw.textbbox((0, 0), label)
        label_width = label_box[2] - label_box[0]
        label_height = label_box[3] - label_box[1]
        label_top = max(0, top - label_height - 4)

        draw.rectangle(
            (left, label_top, left + label_width + 4, label_top + label_height + 4),
            fill="red",
        )
        draw.text(
            (left + 2, label_top + 2),
            label,
            fill="white",
        )

    annotated_image.save(annotated_path)

    return annotated_path
