"""Shared fixtures for the task_h test suite."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_TASK_H = Path(__file__).parent.parent
for _p in (str(_TASK_H), str(_TASK_H / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from failure_log.failure_classes import FailureClass
from failure_log.models import FailureEvent
from failure_log.substrate import FailureSubstrate

_FC = FailureClass("TIMEOUT")
_ROOT_CAUSE = "Root cause hypothesis that satisfies the 20-character minimum length floor."


def make_event(**overrides: object) -> FailureEvent:
    kwargs: dict = dict(
        failure_class=_FC,
        severity_tier="INFO",
        downstream_impact_envelope="ISOLATED",
        originating_component_id="test-component",
        root_cause_hypothesis=_ROOT_CAUSE,
    )
    kwargs.update(overrides)
    return FailureEvent(**kwargs)


@pytest.fixture
def substrate() -> FailureSubstrate:
    return FailureSubstrate()


@pytest.fixture
def cascade_tree(substrate: FailureSubstrate) -> dict:
    """
    5-node cascade tree (all in-memory, timestamps fixed for determinism):

        root
        ├── child_a
        │   └── grandchild      ← useful target for path tests
        └── child_b
            └── great_grandchild
    """
    ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    root_id = substrate.log_failure(make_event(
        timestamp=ts,
        originating_component_id="root-svc",
    ))
    child_a_id = substrate.log_failure(make_event(
        timestamp=ts.replace(minute=1),
        parent_failure_id=root_id,
        originating_component_id="child-a-svc",
    ))
    child_b_id = substrate.log_failure(make_event(
        timestamp=ts.replace(minute=2),
        parent_failure_id=root_id,
        originating_component_id="child-b-svc",
    ))
    grandchild_id = substrate.log_failure(make_event(
        timestamp=ts.replace(minute=3),
        parent_failure_id=child_a_id,
        originating_component_id="grandchild-svc",
    ))
    great_grandchild_id = substrate.log_failure(make_event(
        timestamp=ts.replace(minute=4),
        parent_failure_id=child_b_id,
        originating_component_id="great-grandchild-svc",
    ))

    return {
        "substrate": substrate,
        "root_id": root_id,
        "child_a_id": child_a_id,
        "child_b_id": child_b_id,
        "grandchild_id": grandchild_id,
        "great_grandchild_id": great_grandchild_id,
    }
