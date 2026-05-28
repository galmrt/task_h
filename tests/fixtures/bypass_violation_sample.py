# Intentional bypass violation — for static-analysis tests ONLY.
# This file must never be imported in production code.
# scripts/check_static_analysis.py is expected to flag the string below.

VIOLATION_SQL = (
    "INSERT INTO failures (failure_id, sequence, failure_class, severity_tier, "
    "downstream_impact_envelope, originating_component_id, root_cause_hypothesis, "
    "parent_hash) VALUES ('aaaa-0000', 0, 'TIMEOUT', 'WARN', 'ISOLATED', 'evil', "
    "'bypassing the substrate', 'deadbeef')"
)
