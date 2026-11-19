"""
The 4 agents. Each one does ONE job, then writes its decisions to the audit log.

  Agent 1  validate  : is the record complete and possible?        (tool: validate_records)
  Agent 2  anomaly   : is any lab value very unusual (z-score)?    (tool: lab_zscores)
  Agent 3  route     : auto-clear, human review, or back to site?  (tool: route_records)
  Agent 4  report    : summary numbers + a short written report (LLM if available)

Agents 1 to 3 do not contain the check logic themselves. They call TOOLS:
  - through MCP (mcp_server.py)  when run with --mcp
  - directly (checks.py)         otherwise
Either way the tools are fixed rules, not an LLM, because safety decisions must be
predictable and explainable. Only Agent 4 uses an LLM, and only to WRITE the summary.
"""
import pandas as pd

from .config import Z_THRESHOLD, ZSCORE_COLUMNS

BATCH = 500   # records per tool call (5,000 records = 10 calls per agent)


def as_dicts(df):
    """pandas rows -> plain JSON-friendly dicts (NaN becomes None)."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


async def call_in_batches(tools, name, key, items, **extra):
    out = []
    for i in range(0, len(items), BATCH):
        res = await tools.call(name, {key: items[i:i + BATCH], **extra})
        out += res["results"]
    return out


# ======================================================================= Agent 1
async def validate(df, audit, tools):
    df = df.copy()
    base = df.drop(columns=[c for c in df.columns if c in ("errors", "warnings")])
    results = await call_in_batches(tools, "validate_records", "records", as_dicts(base))
    dup = df.duplicated(keep="first").tolist()          # duplicates need the whole batch, so done here
    errors, warnings = [], []
    for res, is_dup, rid in zip(results, dup, df.record_id):
        e = (["Duplicate record"] if is_dup else []) + res["errors"]
        errors.append(e)
        warnings.append(res["warnings"])
        audit.log(rid, "validate", "FAIL" if e else "PASS", "; ".join(e) if e else "All checks passed",
                  {"warnings": res["warnings"], "tool": "validate_records", "via": tools.mode})
    df["errors"], df["warnings"] = errors, warnings
    return df


# ======================================================================= Agent 2
async def detect_anomalies(df, audit, tools):
    """z = (value - average) / standard deviation, per arm.
    Average and std come only from VALID records, so bad data doesn't distort them."""
    df = df.copy()
    valid = df[df.errors.str.len() == 0]
    stats = {arm: {c: [float(g[c].mean()), float(g[c].std())] for c in ZSCORE_COLUMNS}
             for arm, g in valid.groupby("arm")}
    cols = [c for c in df.columns if c not in ("errors", "warnings")]
    results = await call_in_batches(tools, "lab_zscores", "records", as_dicts(df[cols]), stats=stats)
    for c in ZSCORE_COLUMNS:
        df[f"z_{c}"] = [r["z"][c] for r in results]
    df["anomalies"] = [r["anomalies"] for r in results]
    for (_, row), res in zip(df.iterrows(), results):
        if row["errors"]:
            continue                                     # invalid records are not judged here
        audit.log(row["record_id"], "anomaly", "OUTLIER" if res["anomalies"] else "NORMAL",
                  "; ".join(res["anomalies"]) if res["anomalies"] else f"All |z| < {Z_THRESHOLD}",
                  {**res["z"], "tool": "lab_zscores", "via": tools.mode})
    return df


# ======================================================================= Agent 3
async def route(df, audit, tools):
    df = df.copy()
    cols = [c for c in df.columns if c not in ("errors", "warnings", "anomalies")]
    items = [{"record": r, "errors": e, "anomalies": a}
             for r, e, a in zip(as_dicts(df[cols]), df.errors, df.anomalies)]
    results = await call_in_batches(tools, "route_records", "items", items)
    df["decision"] = [r["decision"] for r in results]
    df["reason"] = [r["reason"] for r in results]
    df["priority"] = [r["priority"] for r in results]
    for rid, r in zip(df.record_id, results):
        audit.log(rid, "route", r["decision"], r["reason"],
                  {"priority": r["priority"], "tool": "route_records", "via": tools.mode})
    return df


# ======================================================================= Agent 4
def site_signals(df):
    """Per site: share of valid XR-17 visits with an ALT outlier. A high share = possible safety signal."""
    v = df[(df.errors.str.len() == 0) & (df.arm == "XR-17")]
    s = v.groupby("site_id").apply(lambda g: (g.z_alt_u_l >= Z_THRESHOLD).mean() * 100,
                                   include_groups=False).rename("pct_alt_outliers").reset_index()
    mean, std = s.pct_alt_outliers.mean(), s.pct_alt_outliers.std()
    s["site_z"] = ((s.pct_alt_outliers - mean) / std).round(2)
    return s


def error_type(message):
    """'age=7 outside possible range 18-90' -> 'Impossible age'  (group similar errors)."""
    if "outside possible range" in message:
        return "Impossible " + message.split("=")[0]
    if message.startswith("Unknown arm"):
        return "Unknown arm"
    return message


def report(df, audit, use_llm=True):
    counts = df.decision.value_counts().to_dict()
    n = len(df)
    signals = site_signals(df)
    top = signals.sort_values("site_z", ascending=False).iloc[0]
    facts = {
        "total_records": n,
        "auto_cleared": counts.get("AUTO_CLEAR", 0),
        "human_review": counts.get("HUMAN_REVIEW", 0),
        "query_site": counts.get("QUERY_SITE", 0),
        "auto_clear_pct": round(100 * counts.get("AUTO_CLEAR", 0) / n, 1),
        "top_error_types": pd.Series([error_type(e) for es in df.errors for e in es])
                             .value_counts().head(6).to_dict(),
        "site_with_most_alt_outliers": f"{top.site_id} ({top.pct_alt_outliers:.1f}% of XR-17 visits, site z={top.site_z})",
    }
    text = None
    if use_llm:
        try:
            from .llm import ask_llm, ollama_up
            if ollama_up():
                text = ask_llm("You write short, factual data review summaries for a clinical trial team. "
                               "Use ONLY the numbers given. 5 bullet points. Plain English. "
                               "'query_site' means records sent BACK to sites to fix data errors.",
                               f"Facts: {facts}")
        except Exception:
            text = None
    if text is None:
        text = (f"- {n} records processed.\n"
                f"- {facts['auto_cleared']} ({facts['auto_clear_pct']}%) auto-cleared.\n"
                f"- {facts['human_review']} sent to human review.\n"
                f"- {facts['query_site']} sent back to sites for data errors.\n"
                f"- Most ALT outliers on XR-17: {facts['site_with_most_alt_outliers']}.")
    audit.log("BATCH", "report", "REPORT_CREATED", "Batch summary written", facts)
    return facts, text, signals
