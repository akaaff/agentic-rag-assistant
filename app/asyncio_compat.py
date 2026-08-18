"""Windows-only asyncio compatibility shim.

psycopg3's async mode is incompatible with Windows' default ProactorEventLoop
(it requires a SelectorEventLoop) - this only matters for local dev/scripts
run directly on Windows. The Docker containers this app actually deploys
into are Linux, where ProactorEventLoop doesn't exist and this is a no-op.

Call apply() once, as early as possible, in any process entrypoint that
opens an async DB connection (scripts/ingest.py, app/main.py, tests).
"""

from __future__ import annotations

import asyncio
import sys


def apply() -> None:
    if sys.platform != "win32":
        return
    # getattr, not a direct attribute access: typeshed only declares
    # WindowsSelectorEventLoopPolicy under a `sys.platform == "win32"` guard,
    # so a direct reference fails mypy when it type-checks under a
    # non-Windows platform assumption (e.g. the Linux CI runners in Day 9).
    policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_cls is not None:
        asyncio.set_event_loop_policy(policy_cls())
