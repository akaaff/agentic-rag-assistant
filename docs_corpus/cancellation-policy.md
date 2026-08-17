# Cancellation policy

## Can I cancel my own order?

**Not through self-service today.** There is currently no in-app or in-chat action to cancel an
order yourself. This assistant can look up your order's status and explain what it means, but it
cannot cancel, modify, or refund an order on your behalf — it only has read access to order data.

## What are my options depending on order status?

- **PENDING** — the order hasn't been confirmed yet. Contact support directly and reference your
  order ID; if it hasn't been reserved yet, support can stop it before it's CONFIRMED.
- **CONFIRMED** — stock has been reserved and the order is being fulfilled. At this point it
  generally cannot be stopped through a simple request; contact support to discuss options.
- **CANCELLED** — the order was already stopped automatically, most commonly due to insufficient
  stock (see `backorder-cancellation-explainer.md`). No action is needed on your end.

## Why doesn't the assistant just cancel it for me?

By design, this assistant only has read-only access to order data (status lookups and search) —
it was never given the ability to place, modify, or cancel orders, precisely so a support
conversation can't accidentally (or maliciously) trigger an unintended account action. Any request
to "cancel my order" should be answered with this policy and a pointer to support, not treated as
something the assistant can just do.
