"""Append-only invariant tests — runtime guard and hash-chain integrity."""
import pytest
import sqlalchemy as sa

from failure_log.exceptions import AppendOnlyViolationError
from failure_log.models import FailureEvent, FailureQuery, FailureRecord, SeverityTier
from failure_log.store import GENESIS_HASH, FailureStore
from failure_log.substrate import FailureSubstrate, _record_hash

_ROOT_CAUSE = "Root cause hypothesis that satisfies the 20-character minimum length floor."


def _make_event(**overrides: object) -> FailureEvent:
    kwargs: dict = dict(
        failure_class="TIMEOUT",
        severity_tier="INFO",
        downstream_impact_envelope="ISOLATED",
        originating_component_id="test-component",
        root_cause_hypothesis=_ROOT_CAUSE,
    )
    kwargs.update(overrides)
    return FailureEvent(**kwargs)


def test_raw_update_raises(substrate: FailureSubstrate) -> None:
    substrate.log_failure(_make_event())
    with pytest.raises(AppendOnlyViolationError):
        with substrate._store._engine.begin() as conn:
            conn.execute(sa.text("UPDATE failures SET severity_tier='CRITICAL' WHERE 1=1"))


def test_raw_delete_raises(substrate: FailureSubstrate) -> None:
    substrate.log_failure(_make_event())
    with pytest.raises(AppendOnlyViolationError):
        with substrate._store._engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM failures WHERE 1=1"))


def test_store_has_no_update_method() -> None:
    assert not hasattr(FailureStore, "update")


def test_store_has_no_delete_method() -> None:
    assert not hasattr(FailureStore, "delete")


def test_first_record_uses_genesis_hash(substrate: FailureSubstrate) -> None:
    substrate.log_failure(_make_event())
    records = substrate.query(FailureQuery())
    assert records[0].parent_hash == GENESIS_HASH


def test_hash_chain_links_sequentially(substrate: FailureSubstrate) -> None:
    for i in range(3):
        substrate.log_failure(_make_event(originating_component_id=f"svc-{i}"))
    r0, r1, r2 = substrate.query(FailureQuery())
    assert r0.parent_hash == GENESIS_HASH
    assert r1.parent_hash == _record_hash(r0)
    assert r2.parent_hash == _record_hash(r1)


def test_tampered_record_breaks_hash_chain(substrate: FailureSubstrate) -> None:
    """Recomputed hash of a tampered record diverges from the next record's parent_hash."""
    substrate.log_failure(_make_event())
    substrate.log_failure(_make_event())
    r0, r1 = substrate.query(FailureQuery())

    # Chain is intact before any tampering
    assert r1.parent_hash == _record_hash(r0)

    # Simulate in-memory tampering of one field
    tampered = FailureRecord(
        failure_id=r0.failure_id,
        sequence=r0.sequence,
        timestamp=r0.timestamp,
        failure_class=r0.failure_class,
        severity_tier=SeverityTier.CRITICAL,   # field changed
        downstream_impact_envelope=r0.downstream_impact_envelope,
        originating_component_id=r0.originating_component_id,
        root_cause_hypothesis=r0.root_cause_hypothesis,
        parent_failure_id=r0.parent_failure_id,
        parent_hash=r0.parent_hash,
    )
    assert _record_hash(tampered) != r1.parent_hash
