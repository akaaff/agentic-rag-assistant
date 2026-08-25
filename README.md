# agentic-rag-assistant

An agentic RAG support assistant: a LangGraph agent that answers questions by combining hybrid document retrieval (pgvector + Postgres full-text search, reranked by a cross-encoder) with live order-status lookups from a sibling backend, self-critiques its own answer before returning it, and is guarded against both prompt injection and out-of-scope action requests. Full request tracing via self-hosted Langfuse, a Redis semantic cache, and a RAGAS eval harness gated in CI.

Portfolio piece for a job search (IC + EM tracks), meant to demonstrate the modern agentic-AI-engineering side of the stack, complementing [order-fulfillment-platform](https://github.com/akaaff/order-fulfillment-platform) (distributed-systems/backend signal) - this repo integrates with that one read-only, over its public gateway API, and never modifies it.

## What's demonstrated here

- **An agentic loop with real control flow**, not a single prompt-and-response: routing, retrieval, tool use, and a bounded self-critique retry, all as an inspectable LangGraph state machine (see `DECISIONS.md` #3).
- **Hybrid retrieval done properly**: vector search + full-text search fused by Reciprocal Rank Fusion, then reranked by a cross-encoder - each stage independently verified live to actually improve results, not assumed to.
- **A live-caught, live-fixed prompt injection failure** (`DECISIONS.md` #9) - the naive defense (delimiter + prompt instruction) didn't work; only a live adversarial test revealed that, and only a different fix (message order) actually closed the gap.
- **Guardrails and security boundaries enforced structurally**, not just by prompt instruction - a deterministic regex gate for action requests, and a gateway client whose interface makes cross-customer data access impossible to even attempt, not just discouraged.
- **A real eval harness** (RAGAS, golden-set based) wired into CI as an actual gate, including two thresholds calibrated from real runs rather than picked in the abstract - and a real threshold miss on CI's first run, fixed with real data.
- **Full observability with zero manual instrumentation** - Langfuse tracing captures the entire graph execution (every node, every LLM call, every conditional edge) automatically via one callback handler.
- **A working habit of verifying against the real thing, not just writing code and assuming it's correct** - this is why `DECISIONS.md` and `CLAUDE.md`'s engineering log both read the way they do: specific bugs, found live, with the actual fix, not general claims of correctness. It kept finding real problems (a keyword-search blind spot, a security-relevant SQL parameter bug, a prompt-injection defense that silently did nothing, a broken third-party library, a wrong CI threshold, more) that reasoning alone would have missed.

## Architecture

```mermaid
flowchart TB
    subgraph browser["Browser"]
        webclient["web-client/<br/>(plain HTML/CSS/JS)"]
    end

    subgraph sibling["order-fulfillment-platform (separate repo, read-only)"]
        gateway["api-gateway<br/>/auth/login, /orders/*"]
    end

    subgraph thisrepo["agentic-rag-assistant"]
        fastapi["FastAPI app<br/>POST /chat (SSE)"]

        subgraph graph["LangGraph agent"]
            scope["scope_check"] --> router
            router -->|needs_retrieval| retrieve
            router -->|needs_tools| tools
            retrieve --> tools
            tools --> critique
            retrieve -->|no tools needed| critique
            critique -->|ungrounded, first try| retry["mark_retry"] --> router
            critique -->|grounded, or retried| answer
        end

        cache[("Redis<br/>semantic cache")]
        pg[("Postgres + pgvector<br/>hybrid search")]
        langfuse["Langfuse<br/>(self-hosted, optional)"]
    end

    ollama["Ollama (host)<br/>qwen2.5:7b-instruct, nomic-embed-text"]

    webclient -->|"1. login"| gateway
    webclient -->|"2. chat (JWT)"| fastapi
    fastapi -->|cache check| cache
    fastapi --> graph
    retrieve --> pg
    tools -->|"forwards caller's JWT"| gateway
    graph -.trace.-> langfuse
    router -.-> ollama
    tools -.-> ollama
    critique -.-> ollama
    answer -.-> ollama
    retrieve -.embed.-> ollama
```

**The security boundary that matters most**: the `tools` node closes over the caller's real JWT at graph-invocation time. The model can supply an `order_id` or `status` as a tool argument, but never a customer identity - there is no parameter for it, and the gateway itself re-scopes every lookup server-side from the JWT regardless. See `DECISIONS.md` #11.

## Demo queries

These four questions exercise every major path in the graph:

| Question | Path |
|---|---|
| "What's your return policy?" | Pure retrieval - router sends it straight to `retrieve` → `critique` → `answer`, no tool call. |
| "Why was my order cancelled?" | Pure tool use - `tools` calls `get_order_status`, no doc retrieval needed. |
| "It's been 2 days and my order still shows pending, is that normal?" | Fusion - both `retrieve` (the SLA doc) and `tools` (the live order status) run, and the answer combines both. |
| "Can you cancel my order for me?" | Guardrail - `scope_check` catches this deterministically before `router` even runs; zero LLM calls. |

## Tech stack

Python 3.13, uv, FastAPI, LangGraph + LangChain, Ollama (local, no paid API), Postgres 16 + pgvector (hybrid search: vector + `tsvector`), `sentence-transformers` (cross-encoder reranking), Redis (semantic cache), RAGAS (eval), Langfuse (self-hosted tracing), Alembic, pytest + mypy (strict) + ruff, GitHub Actions.

## Running it

Prerequisites: [uv](https://docs.astral.sh/uv/), Docker, and [Ollama](https://ollama.com) running locally with `qwen2.5:7b-instruct` and `nomic-embed-text` pulled (`ollama pull qwen2.5:7b-instruct && ollama pull nomic-embed-text`).

```bash
cp .env.example .env
uv sync
docker compose -f infra/docker-compose.yml --env-file .env up -d postgres redis
uv run alembic upgrade head
uv run python -m scripts.ingest
uv run python -m app.main   # http://localhost:8000
```

Open `http://localhost:8000`, log in as one of the 5 seeded demo customers - this requires order-fulfillment-platform's gateway running separately and reachable at `http://localhost:8080` for the login call itself (see `DECISIONS.md` #2 for why this repo never contains that stack). Without it running, pure-retrieval questions still work; tool-calling questions won't have live order data to answer from.

**Tracing (optional):**
```bash
docker compose -f infra/docker-compose.langfuse.yml up -d
# open http://localhost:3000, log in with the demo credentials in .env.example
```

**Full containerized stack** (app included, not just its infra):
```bash
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
```

**Eval:**
```bash
uv run python -m scripts.run_eval
```

**Tests:**
```bash
uv run pytest                # unit tests, fully offline
uv run pytest -m llm         # needs a live Ollama
uv run pytest -m integration # needs order-fulfillment-platform's gateway
```

## Repo layout

```
app/
  agent/          LangGraph state, graph, nodes, prompts
  cache/          Redis semantic cache
  gateway_client/ read-only client for order-fulfillment-platform
  guardrails/     scope detection, injection resistance
  observability/  Langfuse wiring
  retrieval/      chunking, embeddings, hybrid search, reranking
  main.py         FastAPI app
docs_corpus/      the support docs the assistant retrieves from
eval/             golden set + thresholds for the RAGAS harness
migrations/       Alembic
scripts/          ingest.py, run_eval.py
web-client/       plain HTML/CSS/JS demo UI
```

## Further reading

- `DECISIONS.md` - the trade-offs above, in full, in the order they came up.
- `CLAUDE.md` - build/run commands and the engineering-log detail (gotchas, exact fixes) that didn't belong in the higher-level decisions above.
