---
doc_type: policy
category: sla
title: Fulfillment SLA
---

# Fulfillment SLA

## How long does confirmation take?

When you place an order, it starts in **PENDING** status. Behind the scenes, the platform checks
stock for every item in the order and reserves it. This normally completes **within about an
hour** of the order being placed — in practice it is usually much faster (minutes), since it is an
automated, event-driven process with no manual review step.

Once that check finishes, your order moves to one of two final states:

- **CONFIRMED** — stock was available for every item, your order is being fulfilled.
- **CANCELLED** — stock was not available for at least one item (see
  `backorder-cancellation-explainer.md` for why the whole order is cancelled rather than partially
  fulfilled).

## When is a PENDING order considered delayed?

**If an order has been PENDING for longer than 24 hours, this is outside normal SLA and should be
treated as a delay**, not a normal wait. This should not happen under regular operation — a PENDING
order stuck past this window usually indicates a processing issue on our side, not a stock
shortage (a stock shortage resolves quickly, into CANCELLED, not by staying PENDING). If you see
this, contact support with your order ID.

## What happens after CONFIRMED or CANCELLED?

Both are final states. There is currently no further status beyond CONFIRMED (no separate
"shipped" or "delivered" tracking stage) and no self-service way to change an order's status once
it leaves PENDING — see `cancellation-policy.md`.
