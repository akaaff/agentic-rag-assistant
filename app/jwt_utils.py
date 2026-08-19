from __future__ import annotations

import base64
import json


def extract_customer_id(token: str) -> str:
    """Decode (NOT verify) the JWT's payload to read the `sub` claim, for
    cache-namespacing purposes only.

    Signature verification is deliberately NOT done here -
    order-fulfillment-platform's gateway independently re-verifies the same
    token's RS256 signature on every actual data call (get_order/
    search_orders), which is the real authorization boundary, same as the
    sibling repo's own defense-in-depth pattern. A forged or garbage token
    reaching this function can only misplace a semantic-cache entry into
    the wrong (or a malformed) namespace; it can never grant access to real
    order data, since GatewayClient always forwards the caller's raw token
    for the sibling gateway to verify itself, independent of anything
    decided here.
    """
    try:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return str(payload["sub"])
    except (IndexError, ValueError, KeyError) as e:
        raise ValueError("Malformed JWT: cannot extract customer id") from e
