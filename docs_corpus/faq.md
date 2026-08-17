# Frequently asked questions

## What do the order statuses mean?

- **PENDING** — order placed, stock reservation in progress. Normally resolves within about an
  hour (see `fulfillment-sla.md`).
- **CONFIRMED** — stock reserved for every item, order is being fulfilled. Final state.
- **CANCELLED** — at least one item was out of stock, so the whole order was cancelled (see
  `backorder-cancellation-explainer.md`). Final state. You are not charged for a cancelled order.

## How do I check my order status?

Ask this assistant about a specific order by its order ID, or ask it to list your recent orders
(optionally filtered by status).

## Can I change what's in an order after placing it?

No — orders cannot be edited after being placed. If it's still PENDING, contact support; if it's
already CONFIRMED, see the return policy instead.

## Do you offer partial refunds on damaged items?

Refunds for damaged items are full refunds for the affected item, not partial — see
`return-policy.md` for the damaged-item process and timeline.

## Who do I contact for something this assistant can't help with?

This assistant only has read access to your own order data and to these support documents. For
anything requiring an account change — cancellations, refunds, address changes — contact support
directly and reference your order ID.
