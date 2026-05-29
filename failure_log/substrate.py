"""FailureSubstrate — public interface for the failure-logging substrate.

All writes flow through ``log_failure``; the hash chain is computed here before the
record reaches the store, keeping the store a pure persistence layer.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from failure_log.models import (
    CascadeChain,
    FailureAggregation,
    FailureEvent,
    FailureId,
    FailureQuery,
    FailureRecord,
)
from failure_log.store import GENESIS_HASH, FailureStore, make_engine


def _record_hash(r: FailureRecord) -> str:
    """Canonical hash of a stored record — used as the next record's parent_hash."""
    data = "".join([
        str(r.failure_id),
        str(r.sequence),
        r.timestamp.isoformat(),
        r.failure_class.value,
        r.severity_tier.value,
        r.downstream_impact_envelope.value,
        r.originating_component_id,
        r.root_cause_hypothesis,
        str(r.parent_failure_id) if r.parent_failure_id is not None else "",
        r.parent_hash,
    ])
    return hashlib.sha256(data.encode()).hexdigest()


class FailureSubstrate:

    def __init__(self, db_url: str = "sqlite:///:memory:") -> None:
        self._store = FailureStore(make_engine(db_url))

    def log_failure(self, failure: FailureEvent) -> FailureId:
        """Validate, hash-chain, and persist a failure. Returns the new failure_id."""
        timestamp = failure.timestamp or datetime.now(timezone.utc)

        latest = self._store.get_latest()
        if latest is None:
            parent_hash = GENESIS_HASH
            sequence = 0
        else:
            parent_hash = _record_hash(latest)
            sequence = latest.sequence + 1

        record = FailureRecord(
            failure_id=uuid4(),
            sequence=sequence,
            timestamp=timestamp,
            failure_class=failure.failure_class,
            severity_tier=failure.severity_tier,
            downstream_impact_envelope=failure.downstream_impact_envelope,
            originating_component_id=failure.originating_component_id,
            root_cause_hypothesis=failure.root_cause_hypothesis,
            parent_failure_id=failure.parent_failure_id,
            parent_hash=parent_hash,
        )
        self._store.insert(record)
        return record.failure_id

    def query(self, filters: FailureQuery) -> list[FailureRecord]:
        """Return all failures matching the given filters, ordered by sequence."""
        return self._store.query(filters)

    def aggregate(
        self,
        time_window: tuple[datetime, datetime],
        group_by: list[str],
    ) -> FailureAggregation:
        """Count failures grouped by the requested dimensions plus a per-day bucket.

        group_by must be a non-empty subset of:
          {originating_component_id, failure_class, severity_tier,
           downstream_impact_envelope}
        """
        if not group_by:
            raise ValueError("group_by must contain at least one dimension")
        start, end = time_window
        buckets = self._store.aggregate(group_by, start, end)
        return FailureAggregation(group_by=group_by, buckets=buckets)

    def cascade_path(
        self,
        failure_id: FailureId,
        time_window: tuple[datetime, datetime] | None = None,
    ) -> CascadeChain:
        """Return the cascade chain for the given failure.

        Walks ``parent_failure_id`` upward to the root via a recursive CTE, then
        collects sibling branches (nodes reachable from the root not on the ancestor
        path). ``time_window`` narrows siblings by timestamp; the path is always full.
        Raises ``KeyError`` if ``failure_id`` is not found.
        """
        path, siblings = self._store.cascade_path(failure_id, time_window)
        if not path:
            raise KeyError(f"No failure found with id={failure_id}")
        return CascadeChain(target_id=failure_id, path=path, siblings=siblings)
