"""Schema-rejection tests — every invariant enforced by Pydantic at construction time."""
import pytest
from pydantic import ValidationError

from failure_log.models import FailureEvent

_ROOT_CAUSE = "Root cause hypothesis that satisfies the 20-character minimum length floor."
_VALID: dict = dict(
    failure_class="TIMEOUT",
    severity_tier="INFO",
    downstream_impact_envelope="ISOLATED",
    originating_component_id="test-component",
    root_cause_hypothesis=_ROOT_CAUSE,
)


def test_unknown_failure_class():
    with pytest.raises(ValidationError):
        FailureEvent(**{**_VALID, "failure_class": "NONEXISTENT_CLASS"})


def test_invalid_severity_tier():
    with pytest.raises(ValidationError):
        FailureEvent(**{**_VALID, "severity_tier": "FATAL"})


def test_invalid_downstream_impact_envelope():
    with pytest.raises(ValidationError):
        FailureEvent(**{**_VALID, "downstream_impact_envelope": "TOTAL_OUTAGE"})


def test_root_cause_below_floor():
    with pytest.raises(ValidationError):
        FailureEvent(**{**_VALID, "root_cause_hypothesis": "Too short."})


def test_root_cause_above_ceiling():
    with pytest.raises(ValidationError):
        FailureEvent(**{**_VALID, "root_cause_hypothesis": "x" * 2001})


def test_root_cause_at_floor_is_accepted():
    event = FailureEvent(**{**_VALID, "root_cause_hypothesis": "a" * 20})
    assert event.root_cause_hypothesis == "a" * 20


def test_root_cause_at_ceiling_is_accepted():
    event = FailureEvent(**{**_VALID, "root_cause_hypothesis": "a" * 2000})
    assert len(event.root_cause_hypothesis) == 2000


def test_empty_originating_component_id():
    with pytest.raises(ValidationError):
        FailureEvent(**{**_VALID, "originating_component_id": ""})


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        FailureEvent(**{**_VALID, "unexpected_field": "value"})


def test_bad_parent_failure_id_type():
    with pytest.raises(ValidationError):
        FailureEvent(**{**_VALID, "parent_failure_id": "not-a-uuid"})
