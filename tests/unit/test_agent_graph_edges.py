from app.agent.graph import _after_critique, _after_retrieve, _after_router, _after_tools
from app.agent.state import MAX_TOOL_CALLS, GraphState


def _base_state(**overrides: object) -> GraphState:
    state: GraphState = {
        "messages": [],
        "is_out_of_scope_action": False,
        "customer_jwt": "fake-jwt",
        "needs_retrieval": False,
        "needs_tools": False,
        "retrieved_docs": [],
        "tool_call_count": 0,
        "needs_more_tools": False,
        "critique_verdict": None,
        "retried": False,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def test_after_router_prefers_retrieve_when_needed() -> None:
    state = _base_state(needs_retrieval=True, needs_tools=True)
    assert _after_router(state) == "retrieve"


def test_after_router_goes_to_tools_when_only_tools_needed() -> None:
    state = _base_state(needs_retrieval=False, needs_tools=True)
    assert _after_router(state) == "tools"


def test_after_router_goes_straight_to_critique_when_neither_needed() -> None:
    state = _base_state(needs_retrieval=False, needs_tools=False)
    assert _after_router(state) == "critique"


def test_after_retrieve_continues_to_tools_when_needed() -> None:
    state = _base_state(needs_tools=True)
    assert _after_retrieve(state) == "tools"


def test_after_retrieve_goes_to_critique_when_tools_not_needed() -> None:
    state = _base_state(needs_tools=False)
    assert _after_retrieve(state) == "critique"


def test_after_tools_loops_back_when_model_wants_more_and_budget_remains() -> None:
    state = _base_state(needs_more_tools=True, tool_call_count=1)
    assert _after_tools(state) == "tools"


def test_after_tools_stops_at_budget_even_if_model_wants_more() -> None:
    # This is the exact scenario the design almost got wrong: a real
    # infinite loop risk if "should continue" were derived from message
    # history instead of an explicit per-round flag.
    state = _base_state(needs_more_tools=True, tool_call_count=MAX_TOOL_CALLS)
    assert _after_tools(state) == "critique"


def test_after_tools_stops_when_model_has_no_more_tool_calls() -> None:
    state = _base_state(needs_more_tools=False, tool_call_count=1)
    assert _after_tools(state) == "critique"


def test_after_critique_answers_when_grounded() -> None:
    state = _base_state(critique_verdict="grounded", retried=False)
    assert _after_critique(state) == "answer"


def test_after_critique_retries_once_when_ungrounded() -> None:
    state = _base_state(critique_verdict="ungrounded", retried=False)
    assert _after_critique(state) == "mark_retry"


def test_after_critique_answers_anyway_after_already_retried() -> None:
    # Bounded retry: even a second "ungrounded" verdict must not loop again.
    state = _base_state(critique_verdict="ungrounded", retried=True)
    assert _after_critique(state) == "answer"
