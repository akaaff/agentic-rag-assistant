from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrderStatus(StrEnum):
    """Mirrors order-service's OrderStatus enum exactly - these 3 values are
    the whole state machine. There is no SHIPPED/DELIVERED - creation is
    async: POST /orders returns PENDING immediately, and the real outcome
    (CONFIRMED or CANCELLED) only becomes visible on a later GET/search."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class OrderLine(BaseModel):
    sku: str
    quantity: int


class OrderResponse(BaseModel):
    """Mirrors OrderResponse.java exactly (field names, camelCase aliases)."""

    model_config = ConfigDict(populate_by_name=True)

    order_id: UUID = Field(alias="orderId")
    customer_id: str = Field(alias="customerId")
    lines: list[OrderLine]
    status: OrderStatus
    cancellation_reason: str | None = Field(default=None, alias="cancellationReason")
    created_at: datetime = Field(alias="createdAt")


class OrderSearchDocument(BaseModel):
    """Mirrors OrderSearchDocument.java - same shape as OrderResponse plus
    updatedAt, minus the per-line detail (skus is a flat list of strings,
    not OrderLine objects, matching the search index's own projection)."""

    model_config = ConfigDict(populate_by_name=True)

    order_id: UUID = Field(alias="orderId")
    customer_id: str = Field(alias="customerId")
    status: OrderStatus
    skus: list[str]
    cancellation_reason: str | None = Field(default=None, alias="cancellationReason")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class LoginResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token: str
    customer_id: str = Field(alias="customerId")
    expires_at: datetime = Field(alias="expiresAt")
