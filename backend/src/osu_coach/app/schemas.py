"""Shared response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Request(BaseModel):
    """Base of request bodies: unknown fields are an error, not silently ignored."""

    model_config = ConfigDict(extra="forbid")


class Choice(BaseModel):
    key: str
    label: str


class Count(BaseModel):
    """A reason / name with how often it occurs."""

    label: str
    count: int
