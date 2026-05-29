"""Pydantic schema — single source of truth for what a failure is.

Every invariant is enforced at construction time; a malformed event can never reach
the store. ``FailureEvent`` is caller-supplied input; ``FailureRecord`` extends it with
substrate-computed fields (sequence, hashes).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from failure_log.failure_classes import FailureClass

FailureId = UUID

ROOT_CAUSE_MIN_LEN = 20
ROOT_CAUSE_MAX_LEN = 2000


class SeverityTier(str, Enum):
    """Closed five-mode severity enumeration."""

    INFO = "INFO"
    WARN = "WARN"
    RECOVERABLE = "RECOVERABLE"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class DownstreamImpactEnvelope(str, Enum):
    """Closed three-mode blast-radius enumeration."""

    ISOLATED = "ISOLATED"
    LOCAL_CASCADE = "LOCAL_CASCADE"
    CROSS_COMPONENT_CASCADE = "CROSS_COMPONENT_CASCADE"


class FailureEvent(BaseModel):
    """Caller-supplied input. ``timestamp`` is optional; substrate stamps it if omitted."""

    model_config = {"extra": "forbid"}

    failure_class: FailureClass
    severity_tier: SeverityTier
    downstream_impact_envelope: DownstreamImpactEnvelope
    originating_component_id: str = Field(min_length=1, max_length=256)
    root_cause_hypothesis: str = Field(
        min_length=ROOT_CAUSE_MIN_LEN, max_length=ROOT_CAUSE_MAX_LEN
    )
    parent_failure_id: UUID | None = None
    timestamp: datetime | None = None


class FailureRecord(FailureEvent):
    """Full persisted form. Frozen — immutable by construction, mirroring the append-only store."""

    model_config = {"frozen": True, "extra": "forbid"}

    failure_id: FailureId = Field(default_factory=uuid4)
    sequence: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    parent_hash: str


class FailureQuery(BaseModel):
    """Filter set for ``query()``. All fields optional."""

    model_config = {"extra": "forbid"}

    originating_component_id: str | None = None
    failure_class: FailureClass | None = None
    severity_tier: SeverityTier | None = None
    downstream_impact_envelope: DownstreamImpactEnvelope | None = None
    parent_failure_id: UUID | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class AggregationBucket(BaseModel):
    """One output row of ``aggregate()``: a group-key/date bucket and its count."""

    keys: dict[str, str]
    date_bucket: str
    count: int


class FailureAggregation(BaseModel):
    """Result of ``aggregate()`` — the group-by dimensions and the counted buckets."""

    group_by: list[str]
    buckets: list[AggregationBucket]


class CascadeChain(BaseModel):
    """Result of ``cascade_path()``.

    ``path``: ancestor chain, root-first to target.
    ``siblings``: other nodes in the cascade tree that share an ancestor with the target.
    """

    target_id: FailureId
    path: list[FailureRecord]
    siblings: list[FailureRecord]

    @property
    def root(self) -> FailureRecord | None:
        return self.path[0] if self.path else None

    @property
    def depth(self) -> int:
        return len(self.path)
