"""Test support code (not a test module itself - no test_ prefix)."""

from __future__ import annotations

from typing import Any


class FakeChatModel:
    """Minimal stand-in for ChatOllama in tests: implements just enough of
    the chain our nodes actually call - .bind_tools()/.with_structured_output()
    returning self, then .ainvoke() returning the next pre-programmed
    response - without needing a real Ollama call or LangChain's own fake
    model utilities, which don't cleanly simulate tool-calling/structured
    output for our purposes."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)

    def bind_tools(self, tools: Any) -> FakeChatModel:
        return self

    def with_structured_output(self, schema: Any) -> FakeChatModel:
        return self

    async def ainvoke(self, messages: Any) -> Any:
        return self._responses.pop(0)
