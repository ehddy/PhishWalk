"""Provider-neutral chat model configuration for PhishWalk."""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Literal, cast

from dotenv import load_dotenv
from langchain.chat_models import BaseChatModel, init_chat_model
from langchain_openrouter import ChatOpenRouter


ModelProvider = Literal["openai", "anthropic", "google_genai", "openrouter"]

_DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
_CREDENTIAL_VARIABLES: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


@dataclass(frozen=True)
class ModelConfig:
    """Configuration needed to initialize one supported chat model."""

    provider: ModelProvider
    model: str
    temperature: float = 0.0

    @classmethod
    def from_env(cls, env_file: str | Path = _DEFAULT_ENV_FILE) -> "ModelConfig":
        """Load model selection and provider credentials from the environment."""
        load_dotenv(env_file)

        provider = os.getenv("PHISHWALK_MODEL_PROVIDER", "").strip()
        model = os.getenv("PHISHWALK_MODEL_NAME", "").strip()

        if provider not in _CREDENTIAL_VARIABLES:
            supported = ", ".join(_CREDENTIAL_VARIABLES)
            raise ValueError(
                "PHISHWALK_MODEL_PROVIDER must be one of: " f"{supported}."
            )
        if not model:
            raise ValueError("PHISHWALK_MODEL_NAME must be set.")

        credential_variable = _CREDENTIAL_VARIABLES[provider]
        if not os.getenv(credential_variable):
            raise ValueError(
                f"{credential_variable} must be set for provider '{provider}'."
            )

        try:
            temperature = float(os.getenv("PHISHWALK_MODEL_TEMPERATURE", "0.0"))
        except ValueError as error:
            raise ValueError(
                "PHISHWALK_MODEL_TEMPERATURE must be a number."
            ) from error

        return cls(
            provider=cast(ModelProvider, provider),
            model=model,
            temperature=temperature,
        )


def create_chat_model(config: ModelConfig) -> BaseChatModel:
    """Initialize a configured provider model through LangChain."""
    if config.provider == "openrouter":
        return ChatOpenRouter(
            model=config.model,
            temperature=config.temperature,
            app_title="PhishWalk",
            openrouter_provider={
                "allow_fallbacks": True,
                "data_collection": "deny",
                "require_parameters": True,
            },
        )

    provider_options = (
        {"use_responses_api": True}
        if config.provider == "openai"
        else {}
    )
    return init_chat_model(
        model=config.model,
        model_provider=config.provider,
        temperature=config.temperature,
        **provider_options,
    )
