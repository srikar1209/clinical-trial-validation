"""
How the agents reach the tools. Two options with the SAME interface:  await tools.call(name, args)

  LocalTools: calls the functions in checks.py directly (fast, simple)
  MCPTools:   starts mcp_server.py and calls its tools through the MCP protocol

The agents don't know or care which one they get. That's the point of a standard interface.
"""
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from clinical_trial_validation import checks


class LocalTools:
    mode = "local"

    async def call(self, name, args):
        if name == "validate_records":
            return {"results": [checks.check_record(r) for r in args["records"]]}
        if name == "lab_zscores":
            return {"results": [checks.lab_zscores(r, args["stats"]) for r in args["records"]]}
        if name == "route_records":
            return {"results": [checks.route_record(i["record"], i["errors"], i["anomalies"]) for i in args["items"]]}
        raise ValueError(f"Unknown tool {name}")

    async def close(self):
        pass


class MCPTools:
    mode = "mcp"

    def __init__(self):
        self.stack, self.session, self.n_calls, self.tool_names = AsyncExitStack(), None, 0, []

    async def start(self):
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
        # run the server as a module from the repo root so its package imports resolve
        server = StdioServerParameters(command=sys.executable,
                                       args=["-m", "clinical_trial_validation.mcp_server"],
                                       cwd=str(Path(__file__).resolve().parent.parent))
        read, write = await self.stack.enter_async_context(stdio_client(server))
        self.session = await self.stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()                       # MCP handshake
        listed = await self.session.list_tools()              # ask the server: what tools do you have?
        self.tool_names = [t.name for t in listed.tools]
        return self

    async def call(self, name, args):
        self.n_calls += 1
        result = await self.session.call_tool(name, args)
        if getattr(result, "isError", False):
            raise RuntimeError(f"MCP tool {name} failed: {result.content}")
        if getattr(result, "structuredContent", None):
            return result.structuredContent
        return json.loads(result.content[0].text)             # fallback: result sent as JSON text

    async def close(self):
        await self.stack.aclose()
