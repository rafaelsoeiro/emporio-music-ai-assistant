from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.agent.service import AgentExecutionError, CustomerServiceAgent
from app.api.dependencies import provide_chat_agent
from app.schemas.chat import ChatRequest, ChatResponse, ChatSource

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent: Annotated[CustomerServiceAgent, Depends(provide_chat_agent)],
) -> ChatResponse:
    try:
        reply = agent.answer(
            request.message,
            conversation_id=request.conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AgentExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat service is temporarily unavailable",
        ) from exc

    return ChatResponse(
        answer=reply.answer,
        sources=[
            ChatSource(kind=source.kind, name=source.name, page=source.page)
            for source in reply.sources
        ],
    )
