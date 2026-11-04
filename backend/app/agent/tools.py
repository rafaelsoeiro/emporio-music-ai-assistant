import json
from collections.abc import Callable
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.types import RegisteredTool, SourceReference, ToolResult
from app.db.session import SessionLocal
from app.rag.retriever import PolicyRetriever
from app.services.read_queries import (
    get_active_promotions,
    get_order_detail,
    search_available_products,
)

PRODUCT_TOOL = "search_products"
PROMOTION_TOOL = "get_active_promotions"
POLICY_TOOL = "search_store_policies"
ORDER_TOOL = "get_order"


class ProductSearchInput(BaseModel):
    term: str | None = Field(default=None, description="Termo em nome ou descrição")
    category_id: int | None = Field(default=None, gt=0)
    minimum_price: Decimal | None = Field(default=None, ge=0)
    maximum_price: Decimal | None = Field(default=None, ge=0)


class ActivePromotionsInput(BaseModel):
    pass


class PolicySearchInput(BaseModel):
    question: str = Field(min_length=1, description="Pergunta sobre políticas da loja")


class OrderLookupInput(BaseModel):
    order_id: int = Field(gt=0)
    customer_email: str = Field(min_length=3)


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def create_registered_tool(
    *,
    name: str,
    description: str,
    args_schema: type[BaseModel],
    executor: Callable[[dict[str, Any]], ToolResult],
) -> RegisteredTool:
    def exposed_tool(**kwargs: Any) -> str:
        return executor(kwargs).content

    tool = StructuredTool.from_function(
        func=exposed_tool,
        name=name,
        description=description,
        args_schema=args_schema,
    )
    return RegisteredTool(tool=tool, execute=executor)


def build_customer_tools(
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    retriever_factory: Callable[[], PolicyRetriever] = PolicyRetriever.from_settings,
) -> list[RegisteredTool]:
    def search_products(payload: dict[str, Any]) -> ToolResult:
        arguments = ProductSearchInput.model_validate(payload)
        with session_factory() as session:
            products = search_available_products(session, **arguments.model_dump())
        return ToolResult(
            content=_json({"products": [asdict(product) for product in products]}),
            sources=(SourceReference("database", "SQLite: products/categories"),),
        )

    def active_promotions(payload: dict[str, Any]) -> ToolResult:
        ActivePromotionsInput.model_validate(payload)
        with session_factory() as session:
            promotions = get_active_promotions(session)
        return ToolResult(
            content=_json(
                {"promotions": [asdict(promotion) for promotion in promotions]}
            ),
            sources=(SourceReference("database", "SQLite: promotions/products"),),
        )

    def search_policies(payload: dict[str, Any]) -> ToolResult:
        arguments = PolicySearchInput.model_validate(payload)
        with retriever_factory() as retriever:
            chunks = retriever.retrieve(arguments.question)
        return ToolResult(
            content=_json({"policy_chunks": [asdict(chunk) for chunk in chunks]}),
            sources=tuple(
                SourceReference("document", chunk.source, chunk.page)
                for chunk in chunks
            ),
        )

    def lookup_order(payload: dict[str, Any]) -> ToolResult:
        arguments = OrderLookupInput.model_validate(payload)
        with session_factory() as session:
            order = get_order_detail(session, arguments.order_id)

        email_matches = (
            order is not None
            and order.customer.email.casefold()
            == arguments.customer_email.strip().casefold()
        )
        if not email_matches:
            return ToolResult(
                content=_json(
                    {
                        "confirmed": False,
                        "message": (
                            "Não foi possível confirmar o pedido com os dados "
                            "informados."
                        ),
                    }
                ),
                sources=(
                    SourceReference(
                        "database", "SQLite: orders/customers/order_items/products"
                    ),
                ),
            )

        return ToolResult(
            content=_json({"confirmed": True, "order": asdict(order)}),
            sources=(
                SourceReference(
                    "database", "SQLite: orders/customers/order_items/products"
                ),
            ),
        )

    return [
        create_registered_tool(
            name=PRODUCT_TOOL,
            description=(
                "Busca produtos ativos e em estoque por termo, categoria e faixa de "
                "preço. Use antes de afirmar produto, preço ou disponibilidade."
            ),
            args_schema=ProductSearchInput,
            executor=search_products,
        ),
        create_registered_tool(
            name=PROMOTION_TOOL,
            description="Lista promoções ativas com preço original e preço final.",
            args_schema=ActivePromotionsInput,
            executor=active_promotions,
        ),
        create_registered_tool(
            name=POLICY_TOOL,
            description=(
                "Recupera trechos do PDF de políticas da loja para responder sobre "
                "trocas, devoluções, entrega e outras regras."
            ),
            args_schema=PolicySearchInput,
            executor=search_policies,
        ),
        create_registered_tool(
            name=ORDER_TOOL,
            description=(
                "Consulta um pedido somente após receber order_id e customer_email "
                "para confirmação."
            ),
            args_schema=OrderLookupInput,
            executor=lookup_order,
        ),
    ]
