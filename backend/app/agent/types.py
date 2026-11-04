from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.tools import BaseTool


@dataclass(frozen=True)
class SourceReference:
    kind: Literal["database", "document"]
    name: str
    page: int | None = None


@dataclass(frozen=True)
class ToolResult:
    content: str
    sources: tuple[SourceReference, ...] = ()


@dataclass(frozen=True)
class RegisteredTool:
    tool: BaseTool
    execute: Callable[[dict[str, Any]], ToolResult]


@dataclass(frozen=True)
class AgentReply:
    answer: str
    sources: tuple[SourceReference, ...]
