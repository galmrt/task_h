# Task H — Structured Failure-Logging Substrate

A Python package that converts every operational failure into a typed, schema-conformant, hash-chained record. Downstream components can query and aggregate records, and perform cross-component cascade-impact analysis.

## Features

- **Schema enforcement at write time** — Pydantic rejects any malformed `FailureEvent` before it reaches the database; bypass is statically impossible.
- **Append-only store** — no `UPDATE` or `DELETE` primitive exists at the DAO layer. A SQLAlchemy engine event blocks raw mutations at runtime. A CI script verifies the DAO via AST at every PR.
- **Hash chain** — each record's `parent_hash` is SHA-256 of the previous record's full field set, enabling tamper detection.
- **Cascade traversal** — recursive CTE walks `parent_failure_id` upward to the root and collects sibling branches; correct on chains up to depth 50.
- **Flexible aggregation** — `group_by` over any combination of `{originating_component_id, failure_class, severity_tier, downstream_impact_envelope}` with per-day time bucketing.
- **Config-driven failure classes** — 15 named classes in `config/failure_classes.json`; adding a new class requires only a JSON edit.

## Quickstart

```bash
pip install -e ".[dev]"

python3 -c "
from failure_log.substrate import FailureSubstrate
from failure_log.models import FailureEvent, FailureQuery

s = FailureSubstrate()
fid = s.log_failure(FailureEvent(
    failure_class='TIMEOUT',
    severity_tier='WARN',
    downstream_impact_envelope='LOCAL_CASCADE',
    originating_component_id='biomarker-ingest',
    root_cause_hypothesis='Lab API did not respond within the 30s deadline.',
))
print(s.query(FailureQuery(originating_component_id='biomarker-ingest')))
"
```

## Public Interface

| Method | Signature | Description |
|---|---|---|
| `log_failure` | `(FailureEvent) -> FailureId` | Validate, hash-chain, and persist a failure |
| `query` | `(FailureQuery) -> list[FailureRecord]` | Filter stored failures, ordered by sequence |
| `aggregate` | `(time_window, group_by) -> FailureAggregation` | Count failures grouped by dimensions + day |
| `cascade_path` | `(FailureId) -> CascadeChain` | Ancestor path (root-first) + sibling branches |

## Schema

`FailureEvent` fields — all validated by Pydantic at construction:

| Field | Type | Constraint |
|---|---|---|
| `failure_class` | `FailureClass` (str enum) | Closed set of 15 classes from `config/failure_classes.json` |
| `severity_tier` | `SeverityTier` | `INFO \| WARN \| RECOVERABLE \| DEGRADED \| CRITICAL` |
| `downstream_impact_envelope` | `DownstreamImpactEnvelope` | `ISOLATED \| LOCAL_CASCADE \| CROSS_COMPONENT_CASCADE` |
| `originating_component_id` | `str` | 1–256 characters |
| `root_cause_hypothesis` | `str` | 20–2000 characters |
| `parent_failure_id` | `UUID \| None` | Points to upstream cascade source |
| `timestamp` | `datetime \| None` | Substrate-stamped if omitted |

`FailureRecord` extends `FailureEvent` with substrate-computed fields: `failure_id` (uuid4), `sequence` (monotonic), `parent_hash` (SHA-256 chain).

## Architecture

```
config/failure_classes.json      ← single source of truth for the failure_class enum
failure_log/failure_classes.py   ← loads JSON → FailureClass enum (no logic)
failure_log/models.py            ← Pydantic types only; no DB or hashing
failure_log/store.py             ← only code allowed to touch the DB
failure_log/substrate.py         ← public interface; orchestrates store + hashing
failure_log/exceptions.py        ← exception hierarchy
scripts/check_static_analysis.py ← CI check; must never import failure_log
```

Two independent "parent" concepts:

| Field | Purpose |
|---|---|
| `parent_hash` | Tamper-evidence — linear SHA-256 chain across all records in insertion order |
| `parent_failure_id` | Causality — tree/DAG driving `cascade_path` |

## Running Tests

```bash
# All tests
pytest tests/

# Single file
pytest tests/test_cascade.py

# Single test
pytest tests/test_cascade.py::test_cascade_depth_50_chain_completes
```

45 tests across 6 files:

| File | Coverage |
|---|---|
| `test_schema_rejection.py` | Unknown class, bad severity/envelope, root_cause floor/ceiling, empty component, extra field, bad UUID type |
| `test_append_only.py` | UPDATE/DELETE raise `AppendOnlyViolationError`, no update/delete method on DAO, genesis hash, hash chain links, tamper detection |
| `test_static_analysis.py` | Clean package passes both checks, planted bypass fixture fires, monkeypatched store with `update`/`delete` triggers check |
| `test_cascade.py` | Root-first ordering, sibling inclusion, path/sibling disjoint, single node, root as target, depth-6 chain, depth-50 chain, missing ID raises `KeyError` |
| `test_aggregation.py` | Single dim, multi-dim, day separation, count correctness, empty window, unknown dim raises `ValueError`, empty `group_by` raises |
| `test_query.py` | Each filter individually, combined filters, empty filter returns all, sequence ordering |

## Static-Analysis CI Check

```bash
# Must exit 0 on a clean repo
python3 scripts/check_static_analysis.py

# Must exit 1 — demonstrates the planted bypass fixture is detected
python3 scripts/check_static_analysis.py tests/fixtures/bypass_violation_sample.py
```

Two checks:

1. **Append-only** — `failure_log/store.py` must contain no method named `update` or `delete`.
2. **Bypass** — no `.py` file in `failure_log/` may contain a raw SQL string literal that inserts directly into the `failures` table; all writes must flow through `log_failure → FailureStore.insert`.

## Failure Classes

See [FAILURE_CLASSES_REPORT.md](FAILURE_CLASSES_REPORT.md) for the full list of 15 classes with definitions and one example each. Classes at a glance:

`TIMEOUT` · `CONNECTION_REFUSED` · `RATE_LIMIT_EXCEEDED` · `AUTHENTICATION_FAILURE` · `AUTHORIZATION_DENIED` · `SCHEMA_VALIDATION_ERROR` · `DATA_CORRUPTION` · `RESOURCE_EXHAUSTION` · `DEPENDENCY_UNAVAILABLE` · `CONFIGURATION_ERROR` · `SERIALIZATION_ERROR` · `DEADLOCK` · `INTEGRITY_CONSTRAINT_VIOLATION` · `NETWORK_PARTITION` · `MODEL_INFERENCE_FAILURE`

## Dependencies

| Package | Role |
|---|---|
| `pydantic >= 2.0` | Schema validation and model types |
| `sqlalchemy >= 2.0` | Append-only DAO and recursive CTE queries |
| `hashlib` (stdlib) | SHA-256 hash chain |
