import logging
from collections.abc import Sequence
from threading import Lock
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from pydantic import ValidationError

from app.agent.prompt import SYSTEM_PROMPT
from app.agent.tools import ORDER_TOOL
from app.agent.types import AgentReply, RegisteredTool, SourceReference, ToolResult

logger = logging.getLogger(__name__)

_ORDER_CONFIRMATION_MESSAGE = (
    "Confirmação necessária: solicite ao cliente o order_id e o customer_email. "
    "Não revele se o pedido existe nem qualquer detalhe antes de receber ambos."
)


class AgentExecutionError(RuntimeError):
    """Raised when the language model cannot complete the agent loop."""


class InMemoryConversationStore:
    def __init__(self, *, max_messages: int = 20) -> None:
        self._max_messages = max_messages
        self._messages: dict[str, list[BaseMessage]] = {}
        self._lock = Lock()

    def get(self, conversation_id: str | None) -> list[BaseMessage]:
        if conversation_id is None or self._max_messages == 0:
            return []
        with self._lock:
            return list(self._messages.get(conversation_id, ()))

    def append_turn(
        self,
        conversation_id: str | None,
        human_message: HumanMessage,
        ai_message: AIMessage,
    ) -> None:
        if conversation_id is None or self._max_messages == 0:
            return
        with self._lock:
            history = self._messages.setdefault(conversation_id, [])
            history.extend((human_message, ai_message))
            del history[: -self._max_messages]


class CustomerServiceAgent:
    def __init__(
        self,
        model: Any,
        tools: Sequence[RegisteredTool],
        *,
        max_iterations: int = 6,
        conversation_store: InMemoryConversationStore | None = None,
    ) -> None:
        if max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        self._tools = {registered.tool.name: registered for registered in tools}
        self._model = model.bind_tools(
            [registered.tool for registered in tools],
            parallel_tool_calls=False,
        )
        self._max_iterations = max_iterations
        self._conversation_store = conversation_store or InMemoryConversationStore()

    def answer(self, message: str, *, conversation_id: str | None = None) -> AgentReply:
        normalized_message = message.strip()
        if not normalized_message:
            raise ValueError("message cannot be empty")

        human_message = HumanMessage(content=normalized_message)
        messages: list[BaseMessage] = [
            SystemMessage(content=SYSTEM_PROMPT),
            *self._conversation_store.get(conversation_id),
            human_message,
        ]
        consulted_sources: list[SourceReference] = []

        for _ in range(self._max_iterations):
            try:
                response = self._model.invoke(messages)
            except Exception as exc:
                raise AgentExecutionError("Chat model invocation failed") from exc
            if not isinstance(response, AIMessage):
                raise AgentExecutionError("Chat model returned an invalid message")
            messages.append(response)

            if not response.tool_calls:
                answer = self._message_text(response)
                if not answer:
                    raise AgentExecutionError("Chat model returned an empty answer")
                self._conversation_store.append_turn(
                    conversation_id,
                    human_message,
                    AIMessage(content=answer),
                )
                return AgentReply(
                    answer=answer,
                    sources=tuple(dict.fromkeys(consulted_sources)),
                )

            for tool_call in response.tool_calls:
                result = self._execute_tool_call(tool_call)
                consulted_sources.extend(result.sources)
                messages.append(
                    ToolMessage(
                        content=result.content,
                        tool_call_id=str(tool_call.get("id", "missing-id")),
                        name=str(tool_call.get("name", "unknown")),
                    )
                )

        raise AgentExecutionError("Maximum tool iterations exceeded")

    def _execute_tool_call(self, tool_call: dict[str, Any]) -> ToolResult:
        name = str(tool_call.get("name", ""))
        arguments = tool_call.get("args")
        if not isinstance(arguments, dict):
            return ToolResult("Parâmetros inválidos para a consulta solicitada.")

        registered = self._tools.get(name)
        if registered is None:
            return ToolResult("A consulta solicitada não está disponível.")

        if name == ORDER_TOOL and not self._has_order_confirmation(arguments):
            return ToolResult(_ORDER_CONFIRMATION_MESSAGE)

        try:
            args_schema = registered.tool.args_schema
            validated_arguments = (
                args_schema.model_validate(arguments).model_dump()
                if args_schema is not None
                else arguments
            )
            return registered.execute(validated_arguments)
        except ValidationError as exc:
            return ToolResult(f"Parâmetros inválidos para a consulta: {exc}")
        except Exception:
            logger.exception("Read-only tool failed", extra={"tool_name": name})
            return ToolResult(
                "A consulta falhou temporariamente. Não invente dados; informe ao "
                "cliente que não foi possível consultar agora."
            )

    @staticmethod
    def _has_order_confirmation(arguments: dict[str, Any]) -> bool:
        return bool(arguments.get("order_id")) and bool(
            str(arguments.get("customer_email", "")).strip()
        )

    @staticmethod
    def _message_text(message: AIMessage) -> str:
        if isinstance(message.content, str):
            return message.content.strip()
        return "".join(
            str(block.get("text", ""))
            for block in message.content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
