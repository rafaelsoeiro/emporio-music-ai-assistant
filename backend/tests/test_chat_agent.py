import asyncio
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from app.agent.prompt import SYSTEM_PROMPT
from app.agent.service import CustomerServiceAgent
from app.agent.tools import (
    ORDER_TOOL,
    POLICY_TOOL,
    PRODUCT_TOOL,
    PROMOTION_TOOL,
    ActivePromotionsInput,
    OrderLookupInput,
    PolicySearchInput,
    ProductSearchInput,
    build_customer_tools,
    create_registered_tool,
)
from app.agent.types import AgentReply, SourceReference, ToolResult
from app.api.dependencies import provide_chat_agent
from app.main import app
from app.services.read_queries import CustomerResult, OrderDetailResult


def _tool_call(name: str, args: dict) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": args,
                "id": f"call-{name}",
                "type": "tool_call",
            }
        ],
    )


def _agent_for(
    *,
    tool_name: str,
    args_schema,
    executor: MagicMock,
    responses: list[AIMessage],
) -> tuple[CustomerServiceAgent, MagicMock]:
    registered = create_registered_tool(
        name=tool_name,
        description="Test tool",
        args_schema=args_schema,
        executor=executor,
    )
    model = MagicMock()
    bound_model = MagicMock()
    bound_model.invoke.side_effect = responses
    model.bind_tools.return_value = bound_model
    agent = CustomerServiceAgent(model, [registered])
    return agent, bound_model


def _last_tool_message(bound_model: MagicMock) -> ToolMessage:
    messages = bound_model.invoke.call_args_list[-1].args[0]
    return next(
        message for message in reversed(messages) if isinstance(message, ToolMessage)
    )


def test_product_question_uses_product_tool() -> None:
    source = SourceReference("database", "SQLite: products/categories")
    executor = MagicMock(
        return_value=ToolResult('{"products": [{"name": "Guitar"}]}', (source,))
    )
    agent, bound_model = _agent_for(
        tool_name=PRODUCT_TOOL,
        args_schema=ProductSearchInput,
        executor=executor,
        responses=[
            _tool_call(PRODUCT_TOOL, {"term": "guitarra"}),
            AIMessage(content="Encontrei uma guitarra disponível."),
        ],
    )

    reply = agent.answer("Tem guitarra disponível?")

    executor.assert_called_once_with(
        {
            "term": "guitarra",
            "category_id": None,
            "minimum_price": None,
            "maximum_price": None,
        }
    )
    assert reply.answer == "Encontrei uma guitarra disponível."
    assert reply.sources == (source,)
    assert "Guitar" in _last_tool_message(bound_model).content


def test_policy_question_uses_qdrant_tool_and_returns_page_source() -> None:
    source = SourceReference("document", "políticas_da_loja.pdf", 2)
    executor = MagicMock(return_value=ToolResult("Trocas em até 30 dias.", (source,)))
    agent, _ = _agent_for(
        tool_name=POLICY_TOOL,
        args_schema=PolicySearchInput,
        executor=executor,
        responses=[
            _tool_call(POLICY_TOOL, {"question": "Qual é o prazo de troca?"}),
            AIMessage(content="A troca pode ser feita em até 30 dias."),
        ],
    )

    reply = agent.answer("Qual é o prazo de troca?")

    executor.assert_called_once()
    assert reply.sources == (source,)


def test_promotion_question_uses_active_promotions_tool() -> None:
    source = SourceReference("database", "SQLite: promotions/products")
    executor = MagicMock(
        return_value=ToolResult('{"promotions": [{"discount": "10"}]}', (source,))
    )
    agent, _ = _agent_for(
        tool_name=PROMOTION_TOOL,
        args_schema=ActivePromotionsInput,
        executor=executor,
        responses=[
            _tool_call(PROMOTION_TOOL, {}),
            AIMessage(content="Há uma promoção ativa de 10%."),
        ],
    )

    reply = agent.answer("Quais promoções estão ativas?")

    executor.assert_called_once_with({})
    assert reply.sources == (source,)


def test_order_without_email_requests_confirmation_without_running_tool() -> None:
    executor = MagicMock()
    agent, bound_model = _agent_for(
        tool_name=ORDER_TOOL,
        args_schema=OrderLookupInput,
        executor=executor,
        responses=[
            _tool_call(ORDER_TOOL, {"order_id": 123}),
            AIMessage(content="Informe também o e-mail usado no pedido."),
        ],
    )

    reply = agent.answer("Onde está o pedido 123?")

    executor.assert_not_called()
    tool_message = _last_tool_message(bound_model)
    assert "order_id e o customer_email" in tool_message.content
    assert reply.sources == ()


