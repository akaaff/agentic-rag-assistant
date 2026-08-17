# Why was my order cancelled?

## The most common reason: insufficient stock

The platform reserves stock for an order **all-or-nothing across every line item**. If you ordered
three different products and even one of them is out of stock, the **entire order** is cancelled —
not just the unavailable item. We do not partially fulfill orders.

This is a deliberate design choice: partial fulfillment creates its own problems (partial charges,
partial shipments, confused customers), and all-or-nothing keeps the guarantee simple — if your
order is CONFIRMED, everything in it is being fulfilled.

## Is there a waitlist or automatic backorder?

**No.** There is currently no automatic backorder or waitlist feature. A cancelled order does not
automatically retry once stock is replenished. If you still want the items, you'll need to place a
new order once stock is available.

## How do I know why a specific order was cancelled?

Every cancelled order has a specific reason attached (for example, which item was out of stock).
Ask about a specific order by its order ID and the reason will be included if the order was in
fact cancelled.

## Can a cancelled order be reinstated?

No — CANCELLED is a final state, same as CONFIRMED. There is no self-service way to reverse it;
see `cancellation-policy.md` for what self-service actions do exist.
