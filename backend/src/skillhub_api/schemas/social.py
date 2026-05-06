"""DTOs for star / rating / subscription endpoints."""

from __future__ import annotations

from pydantic import Field

from skillhub_api.schemas.base import ApiModel


class BooleanResponse(ApiModel):
    value: bool


class RatingRequest(ApiModel):
    score: int = Field(ge=1, le=5)


class RatingStatusResponse(ApiModel):
    score: int
    has_rated: bool
