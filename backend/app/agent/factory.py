from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.agent.service import CustomerServiceAgent, InMemoryConversationStore
from app.agent.tools import build_customer_tools
from app.core.config import settings


class AgentConfigurationError(RuntimeError):
    """Raised when the chat model cannot be configured."""


@lru_cache
def get_chat_agent() -> CustomerServiceAgent:
    if (
        settings.openai_api_key is None
        or not settings.openai_api_key.get_secret_value()
    ):
        raise AgentConfigurationError("OPENAI_API_KEY is required for the chat agent")

    model = ChatOpenAI(
        model=settings.openai_chat_model,
        temperature=0,
        api_key=settings.openai_api_key.get_secret_value(),
    )
    return CustomerServiceAgent(
        model,
        build_customer_tools(),
        max_iterations=settings.agent_max_tool_iterations,
        conversation_store=InMemoryConversationStore(
            max_messages=settings.agent_history_messages
        ),
    )
