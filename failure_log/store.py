"""Append-only store — the *only* code allowed to touch the failures table.

Critical invariant: this module exposes **no update() and no delete() method**. Their
absence is the static guarantee (the CI check in scripts/ verifies no such primitive is
added by a future PR). At runtime, a guard on the engine additionally blocks any raw
UPDATE/DELETE statement, so even hand-written SQL cannot mutate a stored failure.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.engine import Engine

from failure_log.exceptions import AppendOnlyViolationError
from failure_log.models import (
    AggregationBucket,
    DownstreamImpactEnvelope,
    FailureClass,
    FailureQuery,
    FailureRecord,
    SeverityTier,
)

# Every first failure in a fresh substrate uses this as its parent_hash.
GENESIS_HASH: str = hashlib.sha256(b"").hexdigest()

# The single SQLite table backing the substrate. Maps cleanly to Postgres.
FAILURES_TABLE = "failures"

_metadata = sa.MetaData()

_failures = sa.Table(
    FAILURES_TABLE,
    _metadata,
    Column("failure_id", String(36), primary_key=True),
    Column("sequence", Integer, nullable=False, unique=True),
    Column("timestamp", DateTime, nullable=False, index=True),
    Column("failure_class", String(64), nullable=False, index=True),
    Column("severity_tier", String(32), nullable=False, index=True),
    Column("downstream_impact_envelope", String(32), nullable=False, index=True),
    Column("originating_component_id", String(256), nullable=False, index=True),
    Column("root_cause_hypothesis", Text, nullable=False),
    Column("parent_failure_id", String(36), nullable=True, index=True),
    Column("parent_hash", String(64), nullable=False),
)

# Dimensions aggregate() may group over — the closed set from the spec.
_GROUPABLE_COLUMNS: dict[str, sa.Column[Any]] = {
    "originating_component_id": _failures.c.originating_component_id,
    "failure_class": _failures.c.failure_class,
    "severity_tier": _failures.c.severity_tier,
    "downstream_impact_envelope": _failures.c.downstream_impact_envelope,
}

# Append-only invariant: this module exposes no update() or delete() methods.
# Absence of those methods is the static guarantee. The CI check greps the AST for them.


def make_engine(url: str = "sqlite:///:memory:") -> Engine:
    """Create a SQLAlchemy engine, attach the append-only guard, and create tables."""
    engine = sa.create_engine(url)
    _attach_append_only_guard(engine)
    _metadata.create_all(engine)
    return engine


def _attach_append_only_guard(engine: Engine) -> None:
    @sa.event.listens_for(engine, "before_cursor_execute")
    def _block(  # type: ignore[no-untyped-def]
        conn, cursor, statement, parameters, context, executemany
    ):
        if statement.lstrip().upper().startswith(("UPDATE", "DELETE")):
            raise AppendOnlyViolationError(
                f"Append-only violation: mutation blocked — {statement[:80]!r}"
            )


class FailureStore:
    """Append-only data access for failures. No update/delete — by construction."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def insert(self, record: FailureRecord) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                _failures.insert().values(
                    failure_id=str(record.failure_id),
                    sequence=record.sequence,
                    timestamp=record.timestamp.replace(tzinfo=None),
                    failure_class=record.failure_class.value,
                    severity_tier=record.severity_tier.value,
                    downstream_impact_envelope=record.downstream_impact_envelope.value,
                    originating_component_id=record.originating_component_id,
                    root_cause_hypothesis=record.root_cause_hypothesis,
                    parent_failure_id=(
                        str(record.parent_failure_id)
                        if record.parent_failure_id is not None
                        else None
                    ),
                    parent_hash=record.parent_hash,
                )
            )

    def get_latest(self) -> FailureRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(_failures).order_by(_failures.c.sequence.desc()).limit(1)
            ).fetchone()
        return _row_to_record(row._mapping) if row else None

    def get_by_id(self, failure_id: UUID) -> FailureRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(_failures).where(_failures.c.failure_id == str(failure_id))
            ).fetchone()
        return _row_to_record(row._mapping) if row else None

    def query(self, filters: FailureQuery) -> list[FailureRecord]:
        c = _failures.c
        stmt = sa.select(_failures)
        if filters.originating_component_id is not None:
            stmt = stmt.where(c.originating_component_id == filters.originating_component_id)
        if filters.failure_class is not None:
            stmt = stmt.where(c.failure_class == filters.failure_class.value)
        if filters.severity_tier is not None:
            stmt = stmt.where(c.severity_tier == filters.severity_tier.value)
        if filters.downstream_impact_envelope is not None:
            stmt = stmt.where(
                c.downstream_impact_envelope == filters.downstream_impact_envelope.value
            )
        if filters.parent_failure_id is not None:
            stmt = stmt.where(c.parent_failure_id == str(filters.parent_failure_id))
        if filters.start_time is not None:
            stmt = stmt.where(c.timestamp >= filters.start_time.replace(tzinfo=None))
        if filters.end_time is not None:
            stmt = stmt.where(c.timestamp <= filters.end_time.replace(tzinfo=None))
        with self._engine.connect() as conn:
            rows = conn.execute(stmt.order_by(c.sequence)).fetchall()
        return [_row_to_record(r._mapping) for r in rows]

    def aggregate(
        self, group_by: list[str], start: datetime, end: datetime
    ) -> list[AggregationBucket]:
        """Group over the requested dimensions plus a per-day time bucket; count rows."""
        unknown = [g for g in group_by if g not in _GROUPABLE_COLUMNS]
        if unknown:
            raise ValueError(
                f"Cannot group by {unknown}; allowed: {sorted(_GROUPABLE_COLUMNS)}"
            )
        dim_cols = [_GROUPABLE_COLUMNS[g].label(g) for g in group_by]
        date_bucket = sa.func.date(_failures.c.timestamp).label("date_bucket")
        count_col = sa.func.count().label("cnt")
        stmt = (
            sa.select(*dim_cols, date_bucket, count_col)
            .where(
                _failures.c.timestamp >= start.replace(tzinfo=None),
                _failures.c.timestamp <= end.replace(tzinfo=None),
            )
            .group_by(*dim_cols, date_bucket)
            .order_by(date_bucket, *dim_cols)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [
            AggregationBucket(
                keys={g: str(r._mapping[g]) for g in group_by},
                date_bucket=str(r._mapping["date_bucket"]),
                count=int(r._mapping["cnt"]),
            )
            for r in rows
        ]

    def cascade_path(
        self, failure_id: UUID, max_depth: int = 50
    ) -> tuple[list[FailureRecord], list[FailureRecord]]:
        """Return (path, siblings) for the cascade containing ``failure_id``.

        ``path`` is the ancestor chain ordered root-first through to the target, walked
        upward via a recursive CTE (correct for chains up to ``max_depth``). ``siblings``
        are the other nodes in the same cascade tree (everything reachable downward from
        the root that is not on the path). An empty path means the id was not found.
        """
        path = self._ancestors(failure_id, max_depth)
        if not path:
            return [], []
        tree = self._descendants(path[0].failure_id, max_depth)
        path_ids = {r.failure_id for r in path}
        siblings = [r for r in tree if r.failure_id not in path_ids]
        return path, siblings

    def _ancestors(self, failure_id: UUID, max_depth: int) -> list[FailureRecord]:
        sql = sa.text(
            """
            WITH RECURSIVE ancestors(fid, depth) AS (
                SELECT failure_id, 0 FROM failures WHERE failure_id = :fid
                UNION ALL
                SELECT f.parent_failure_id, a.depth + 1
                FROM failures f
                JOIN ancestors a ON f.failure_id = a.fid
                WHERE f.parent_failure_id IS NOT NULL AND a.depth < :max_depth
            )
            SELECT f.* FROM failures f
            JOIN ancestors a ON f.failure_id = a.fid
            ORDER BY a.depth DESC
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(
                sql, {"fid": str(failure_id), "max_depth": max_depth}
            ).fetchall()
        return [_row_to_record(r._mapping) for r in rows]

    def _descendants(self, root_id: UUID, max_depth: int) -> list[FailureRecord]:
        sql = sa.text(
            """
            WITH RECURSIVE descendants(fid, depth) AS (
                SELECT failure_id, 0 FROM failures WHERE failure_id = :root
                UNION ALL
                SELECT f.failure_id, d.depth + 1
                FROM failures f
                JOIN descendants d ON f.parent_failure_id = d.fid
                WHERE d.depth < :max_depth
            )
            SELECT f.* FROM failures f
            JOIN descendants d ON f.failure_id = d.fid
            ORDER BY f.sequence
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(
                sql, {"root": str(root_id), "max_depth": max_depth}
            ).fetchall()
        return [_row_to_record(r._mapping) for r in rows]


def _row_to_record(m: Mapping[str, Any]) -> FailureRecord:
    ts = m["timestamp"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    pfid = m["parent_failure_id"]
    return FailureRecord(
        failure_id=UUID(m["failure_id"]),
        sequence=m["sequence"],
        timestamp=ts.replace(tzinfo=timezone.utc),
        failure_class=FailureClass(m["failure_class"]),
        severity_tier=SeverityTier(m["severity_tier"]),
        downstream_impact_envelope=DownstreamImpactEnvelope(m["downstream_impact_envelope"]),
        originating_component_id=m["originating_component_id"],
        root_cause_hypothesis=m["root_cause_hypothesis"],
        parent_failure_id=UUID(pfid) if pfid else None,
        parent_hash=m["parent_hash"],
    )
