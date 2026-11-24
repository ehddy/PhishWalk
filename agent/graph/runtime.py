"""Run-scoped dependencies used by PhishWalk graph nodes."""

from dataclasses import dataclass, field
from pathlib import Path

from langchain.chat_models import BaseChatModel
from playwright.async_api import Page

from agent.browser.dialog import DialogRuntimeState
from agent.config import AgentConfig
from agent.model import ModelProvider


@dataclass
class PhishWalkRuntime:
    """Non-serializable dependencies kept outside the LangGraph state."""

    active_page: Page
    output_directory: Path
    model: BaseChatModel
    model_provider: ModelProvider
    model_name: str
    agent_config: AgentConfig
    observation_count: int = 0
    dialog: DialogRuntimeState = field(default_factory=DialogRuntimeState)
