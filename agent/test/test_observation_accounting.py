"""Test that observation artifacts use an independent monotonic counter."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from agent.browser.dialog import DialogRuntimeState
from agent.graph.nodes.observe import observe_node


async def main() -> None:
    with TemporaryDirectory() as directory:
        target_directory = Path(directory) / "target"
        target_directory.mkdir()
        phishwalk_runtime = SimpleNamespace(
            active_page=SimpleNamespace(),
            output_directory=target_directory,
            observation_count=0,
            dialog=DialogRuntimeState(),
        )
        runtime = SimpleNamespace(context=phishwalk_runtime)
        state = {
            "target_url": "https://example.invalid",
            "action_plan_step_count": 0,
        }
        collection_count = 0

        async def collect_with_initial_dialog(
            page: object,
            output_directory: Path,
        ) -> dict[str, object]:
            nonlocal collection_count
            collection_count += 1
            if collection_count == 1:
                phishwalk_runtime.dialog.pending_dialog = SimpleNamespace()
                phishwalk_runtime.dialog.observation = {
                    "type": "alert",
                    "message": "Synthetic dialog",
                    "default_value": "",
                }
                phishwalk_runtime.dialog.detected.set()
                await asyncio.Event().wait()

            return {
                "url": "https://example.invalid",
                "title": "Synthetic page",
                "screenshot_path": output_directory / "screenshot.png",
                "annotated_screenshot_path": (
                    output_directory / "annotated_screenshot.png"
                ),
                "elements": [],
                "visible_text": "Synthetic observation",
            }

        with patch(
            "agent.graph.nodes.observe.collect_page_observation",
            side_effect=collect_with_initial_dialog,
        ):
            first_update = await observe_node(state, runtime)
            if "dialog_observation" not in first_update:
                raise AssertionError("initial dialog race was not exercised")

            phishwalk_runtime.dialog.clear()
            await observe_node(state, runtime)

        if not (target_directory / "observation_000").is_dir():
            raise AssertionError("first observation directory was not created")
        if not (target_directory / "observation_001").is_dir():
            raise AssertionError("second observation directory was not created")
        if phishwalk_runtime.observation_count != 2:
            raise AssertionError("observation counter was not advanced")

    print("observation accounting checks passed")


if __name__ == "__main__":
    asyncio.run(main())
