"""
The actual check logic, one record at a time. Plain Python, no AI.

These 3 functions are used in two ways:
  - LOCAL mode: the agents call them directly
  - MCP mode:   the MCP server (mcp_server.py) offers them as tools, and the agents call them through MCP
Same functions = same results in both modes.

A record here is a plain dict (JSON-friendly): missing values are None.
"""
from datetime import date

from .config import ALLOWED_ARMS, HIGH_SEVERITY_GRADE, PLAUSIBLE, REQUIRED_FIELDS, Z_THRESHOLD, ZSCORE_COLUMNS


def missing(v):
    return v is None or v == "" or (isinstance(v, float) and v != v)   # v != v is True only for NaN


def check_record(r: dict) -> dict:
    """Agent 1's tool: is this record complete and possible?"""
    errors, warnings = [], []
    for f in REQUIRED_FIELDS:
        if missing(r.get(f)):
            errors.append(f"Missing {f}")
    if not missing(r.get("arm")) and r["arm"] not in ALLOWED_ARMS:
        errors.append(f"Unknown arm '{r['arm']}'")
    for col, (lo, hi) in PLAUSIBLE.items():
        v = r.get(col)
        if not missing(v) and not lo <= v <= hi:
            errors.append(f"{col}={v} outside possible range {lo}-{hi}")
    if not missing(r.get("visit_date")) and not missing(r.get("consent_date")):
        if date.fromisoformat(r["visit_date"]) < date.fromisoformat(r["consent_date"]):
            errors.append("Visit date is before consent date")
    if r.get("ae_reported") == "Y" and missing(r.get("ae_grade")):
        errors.append("AE reported but grade missing")
    if r.get("ae_reported") == "Y" and missing(r.get("ae_term")):
        warnings.append("AE reported but term empty")
    return {"errors": errors, "warnings": warnings}


def lab_zscores(r: dict, stats: dict) -> dict:
    """Agent 2's tool: z-score of each lab value, against the average for the same arm.
    stats = {"XR-17": {"alt_u_l": [mean, std], ...}, "Placebo": {...}}"""
    z, anomalies = {}, []
    arm_stats = stats.get(r.get("arm"))
    for col in ZSCORE_COLUMNS:
        v = r.get(col)
        if arm_stats is None or missing(v):
            z[col] = None
            continue
        mean, std = arm_stats[col]
        z[col] = round((v - mean) / std, 2)
        if abs(z[col]) >= Z_THRESHOLD:
            anomalies.append(f"{col} z={z[col]:.1f}")
    return {"z": z, "anomalies": anomalies}


def route_record(r: dict, errors: list, anomalies: list) -> dict:
    """Agent 3's tool: where does this record go? First matching rule wins."""
    if errors:
        return {"decision": "QUERY_SITE", "priority": "-",
                "reason": "Data error, sent back to site to fix: " + "; ".join(errors)}
    if r.get("ae_serious") == "Y":
        return {"decision": "HUMAN_REVIEW", "priority": "HIGH", "reason": "Serious adverse event (always needs a human)"}
    grade = r.get("ae_grade")
    if not missing(grade) and grade >= HIGH_SEVERITY_GRADE:
        return {"decision": "HUMAN_REVIEW", "priority": "HIGH", "reason": f"AE grade {int(grade)} (severe)"}
    if anomalies:
        return {"decision": "HUMAN_REVIEW", "priority": "HIGH" if r.get("ae_reported") == "Y" else "MEDIUM",
                "reason": "Unusual lab value: " + "; ".join(anomalies)}
    return {"decision": "AUTO_CLEAR", "priority": "-", "reason": "Valid, no serious or severe AE, no outliers"}
