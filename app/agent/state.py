from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.retrieval.store import SearchResult

# Hard budget on tool-calling iterations within a single turn - distinct
# from the critique node's own single-retry allowance (`retried` below).
# Two separate counters so a runaway tool-call loop can't hide behind "it's
# still on its one critique retry".
MAX_TOOL_CALLS = 3


class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

    # Set by scope_check_node (nodes/scope_check.py), the graph's entry
    # point - a deterministic (regex-based, not model-judged) check for
    # "is the user asking me to DO something I have no tool for". When
    # True, scope_check_node writes the decline itself and the graph edges
    # straight to END, skipping router/retrieve/tools/critique/answer
    # entirely - a phrasing trick or a degraded model response can't talk
    # this check out of declining, unlike relying on the answer prompt alone.
    is_out_of_scope_action: bool

    # Bound once per graph invocation from the caller's real JWT - never a
    # model-suppliable value. The tools node closes over this; the model
    # only ever controls which tool and what arguments (e.g. order_id), the
    # same boundary the sibling repo's OrderTools enforces.
    customer_jwt: str

    # Router's decision (see nodes/router.py).
    needs_retrieval: bool
    needs_tools: bool

    retrieved_docs: list[SearchResult]
    tool_call_count: int
    # Set explicitly by tools_node every invocation (True only if it just
    # executed a tool call, never left stale from a prior round) - the
    # tools<->tools loop-back edge reads this, not "was the last message a
    # ToolMessage", which would still be true on the round *after* the model
    # stopped calling tools and cause an infinite loop.
    needs_more_tools: bool

    # Critique's verdict (see nodes/critique.py) - None until critique runs.
    critique_verdict: Literal["grounded", "ungrounded"] | None
    retried: bool
