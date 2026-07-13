from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.llm.base import ToolSpec

# Async tool callable: receives parsed arguments as keyword arguments.
ToolFunc = Callable[..., Awaitable[Any]]


class ToolRegistry:
    """Registry mapping tool name -> (ToolSpec, async callable)."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolSpec, ToolFunc]] = {}

    def register(self, spec: ToolSpec, func: ToolFunc) -> None:
        """Register a tool under ``spec.name`` (overwrites on collision)."""
        self._tools[spec.name] = (spec, func)

    def specs(self) -> list[ToolSpec]:
        """Tool specs to pass to ``llm.complete(tools=...)``."""
        return [spec for spec, _ in self._tools.values()]

    def get(self, name: str) -> tuple[ToolSpec, ToolFunc] | None:
        """Look up a tool by name; ``None`` if unknown."""
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())
