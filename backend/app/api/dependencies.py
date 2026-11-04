from fastapi import HTTPException, status

from app.agent.factory import AgentConfigurationError, get_chat_agent
from app.agent.service import CustomerServiceAgent


async def provide_chat_agent() -> CustomerServiceAgent:
    try:
        return get_chat_agent()
    except AgentConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat service is not configured",
        ) from exc
