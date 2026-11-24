"""Runtime configuration for the PhishWalk agent."""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Literal, cast

from dotenv import load_dotenv


_DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

TraversalPolicy = Literal[
    "one_shot",
    "generic",
    "phishwalk",
]

SUPPORTED_TRAVERSAL_POLICIES: tuple[TraversalPolicy, ...] = (
    "one_shot",
    "generic",
    "phishwalk",
)

ActionName = Literal[
    "click",
    "fill",
    "press_enter",
    "mouse_move",
    "drag",
    "hold",
    "scroll",
    "wait",
    "go_back",
]

SUPPORTED_ACTIONS: tuple[ActionName, ...] = (
    "click",
    "fill",
    "press_enter",
    "mouse_move",
    "drag",
    "hold",
    "scroll",
    "wait",
    "go_back",
)
DEFAULT_ENABLED_ACTIONS: tuple[ActionName, ...] = (
    "click",
    "fill",
    "mouse_move",
    "drag",
    "hold",
    "scroll",
    "wait",
)


@dataclass(frozen=True)
class AgentConfig:
    """Adjustable limits for information supplied to the agent model."""

    max_interactive_elements: int = 100
    max_visible_text_chars: int = 4000
    max_change_text_items: int = 50
    max_change_element_items: int = 50
    max_action_plan_steps: int = 5
    max_validation_retries: int = 2
    max_provider_error_retries: int = 3
    target_timeout_seconds: float = 300.0
    enabled_actions: tuple[ActionName, ...] = DEFAULT_ENABLED_ACTIONS
    traversal_policy: TraversalPolicy = "phishwalk"

    def __post_init__(self) -> None:
        """Reject limits that cannot produce a useful observation."""
        if self.max_interactive_elements < 1:
            raise ValueError("max_interactive_elements must be at least 1")
        if self.max_visible_text_chars < 1:
            raise ValueError("max_visible_text_chars must be at least 1")
        if self.max_change_text_items < 1:
            raise ValueError("max_change_text_items must be at least 1")
        if self.max_change_element_items < 1:
            raise ValueError("max_change_element_items must be at least 1")
        if self.max_action_plan_steps < 1:
            raise ValueError("max_action_plan_steps must be at least 1")
        if self.max_validation_retries < 0:
            raise ValueError("max_validation_retries must be non-negative")
        if self.max_provider_error_retries < 0:
            raise ValueError("max_provider_error_retries must be non-negative")
        if self.target_timeout_seconds <= 0:
            raise ValueError("target_timeout_seconds must be greater than 0")
        if self.traversal_policy not in SUPPORTED_TRAVERSAL_POLICIES:
            raise ValueError(
                f"unsupported traversal policy: {self.traversal_policy}"
            )
        if self.traversal_policy == "one_shot" and self.enabled_actions:
            raise ValueError(
                "one_shot traversal policy requires an empty enabled_actions tuple"
            )
        if self.traversal_policy != "one_shot" and not self.enabled_actions:
            raise ValueError(
                "active traversal policies require at least one enabled action"
            )
        if len(set(self.enabled_actions)) != len(self.enabled_actions):
            raise ValueError("enabled_actions must not contain duplicates")

        unsupported_actions = set(self.enabled_actions) - set(SUPPORTED_ACTIONS)
        if unsupported_actions:
            unsupported = ", ".join(sorted(unsupported_actions))
            raise ValueError(f"unsupported enabled action(s): {unsupported}")

    @classmethod
    def from_env(
        cls,
        env_file: str | Path = _DEFAULT_ENV_FILE,
    ) -> "AgentConfig":
        """Load agent limits and enabled browser actions from the environment."""
        load_dotenv(env_file)
        try:
            max_action_plan_steps = int(
                os.getenv("PHISHWALK_MAX_ACTION_PLAN_STEPS", "5")
            )
        except ValueError as error:
            raise ValueError(
                "PHISHWALK_MAX_ACTION_PLAN_STEPS must be an integer."
            ) from error

        try:
            max_validation_retries = int(
                os.getenv("PHISHWALK_MAX_VALIDATION_RETRIES", "2")
            )
        except ValueError as error:
            raise ValueError(
                "PHISHWALK_MAX_VALIDATION_RETRIES must be an integer."
            ) from error

        try:
            max_provider_error_retries = int(
                os.getenv("PHISHWALK_MAX_PROVIDER_ERROR_RETRIES", "3")
            )
        except ValueError as error:
            raise ValueError(
                "PHISHWALK_MAX_PROVIDER_ERROR_RETRIES must be an integer."
            ) from error

        try:
            target_timeout_seconds = float(
                os.getenv("PHISHWALK_TARGET_TIMEOUT_SECONDS", "300")
            )
        except ValueError as error:
            raise ValueError(
                "PHISHWALK_TARGET_TIMEOUT_SECONDS must be a number."
            ) from error

        raw_enabled_actions = os.getenv(
            "PHISHWALK_ENABLED_ACTIONS",
            ",".join(DEFAULT_ENABLED_ACTIONS),
        )
        enabled_action_values = tuple(
            action.strip().lower()
            for action in raw_enabled_actions.split(",")
            if action.strip()
        )
        raw_traversal_policy = os.getenv(
            "PHISHWALK_TRAVERSAL_POLICY",
            "phishwalk",
        ).strip().lower()

        return cls(
            max_action_plan_steps=max_action_plan_steps,
            max_validation_retries=max_validation_retries,
            max_provider_error_retries=max_provider_error_retries,
            target_timeout_seconds=target_timeout_seconds,
            enabled_actions=cast(tuple[ActionName, ...], enabled_action_values),
            traversal_policy=cast(TraversalPolicy, raw_traversal_policy),
        )


DEFAULT_AGENT_CONFIG = AgentConfig()
