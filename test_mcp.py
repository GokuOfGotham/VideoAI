"""Connectivity check for the Epidemic Sound MCP endpoint (no downloads, no charges)."""
from epidemic_mcp_client import EpidemicMCPClient

try:
    client = EpidemicMCPClient()
    tools = client.list_tools()
    print("MCP session:", "ok" if client.session_id else "missing session id")
    print(f"{len(tools)} tools:")
    for tool in tools:
        print(" -", tool.get("name"))
except Exception as exc:  # network / auth problems are the point of this check
    print("MCP Tools List failed:", exc)
