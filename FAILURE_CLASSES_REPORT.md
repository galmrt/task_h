# Failure-Class Enumeration — Report

The substrate recognizes a **closed enumeration of 15 operational failure classes**. The
authoritative source is [`config/failure_classes.json`](config/failure_classes.json); this
report mirrors it. Each entry below gives the class, a one-line definition, and one concrete
example. The `failure_class` field on every `FailureEvent` is validated against this set at
write time — any value outside it is rejected by Pydantic.

| # | Failure class | Definition (short) | Example |
|---|---|---|---|
| 1 | `TIMEOUT` | An operation exceeded its deadline and was aborted; the target may be alive but did not respond in time. | The biomarker-ingest worker waited 30s for the lab-results API and aborted when no response arrived before the deadline. |
| 2 | `CONNECTION_REFUSED` | The transport layer was actively rejected (RST / nothing listening), so no connection could be established. | The protocol-scheduler opened a TCP connection to the cohort-store on port 5432 and got an immediate RST because the DB was down. |
| 3 | `RATE_LIMIT_EXCEEDED` | A healthy dependency deliberately shed load because the caller surpassed its request quota. | The intervention-recommender exceeded 600 req/min on the external genomics API and received HTTP 429. |
| 4 | `AUTHENTICATION_FAILURE` | The caller's identity could not be verified (missing, malformed, or expired credentials) before any permission check. | The data-export service presented a JWT whose signature failed because the signing key had been rotated. |
| 5 | `AUTHORIZATION_DENIED` | An authenticated caller lacked the permission required for the action or resource. | An authenticated analytics component requested raw consent records but its role only grants anonymized aggregates. |
| 6 | `SCHEMA_VALIDATION_ERROR` | A payload failed its declared schema/contract (missing field, wrong type, out-of-range enum) and was rejected at the boundary. | A submitted event carried `severity_tier='FATAL'`, outside the closed five-mode enum, so Pydantic rejected the write. |
| 7 | `DATA_CORRUPTION` | Stored or transmitted data was found internally inconsistent (checksum/hash mismatch, truncation, impossible values). | A record's recomputed `parent_hash` did not match the persisted value, indicating the row was altered after insertion. |
| 8 | `RESOURCE_EXHAUSTION` | A finite local resource (memory, disk, FDs, threads, pool slots) was depleted, so work could not proceed. | The cohort-aggregation job was OOM-killed after loading a 12 GB result set on an 8 GB worker. |
| 9 | `DEPENDENCY_UNAVAILABLE` | A required downstream subsystem was unreachable or not-ready as a whole — the canonical cascade trigger. | The model-serving tier had no healthy instances during a rolling deploy, failing every dependent component. |
| 10 | `CONFIGURATION_ERROR` | Configuration was missing, malformed, contradictory, or pointed at the wrong target; often surfaces at startup or post-deploy. | A component started with an empty `DATABASE_URL` and could not construct its engine, halting initialization. |
| 11 | `SERIALIZATION_ERROR` | Encoding to or decoding from a wire/storage format failed, breaking the data round-trip contract. | A consumer received a JSON body truncated mid-object and raised a decode error while parsing it. |
| 12 | `DEADLOCK` | Concurrent operations formed a circular wait and were permanently blocked until a detector aborted a victim. | Two writers updated overlapping cohort rows in opposite key order; the DB deadlock detector aborted one transaction. |
| 13 | `INTEGRITY_CONSTRAINT_VIOLATION` | A write violated a declared DB constraint (unique, foreign key, not-null, check) and was rejected. | A second record reused an existing `sequence` number, violating the unique constraint on the failures table. |
| 14 | `NETWORK_PARTITION` | Connectivity between live nodes was severed, splitting the cluster and risking loss of quorum/consistency. | A switch failure isolated the secondary datacenter and the replication layer lost quorum. |
| 15 | `MODEL_INFERENCE_FAILURE` | An ML model raised, returned malformed/out-of-distribution output, or breached a confidence floor — a longevity-AI-specific fault. | The biological-age estimator returned NaN for inputs far outside its training distribution; the recommender discarded it. |

## Severity tiers (closed five-mode enum)

`INFO` · `WARN` · `RECOVERABLE` · `DEGRADED` · `CRITICAL`

## Downstream-impact envelope (closed three-mode enum)

`ISOLATED` · `LOCAL_CASCADE` · `CROSS_COMPONENT_CASCADE`

> Note: a failure *class* (what went wrong) is orthogonal to its *severity tier* (how bad) and
> its *impact envelope* (how far it spread). The same `TIMEOUT` class can be `WARN`/`ISOLATED`
> in one occurrence and `CRITICAL`/`CROSS_COMPONENT_CASCADE` in another.