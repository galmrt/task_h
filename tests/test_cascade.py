"""Cascade-traversal tests — correctness of recursive CTE path and sibling logic."""
from __future__ import annotations

import uuid

import pytest

from failure_log.models import FailureEvent
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


def test_cascade_path_is_root_first(cascade_tree: dict) -> None:
    s: FailureSubstrate = cascade_tree["substrate"]
    chain = s.cascade_path(cascade_tree["grandchild_id"])
    path_ids = [r.failure_id for r in chain.path]
    assert path_ids == [
        cascade_tree["root_id"],
        cascade_tree["child_a_id"],
        cascade_tree["grandchild_id"],
    ]
    assert chain.target_id == cascade_tree["grandchild_id"]


def test_cascade_sibling_branches_included(cascade_tree: dict) -> None:
    s: FailureSubstrate = cascade_tree["substrate"]
    chain = s.cascade_path(cascade_tree["grandchild_id"])
    sibling_ids = {r.failure_id for r in chain.siblings}
    assert cascade_tree["child_b_id"] in sibling_ids
    assert cascade_tree["great_grandchild_id"] in sibling_ids


def test_cascade_path_excludes_own_nodes(cascade_tree: dict) -> None:
    s: FailureSubstrate = cascade_tree["substrate"]
    chain = s.cascade_path(cascade_tree["grandchild_id"])
    path_ids = {r.failure_id for r in chain.path}
    sibling_ids = {r.failure_id for r in chain.siblings}
    assert path_ids.isdisjoint(sibling_ids)


def test_cascade_single_node_no_siblings(substrate: FailureSubstrate) -> None:
    fid = substrate.log_failure(_make_event())
    chain = substrate.cascade_path(fid)
    assert len(chain.path) == 1
    assert chain.path[0].failure_id == fid
    assert chain.siblings == []
    assert chain.root is not None and chain.root.failure_id == fid
    assert chain.depth == 1


def test_cascade_root_returns_all_descendants_as_siblings(cascade_tree: dict) -> None:
    s: FailureSubstrate = cascade_tree["substrate"]
    chain = s.cascade_path(cascade_tree["root_id"])
    assert len(chain.path) == 1
    # All 4 non-root nodes appear as siblings
    assert len(chain.siblings) == 4


def test_cascade_depth_6_linear_chain(substrate: FailureSubstrate) -> None:
    parent_id = None
    ids = []
    for i in range(6):
        fid = substrate.log_failure(_make_event(
            parent_failure_id=parent_id,
            originating_component_id=f"svc-{i}",
        ))
        ids.append(fid)
        parent_id = fid

    chain = substrate.cascade_path(ids[-1])
    assert len(chain.path) == 6
    assert [r.failure_id for r in chain.path] == ids


def test_cascade_depth_50_chain_completes(substrate: FailureSubstrate) -> None:
    parent_id = None
    last_id = None
    for i in range(50):
        fid = substrate.log_failure(_make_event(
            parent_failure_id=parent_id,
            originating_component_id=f"svc-deep-{i}",
        ))
        parent_id = fid
        last_id = fid

    chain = substrate.cascade_path(last_id)  # type: ignore[arg-type]
    assert len(chain.path) == 50


def test_cascade_missing_id_raises_key_error(substrate: FailureSubstrate) -> None:
    with pytest.raises(KeyError):
        substrate.cascade_path(uuid.uuid4())
