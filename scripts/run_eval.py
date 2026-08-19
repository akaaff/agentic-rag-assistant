"""RAGAS evaluation against eval/golden_set.jsonl.

Judge model defaults to this app's own chat model (settings.ollama_chat_model,
qwen2.5:7b-instruct) but is overridable via EVAL_JUDGE_MODEL - Day 9's CI
job uses a much smaller model there for speed, with correspondingly relaxed
thresholds (see eval/thresholds.yaml's comments).

live_data/fusion golden cases never call the real order-fulfillment-platform
gateway - GatewayClient is patched with a fake returning each case's
mock_order, so this script has no dependency on the sibling repo's stack.
guardrail cases skip RAGAS scoring entirely (scope_check produces a fixed
template with no LLM call at all - there's nothing RAGAS-shaped to
evaluate) and are checked with a plain substring match instead.

Usage: uv run python -m scripts.run_eval
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
from langchain_core.messages import HumanMessage, ToolMessage
from openai import AsyncOpenAI
from ragas.embeddings import OpenAIEmbeddings
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

from app import asyncio_compat
from app.agent.graph import compile_graph
from app.config import settings
from app.gateway_client.models import OrderResponse

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_SET_PATH = REPO_ROOT / "eval" / "golden_set.jsonl"

# CI's fast job uses a much smaller/weaker judge model than local dev
# (qwen2.5:7b-instruct) - EVAL_THRESHOLDS_PATH lets it point at
# eval/thresholds.ci.yaml's deliberately relaxed values instead of
# thresholds.yaml's, rather than forcing one threshold set to fit both a
# strong local judge and a CPU-feasible CI one.
_DEFAULT_THRESHOLDS_PATH = REPO_ROOT / "eval" / "thresholds.yaml"
THRESHOLDS_PATH = Path(os.environ.get("EVAL_THRESHOLDS_PATH", _DEFAULT_THRESHOLDS_PATH))

JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", settings.ollama_chat_model)


class _FakeGatewayClientForEval:
    """Stands in for the real GatewayClient during eval - always returns
    the golden case's own mock_order, regardless of which order_id the
    model asks for. Good enough for eval purposes: each case is written
    around one specific mock order, so the model asking for anything else
    would itself be a sign the case should be marked wrong, not something
    this fake needs to model realistically."""

    def __init__(self, mock_order: OrderResponse | None) -> None:
        self._mock_order = mock_order

    async def get_order(self, order_id: str, token: str) -> OrderResponse | None:
        return self._mock_order

    async def search_orders(
        self, token: str, status: object = None, from_: object = None, to: object = None
    ) -> list[OrderResponse]:
        return [self._mock_order] if self._mock_order else []


@dataclass
class CaseResult:
    case_id: str
    case_type: str
    scores: dict[str, float]
    passed_guardrail_check: bool | None = None


def _load_golden_set() -> list[dict[str, Any]]:
    cases = []
    with GOLDEN_SET_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _build_mock_order(case: dict[str, Any]) -> OrderResponse | None:
    raw = case.get("mock_order")
    if raw is None:
        return None
    raw = dict(raw)
    if "mock_order_created_days_ago" in case:
        created_at = datetime.now(UTC) - timedelta(days=case["mock_order_created_days_ago"])
        raw["createdAt"] = created_at.isoformat()
    return OrderResponse.model_validate(raw)


async def _run_case(graph: Any, case: dict[str, Any]) -> dict[str, Any]:
    mock_order = _build_mock_order(case)
    initial_state = {
        "messages": [HumanMessage(case["question"])],
        "is_out_of_scope_action": False,
        "customer_jwt": "eval-fake-jwt",
        "needs_retrieval": False,
        "needs_tools": False,
        "retrieved_docs": [],
        "tool_call_count": 0,
        "needs_more_tools": False,
        "critique_verdict": None,
        "retried": False,
    }
    config = {"configurable": {"thread_id": f"eval-{case['id']}"}}

    with patch(
        "app.agent.nodes.tools.GatewayClient",
        lambda: _FakeGatewayClientForEval(mock_order),
    ):
        final_state = await graph.ainvoke(initial_state, config=config)

    answer = str(final_state["messages"][-1].content)
    doc_contexts = [doc.content for doc in final_state["retrieved_docs"]]
    tool_contexts = [str(m.content) for m in final_state["messages"] if isinstance(m, ToolMessage)]
    return {"answer": answer, "doc_contexts": doc_contexts, "tool_contexts": tool_contexts}


async def _score_case(
    llm: Any, embeddings: Any, case: dict[str, Any], result: dict[str, Any]
) -> CaseResult:
    if case["type"] == "guardrail":
        passed = case["expected_answer_contains"].lower() in result["answer"].lower()
        return CaseResult(
            case_id=case["id"], case_type=case["type"], scores={}, passed_guardrail_check=passed
        )

    all_contexts = result["doc_contexts"] + result["tool_contexts"]
    scores: dict[str, float] = {}

    answer_relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings)
    scores["answer_relevancy"] = (
        await answer_relevancy.ascore(user_input=case["question"], response=result["answer"])
    ).value

    if all_contexts:
        faithfulness = Faithfulness(llm=llm)
        scores["faithfulness"] = (
            await faithfulness.ascore(
                user_input=case["question"],
                response=result["answer"],
                retrieved_contexts=all_contexts,
            )
        ).value

    # context_precision/recall are specifically about DOC retrieval quality
    # (did hybrid search + rerank find the right doc chunks), not tool-call
    # quality - only scored when real doc retrieval happened and a
    # reference answer exists to compare against.
    if result["doc_contexts"] and "reference" in case:
        context_precision = ContextPrecision(llm=llm)
        scores["context_precision"] = (
            await context_precision.ascore(
                user_input=case["question"],
                reference=case["reference"],
                retrieved_contexts=result["doc_contexts"],
            )
        ).value

        context_recall = ContextRecall(llm=llm)
        scores["context_recall"] = (
            await context_recall.ascore(
                user_input=case["question"],
                retrieved_contexts=result["doc_contexts"],
                reference=case["reference"],
            )
        ).value

    return CaseResult(case_id=case["id"], case_type=case["type"], scores=scores)


def _aggregate(results: list[CaseResult]) -> dict[str, float]:
    totals: dict[str, list[float]] = {}
    for r in results:
        for metric, value in r.scores.items():
            totals.setdefault(metric, []).append(value)
    return {metric: sum(values) / len(values) for metric, values in totals.items()}


async def main() -> int:
    ollama_openai_client = AsyncOpenAI(base_url=f"{settings.ollama_base_url}/v1", api_key="ollama")
    llm = llm_factory(JUDGE_MODEL, provider="openai", client=ollama_openai_client)
    embeddings = OpenAIEmbeddings(
        client=AsyncOpenAI(base_url=f"{settings.ollama_base_url}/v1", api_key="ollama"),
        model=settings.ollama_embed_model,
    )

    graph = compile_graph(checkpointer=None)  # each golden case is a fresh, independent turn
    cases = _load_golden_set()

    results: list[CaseResult] = []
    guardrail_failures: list[str] = []
    for case in cases:
        print(f"Running case: {case['id']} ({case['type']})...", file=sys.stderr)
        result = await _run_case(graph, case)
        case_result = await _score_case(llm, embeddings, case, result)
        results.append(case_result)
        if case_result.passed_guardrail_check is False:
            guardrail_failures.append(case["id"])
        print(
            f"  scores={case_result.scores} guardrail_pass={case_result.passed_guardrail_check}",
            file=sys.stderr,
        )

    aggregated = _aggregate(results)
    thresholds = yaml.safe_load(THRESHOLDS_PATH.read_text(encoding="utf-8"))

    print("\n=== Aggregated scores ===")
    failed_metrics = []
    for metric, avg_score in aggregated.items():
        threshold = thresholds.get(metric)
        status = "OK"
        if threshold is not None and avg_score < threshold:
            status = "FAIL"
            failed_metrics.append(metric)
        print(f"{metric}: {avg_score:.3f} (threshold {threshold}) [{status}]")

    guardrail_total = sum(1 for c in cases if c["type"] == "guardrail")
    guardrail_passed = guardrail_total - len(guardrail_failures)
    print(f"\nGuardrail cases: {guardrail_passed}/{guardrail_total} passed")
    if guardrail_failures:
        print(f"FAILED guardrail cases: {guardrail_failures}")

    if failed_metrics or guardrail_failures:
        print("\nEVAL FAILED", file=sys.stderr)
        return 1
    print("\nEVAL PASSED", file=sys.stderr)
    return 0


if __name__ == "__main__":
    # Must run BEFORE asyncio.run() creates the event loop, not inside
    # main() - verified live (again) that calling it inside main() is too
    # late, same lesson as app/main.py's __main__ block on Day 7: by the
    # time main()'s body executes, asyncio.run() already picked Windows'
    # default ProactorEventLoop, and psycopg's async mode needs Selector.
    asyncio_compat.apply()
    sys.exit(asyncio.run(main()))
