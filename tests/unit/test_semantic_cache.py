from app.cache.semantic_cache import (
    GLOBAL_NAMESPACE,
    SIMILARITY_THRESHOLD,
    _cosine_similarity,
    get_cached_answer,
    store_answer,
)


class _FakeRedis:
    """In-memory stand-in for redis.asyncio.Redis - only get/set are used
    by semantic_cache.py, and both are trivial to fake exactly, unlike
    Postgres/SQLAlchemy (which is why store.py's tests are live-verified
    instead of mocked, but this one can be a real unit test)."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, name: str) -> str | None:
        return self._store.get(name)

    async def set(self, name: str, value: str) -> None:
        self._store[name] = value


def test_cosine_similarity_identical_vectors() -> None:
    import numpy as np

    v = np.array([1.0, 2.0, 3.0])
    assert _cosine_similarity(v, v) == 1.0


def test_cosine_similarity_orthogonal_vectors() -> None:
    import numpy as np

    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert abs(_cosine_similarity(a, b)) < 1e-9


async def test_store_answer_writes_pure_doc_answer_to_global_namespace() -> None:
    redis = _FakeRedis()

    await store_answer(
        redis,
        customer_id="cust-001",
        touched_live_data=False,
        query="What's your return policy?",
        query_embedding=[1.0, 0.0],
        answer="30 days for unused items.",
    )

    assert await redis.get("semantic_cache:global") is not None
    assert await redis.get("semantic_cache:customer:cust-001") is None


async def test_store_answer_writes_live_data_answer_to_customer_namespace() -> None:
    redis = _FakeRedis()

    await store_answer(
        redis,
        customer_id="cust-001",
        touched_live_data=True,
        query="Why was my order cancelled?",
        query_embedding=[1.0, 0.0],
        answer="Order X was cancelled due to insufficient stock.",
    )

    assert await redis.get("semantic_cache:customer:cust-001") is not None
    assert await redis.get("semantic_cache:global") is None


async def test_get_cached_answer_hits_on_near_identical_embedding() -> None:
    redis = _FakeRedis()
    await store_answer(
        redis,
        customer_id="cust-001",
        touched_live_data=False,
        query="What's your return policy?",
        query_embedding=[1.0, 0.0],
        answer="cached policy answer",
    )

    result = await get_cached_answer(redis, "cust-001", query_embedding=[1.0, 0.0001])

    assert result == "cached policy answer"


async def test_get_cached_answer_misses_below_similarity_threshold() -> None:
    redis = _FakeRedis()
    await store_answer(
        redis,
        customer_id="cust-001",
        touched_live_data=False,
        query="What's your return policy?",
        query_embedding=[1.0, 0.0],
        answer="cached policy answer",
    )

    # Orthogonal vector - similarity 0.0, nowhere near SIMILARITY_THRESHOLD.
    result = await get_cached_answer(redis, "cust-001", query_embedding=[0.0, 1.0])

    assert result is None
    assert SIMILARITY_THRESHOLD > 0.5  # sanity: threshold is meaningfully strict


async def test_get_cached_answer_never_leaks_another_customers_namespace() -> None:
    """The actual security property: cust-002's live-order-data answer must
    never be visible to cust-001, even when cust-001 asks something with a
    near-identical embedding."""
    redis = _FakeRedis()
    await store_answer(
        redis,
        customer_id="cust-002",
        touched_live_data=True,
        query="Why was my order cancelled?",
        query_embedding=[1.0, 0.0],
        answer="cust-002's private order details",
    )

    result = await get_cached_answer(redis, "cust-001", query_embedding=[1.0, 0.0001])

    assert result is None


async def test_get_cached_answer_checks_customer_namespace_before_global() -> None:
    redis = _FakeRedis()
    await store_answer(
        redis,
        customer_id="cust-001",
        touched_live_data=False,
        query="q",
        query_embedding=[1.0, 0.0],
        answer="global answer",
    )
    await store_answer(
        redis,
        customer_id="cust-001",
        touched_live_data=True,
        query="q",
        query_embedding=[1.0, 0.0],
        answer="customer-specific answer",
    )

    result = await get_cached_answer(redis, "cust-001", query_embedding=[1.0, 0.0])

    assert result == "customer-specific answer"


def test_global_namespace_constant_is_stable() -> None:
    # Guards against an accidental rename breaking the customer/global split
    # silently (e.g. a customer_id that happens to equal "global").
    assert GLOBAL_NAMESPACE == "global"
