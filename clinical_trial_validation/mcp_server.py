"""
MCP server: offers the check functions as TOOLS that any MCP client can call.

MCP (Model Context Protocol) = a standard way for AI agents to use tools that live in a
separate program. Like a USB port: any client that "speaks MCP" can plug in and use these tools.

This server offers 3 tools. Each takes a BATCH of records (up to 500), so 5,000 records
need only 10 calls per tool instead of 5,000 (much faster over stdio).

It talks over stdio (standard input/output): the client starts this file as a small
background process and sends messages through its input/output. Nothing goes over the network.

Run by itself (to test):   python -m clinical_trial_validation.mcp_server      (it waits for a client; Ctrl+C to stop)
Normally it is started automatically by:  python -m clinical_trial_validation.pipeline --mcp
"""
from mcp.server.mcpserver import MCPServer

from clinical_trial_validation import checks

server = MCPServer(name="trial-checks",
                   instructions="Deterministic data checks for clinical trial records. No AI inside.")


@server.tool(description="Check records are complete and possible. Returns errors and warnings per record.")
def validate_records(records: list[dict]) -> dict:
    return {"results": [checks.check_record(r) for r in records]}


@server.tool(description="Z-score lab values per record against per-arm mean and std. Flags |z| >= 3.")
def lab_zscores(records: list[dict], stats: dict) -> dict:
    return {"results": [checks.lab_zscores(r, stats) for r in records]}


@server.tool(description="Decide AUTO_CLEAR, HUMAN_REVIEW, or QUERY_SITE per record, with the reason.")
def route_records(items: list[dict]) -> dict:
    """items = [{"record": {...}, "errors": [...], "anomalies": [...]}, ...]"""
    return {"results": [checks.route_record(i["record"], i["errors"], i["anomalies"]) for i in items]}


if __name__ == "__main__":
    server.run("stdio")