def test_confirmed_order_runs_tool_with_id_and_email() -> None:
    source = SourceReference(
        "database", "SQLite: orders/customers/order_items/products"
    )
    executor = MagicMock(
        return_value=ToolResult('{"confirmed": true, "status": "shipped"}', (source,))
    )
    agent, _ = _agent_for(
        tool_name=ORDER_TOOL,
        args_schema=OrderLookupInput,
        executor=executor,
        responses=[
            _tool_call(
                ORDER_TOOL,
                {"order_id": 123, "customer_email": "client@example.com"},
            ),
            AIMessage(content="O pedido foi enviado."),
        ],
    )

    reply = agent.answer("Pedido 123, e-mail client@example.com")

    executor.assert_called_once_with(
        {"order_id": 123, "customer_email": "client@example.com"}
    )
    assert reply.sources == (source,)


def test_order_tool_checks_customer_email_before_returning_details(
    monkeypatch,
) -> None:
    order = OrderDetailResult(
        order_id=123,
        customer=CustomerResult(
            customer_id=1,
            name="Customer Name",
            phone="123",
            email="client@example.com",
            city="Campo Grande",
        ),
        items=(),
        order_date=date(2026, 1, 1),
        status="shipped",
        total_brl=Decimal("100.00"),
        payment_method="pix",
        tracking_code="BR123",
        estimated_delivery=date(2026, 1, 10),
        notes=None,
    )
    monkeypatch.setattr(
        "app.agent.tools.get_order_detail", lambda session, order_id: order
    )
    session_context = MagicMock()
    session_context.__enter__.return_value = MagicMock()
    tools = build_customer_tools(
        session_factory=MagicMock(return_value=session_context)
    )
    order_tool = next(tool for tool in tools if tool.tool.name == ORDER_TOOL)

    denied = order_tool.execute(
        {"order_id": 123, "customer_email": "other@example.com"}
    )
    confirmed = order_tool.execute(
        {"order_id": 123, "customer_email": "client@example.com"}
    )

    assert '"confirmed": false' in denied.content
    assert "shipped" not in denied.content
    assert "Customer Name" not in denied.content
    assert '"confirmed": true' in confirmed.content
    assert "shipped" in confirmed.content


def test_out_of_scope_question_returns_boundary_without_tools() -> None:
    executor = MagicMock()
    agent, bound_model = _agent_for(
        tool_name=PRODUCT_TOOL,
        args_schema=ProductSearchInput,
        executor=executor,
        responses=[
            AIMessage(
                content=(
                    "Posso ajudar apenas com produtos, pedidos e políticas da loja."
                )
            )
        ],
    )

    reply = agent.answer("Quem ganhou o campeonato?")

    executor.assert_not_called()
    first_messages = bound_model.invoke.call_args.args[0]
    assert isinstance(first_messages[0], SystemMessage)
    assert first_messages[0].content == SYSTEM_PROMPT
    assert "apenas" in reply.answer


def test_tool_failure_is_returned_to_model_without_fabricated_source() -> None:
    executor = MagicMock(side_effect=RuntimeError("database unavailable"))
    agent, bound_model = _agent_for(
        tool_name=PRODUCT_TOOL,
        args_schema=ProductSearchInput,
        executor=executor,
        responses=[
            _tool_call(PRODUCT_TOOL, {"term": "piano"}),
            AIMessage(content="Não consegui consultar os produtos agora."),
        ],
    )

    reply = agent.answer("Tem piano?")

    assert "Não invente dados" in _last_tool_message(bound_model).content
    assert reply.sources == ()


def test_post_chat_returns_answer_and_sources() -> None:
    fake_agent = MagicMock()
    fake_agent.answer.return_value = AgentReply(
        answer="Produto encontrado.",
        sources=(SourceReference("database", "SQLite: products/categories"),),
    )

    async def override_chat_agent():
        return fake_agent

    app.dependency_overrides[provide_chat_agent] = override_chat_agent

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "message": "Tem guitarra?",
                    "conversation_id": "conversation-1",
                },
            )

    try:
        response = asyncio.run(request())
    finally:
        app.dependency_overrides.pop(provide_chat_agent, None)
    assert response.status_code == 200
    assert response.json() == {
        "answer": "Produto encontrado.",
        "sources": [
            {
                "kind": "database",
                "name": "SQLite: products/categories",
                "page": None,
            }
        ],
    }
    fake_agent.answer.assert_called_once_with(
        "Tem guitarra?", conversation_id="conversation-1"
    )
