"""
Step 2: Run the 4 agents as a LangGraph pipeline.

LangGraph = a library to connect steps (nodes) into a graph.
The graph passes one shared "state" from node to node.

    START -> validate -> detect_anomalies -> route -> report -> END

Agents 1 to 3 call their tools either directly or through MCP:
    python -m trial_validation.pipeline.step2_pipeline          (local tools)
    python -m trial_validation.pipeline.step2_pipeline --mcp    (tools served by mcp_server.py, called over MCP)
Both give the same results. The audit log records which way was used ("via").
"""
import asyncio
import sqlite3
import sys
import time
from typing import Any, TypedDict

import pandas as pd
from langgraph.graph import END, START, StateGraph

from .. import agents
from ..audit_log import AuditLog, verify
from ..config import DB, RECORDS_CSV
from ..tools import LocalTools, MCPTools


class State(TypedDict, total=False):
    records: Any      # the pandas table, updated by each node
    facts: dict
    report_text: str
    signals: Any


def build_graph(audit, tools, use_llm=True):
    async def validate_node(s):
        return {"records": await agents.validate(s["records"], audit, tools)}

    async def anomaly_node(s):
        return {"records": await agents.detect_anomalies(s["records"], audit, tools)}

    async def route_node(s):
        return {"records": await agents.route(s["records"], audit, tools)}

    def report_node(s):
        facts, text, signals = agents.report(s["records"], audit, use_llm)
        return {"facts": facts, "report_text": text, "signals": signals}

    g = StateGraph(State)
    g.add_node("validate", validate_node)
    g.add_node("detect_anomalies", anomaly_node)
    g.add_node("route", route_node)
    g.add_node("report", report_node)
    g.add_edge(START, "validate")
    g.add_edge("validate", "detect_anomalies")
    g.add_edge("detect_anomalies", "route")
    g.add_edge("route", "report")
    g.add_edge("report", END)
    return g.compile()


def save_results(df, signals):
    out = df.copy()
    for c in ["errors", "warnings", "anomalies"]:
        out[c] = out[c].apply("; ".join)
    con = sqlite3.connect(DB)
    out.to_sql("records", con, if_exists="replace", index=False)
    signals.to_sql("site_signals", con, if_exists="replace", index=False)
    con.execute("""CREATE TABLE IF NOT EXISTS reviews (
        record_id TEXT, reviewer TEXT, decision TEXT, comment TEXT, ts_utc TEXT)""")
    con.commit()
    con.close()


async def run_async(use_mcp=False, use_llm=True):
    if DB.exists():
        DB.unlink()          # fresh run (in real life the audit log is NEVER deleted)
    audit = AuditLog()
    tools = await MCPTools().start() if use_mcp else LocalTools()
    t0 = time.time()
    try:
        graph = build_graph(audit, tools, use_llm)
        final = await graph.ainvoke({"records": pd.read_csv(RECORDS_CSV)})
    finally:
        await tools.close()
    audit.flush()
    save_results(final["records"], final["signals"])

    f = final["facts"]
    print(f"Tools via: {tools.mode.upper()}"
          + (f"  (server tools: {', '.join(tools.tool_names)}; {tools.n_calls} MCP calls)" if use_mcp else ""))
    print(f"Records: {f['total_records']}   ({time.time() - t0:.1f}s)")
    print(f"  AUTO_CLEAR    {f['auto_cleared']:5d}  ({f['auto_clear_pct']}%)")
    print(f"  HUMAN_REVIEW  {f['human_review']:5d}")
    print(f"  QUERY_SITE    {f['query_site']:5d}")
    print(f"Top errors: {f['top_error_types']}")
    print(f"Signal: {f['site_with_most_alt_outliers']}")
    ok, n, bad = verify()
    print(f"Audit log: {n} entries, chain {'OK' if ok else 'BROKEN at seq ' + str(bad)}")
    print("\nReport:\n" + final["report_text"])
    return final


def run(use_mcp=False, use_llm=True):
    return asyncio.run(run_async(use_mcp, use_llm))


if __name__ == "__main__":
    run(use_mcp="--mcp" in sys.argv)
