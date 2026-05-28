"""Query filter tests — each filter individually plus combined and ordering."""
from __future__ import annotations

import pytest

from failure_log.models import FailureEvent, FailureQuery
from failure_log.substrate import FailureSubstrate

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


@pytest.fixture
def multi(substrate: FailureSubstrate) -> FailureSubstrate:
    substrate.log_failure(_make_event(originating_component_id="alpha", failure_class="TIMEOUT",            severity_tier="WARN"))
    substrate.log_failure(_make_event(originating_component_id="beta",  failure_class="CONNECTION_REFUSED", severity_tier="CRITICAL"))
    substrate.log_failure(_make_event(originating_component_id="alpha", failure_class="DATA_CORRUPTION",    severity_tier="CRITICAL"))
    substrate.log_failure(_make_event(originating_component_id="gamma", failure_class="TIMEOUT",            severity_tier="INFO"))
    return substrate


def test_filter_by_component_id(multi: FailureSubstrate) -> None:
    records = multi.query(FailureQuery(originating_component_id="alpha"))
    assert all(r.originating_component_id == "alpha" for r in records)
    assert len(records) == 2


def test_filter_by_severity_tier(multi: FailureSubstrate) -> None:
    records = multi.query(FailureQuery(severity_tier="CRITICAL"))
    assert all(r.severity_tier.value == "CRITICAL" for r in records)
    assert len(records) == 2


def test_filter_by_failure_class(multi: FailureSubstrate) -> None:
    records = multi.query(FailureQuery(failure_class="TIMEOUT"))
    assert all(r.failure_class.value == "TIMEOUT" for r in records)
    assert len(records) == 2


def test_combined_filters_narrow_result(multi: FailureSubstrate) -> None:
    records = multi.query(FailureQuery(originating_component_id="alpha", severity_tier="CRITICAL"))
    assert len(records) == 1
    assert records[0].failure_class.value == "DATA_CORRUPTION"


def test_empty_filter_returns_all(multi: FailureSubstrate) -> None:
    records = multi.query(FailureQuery())
    assert len(records) == 4


def test_results_ordered_by_sequence(multi: FailureSubstrate) -> None:
    records = multi.query(FailureQuery())
    sequences = [r.sequence for r in records]
    assert sequences == sorted(sequences)
