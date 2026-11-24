"""Configuration for PhishWalk browser sessions."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


_DEFAULT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class BrowserConfig:
    """Settings needed to initialize a PhishWalk browser session."""

    headless: bool = True
    user_agent: str | None = None
    locale: str = "en-US"
    timezone_id: str = "UTC"
    viewport: tuple[int, int] = (1280, 720)

    def __post_init__(self) -> None:
        """Reject browser-profile values that Playwright cannot use."""
        if not self.locale.strip():
            raise ValueError("locale must not be empty")
        if not self.timezone_id.strip():
            raise ValueError("timezone_id must not be empty")
        if self.viewport[0] < 1 or self.viewport[1] < 1:
            raise ValueError("viewport dimensions must be at least 1")

    @classmethod
    def from_env(
        cls,
        env_file: str | Path = _DEFAULT_ENV_FILE,
    ) -> "BrowserConfig":
        """Load browser settings from environment variables."""
        load_dotenv(env_file)
        raw_headless = os.getenv("BROWSER_HEADLESS", "true").strip().lower()

        if raw_headless in _TRUE_VALUES:
            headless = True
        elif raw_headless in _FALSE_VALUES:
            headless = False
        else:
            raise ValueError(
                "BROWSER_HEADLESS must be one of: "
                "true, false, 1, 0, yes, no, on, off."
            )

        try:
            viewport = (
                int(os.getenv("BROWSER_VIEWPORT_WIDTH", "1280")),
                int(os.getenv("BROWSER_VIEWPORT_HEIGHT", "720")),
            )
        except ValueError as error:
            raise ValueError(
                "BROWSER_VIEWPORT_WIDTH and BROWSER_VIEWPORT_HEIGHT "
                "must be integers."
            ) from error

        return cls(
            headless=headless,
            user_agent=os.getenv("BROWSER_USER_AGENT", "").strip() or None,
            locale=os.getenv("BROWSER_LOCALE", "en-US").strip(),
            timezone_id=os.getenv("BROWSER_TIMEZONE_ID", "UTC").strip(),
            viewport=viewport,
        )
