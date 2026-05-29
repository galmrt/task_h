"""Aggregation tests — group-by correctness, time bucketing, and error paths."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from failure_log.models import FailureEvent
from failure_log.substrate import FailureSubstrate

_ROOT_CAUSE = "Root cause hypothesis that satisfies the 20-character minimum length floor."
_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
_END = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


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
def loaded(substrate: FailureSubstrate) -> FailureSubstrate:
    """6 failures spread across two components, two classes, two severity tiers, two days."""
    day1 = datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)
    day2 = datetime(2024, 6, 2, 10, 0, tzinfo=timezone.utc)

    substrate.log_failure(_make_event(timestamp=day1, originating_component_id="alpha", failure_class="TIMEOUT", severity_tier="WARN"))
    substrate.log_failure(_make_event(timestamp=day1, originating_component_id="alpha", failure_class="TIMEOUT", severity_tier="WARN"))
    substrate.log_failure(_make_event(timestamp=day1, originating_component_id="beta",  failure_class="CONNECTION_REFUSED", severity_tier="CRITICAL"))
    substrate.log_failure(_make_event(timestamp=day2, originating_component_id="alpha", failure_class="TIMEOUT", severity_tier="WARN"))
    substrate.log_failure(_make_event(timestamp=day2, originating_component_id="beta",  failure_class="CONNECTION_REFUSED", severity_tier="CRITICAL"))
    substrate.log_failure(_make_event(timestamp=day2, originating_component_id="gamma", failure_class="TIMEOUT", severity_tier="INFO"))

    return substrate


def test_aggregate_single_dimension(loaded: FailureSubstrate) -> None:
    result = loaded.aggregate((_START, _END), group_by=["originating_component_id"])
    assert result.group_by == ["originating_component_id"]
    components = {b.keys["originating_component_id"] for b in result.buckets}
    assert {"alpha", "beta", "gamma"} == components


def test_aggregate_multi_dimension(loaded: FailureSubstrate) -> None:
    result = loaded.aggregate((_START, _END), group_by=["originating_component_id", "failure_class"])
    assert result.group_by == ["originating_component_id", "failure_class"]
    for bucket in result.buckets:
        assert "originating_component_id" in bucket.keys
        assert "failure_class" in bucket.keys
    groups = {(b.keys["originating_component_id"], b.keys["failure_class"]) for b in result.buckets}
    assert ("alpha", "TIMEOUT") in groups
    assert ("beta", "CONNECTION_REFUSED") in groups


def test_aggregate_time_bucket_separates_days(loaded: FailureSubstrate) -> None:
    result = loaded.aggregate((_START, _END), group_by=["originating_component_id"])
    date_buckets = {b.date_bucket for b in result.buckets}
    assert "2024-06-01" in date_buckets
    assert "2024-06-02" in date_buckets


def test_aggregate_counts_match_known_fixture(loaded: FailureSubstrate) -> None:
    result = loaded.aggregate((_START, _END), group_by=["originating_component_id"])
    # alpha: 2 on day1 + 1 on day2 = 3 total across two date buckets
    alpha_total = sum(b.count for b in result.buckets if b.keys["originating_component_id"] == "alpha")
    assert alpha_total == 3


def test_aggregate_empty_time_window_returns_no_buckets(loaded: FailureSubstrate) -> None:
    far_future_start = datetime(2099, 1, 1, tzinfo=timezone.utc)
    far_future_end = datetime(2099, 12, 31, tzinfo=timezone.utc)
    result = loaded.aggregate((far_future_start, far_future_end), group_by=["severity_tier"])
    assert result.buckets == []


def test_aggregate_unknown_dimension_raises(substrate: FailureSubstrate) -> None:
    with pytest.raises(ValueError, match="Cannot group by"):
        substrate.aggregate((_START, _END), group_by=["nonexistent_column"])


def test_aggregate_empty_group_by_raises(substrate: FailureSubstrate) -> None:
    with pytest.raises(ValueError):
        substrate.aggregate((_START, _END), group_by=[])
