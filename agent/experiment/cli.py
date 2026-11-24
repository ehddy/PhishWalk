"""Command-line entry point for PhishWalk batch experiments."""

import argparse
import asyncio
import logging
import warnings
from pathlib import Path

from agent.browser.config import BrowserConfig
from agent.config import AgentConfig
from agent.experiment.batch_runner import run_batch
from agent.model import ModelConfig, create_chat_model


def main() -> None:
    """Load configured dependencies and execute one target-file batch."""
    warnings.filterwarnings("ignore")
    logging.getLogger("google_genai.models").setLevel(logging.ERROR)

    parser = argparse.ArgumentParser(
        description="Run PhishWalk sequentially for URLs in a text file.",
    )
    parser.add_argument(
        "target_file",
        type=Path,
        help="UTF-8 text file containing one target URL per line.",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("artifacts"),
        help="Artifact root directory (default: artifacts).",
    )
    arguments = parser.parse_args()

    model_config = ModelConfig.from_env()
    browser_config = BrowserConfig.from_env()
    agent_config = AgentConfig.from_env()
    model = create_chat_model(model_config)
    run_directory = asyncio.run(
        run_batch(
            target_file=arguments.target_file,
            artifact_root=arguments.artifact_root,
            model=model,
            model_config=model_config,
            agent_config=agent_config,
            browser_config=browser_config,
        )
    )
    print(f"Completed run: {run_directory.resolve()}")


if __name__ == "__main__":
    main()
