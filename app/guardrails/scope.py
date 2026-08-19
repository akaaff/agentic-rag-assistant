from __future__ import annotations

import re

# Deliberately pattern-based (verb + target co-occurring nearby), not a
# single exact phrase - catches "cancel my order", "please refund this
# purchase", "can you modify my order", etc. "return" is deliberately NOT
# in the verb list: "what's your return policy" needs to reach the normal
# retrieval path (return-policy.md answers it directly), not get diverted
# into a hard decline.
_ACTION_VERBS = r"cancel|refund|modify|change|update|edit|reverse|undo|stop"
_ACTION_TARGETS = r"order|purchase|payment|charge"

_ACTION_REQUEST_PATTERN = re.compile(
    rf"\b({_ACTION_VERBS})\b.{{0,40}}\b({_ACTION_TARGETS})\b"
    rf"|\b({_ACTION_TARGETS})\b.{{0,40}}\b({_ACTION_VERBS})\b",
    re.IGNORECASE,
)


def is_action_request(text: str) -> bool:
    """True if the text looks like a request for this assistant to *do*
    something to an order (cancel/refund/modify/...), not just tell the
    user information.

    This assistant has zero write capability - gateway_client only exposes
    login/get_order/search_orders - so any such request must be declined.
    Doing that via a deterministic check, not just the answer prompt's own
    judgment, means the decline can't be talked out of by clever phrasing,
    a degraded model response, or a prompt-injection attempt riding in on
    retrieved doc content.
    """
    return bool(_ACTION_REQUEST_PATTERN.search(text))


ACTION_DECLINE_TEMPLATE = (
    "I can't cancel, refund, or modify orders myself - I only have read access "
    "to order status and history, no write access at all. If your order is "
    "still PENDING, contact support with your order ID and they may be able to "
    "stop it before it's confirmed. For a CONFIRMED order, support can help "
    "with cancellation, returns, or refunds directly."
)
