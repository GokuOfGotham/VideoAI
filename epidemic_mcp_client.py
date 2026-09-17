"""Minimal Epidemic Sound MCP client (requests-based) for scripts and quick checks.

The full adapter used by renders lives in ``videoai_graphics.epidemic``; this
standalone client exists for ad-hoc searches and connectivity tests. The
Streamable HTTP transport needs a session: ``initialize`` returns an
``Mcp-Session-Id`` header that every later request must carry, followed by a
``notifications/initialized`` notification. Without both, the server answers
422 "expect initialize request".
"""

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

EPIDEMIC_SOUND_API_KEY = os.getenv('EPIDEMIC_SOUND_API_KEY')
MCP_URL = "https://www.epidemicsound.com/a/mcp-service/mcp"
PROTOCOL = "2024-11-05"


class EpidemicMCPClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('EPIDEMIC_SOUND_API_KEY')
        if not self.api_key:
            raise RuntimeError("EPIDEMIC_SOUND_API_KEY is not set (environment or .env).")
        self.session_id = None
        self.protocol = PROTOCOL
        self.req_id = 0

    def _headers(self) -> dict:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
            'MCP-Protocol-Version': self.protocol,
        }
        if self.session_id:
            headers['Mcp-Session-Id'] = self.session_id
        return headers

    def _post(self, method: str, params: dict = None, *, notification: bool = False) -> dict:
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notification:
            self.req_id += 1
            payload["id"] = self.req_id
        res = requests.post(MCP_URL, json=payload, headers=self._headers(), timeout=30)
        res.raise_for_status()
        session = res.headers.get("Mcp-Session-Id")
        if session:
            self.session_id = session
        if notification:
            return {}
        text = res.text
        if "text/event-stream" in res.headers.get("Content-Type", ""):
            # SSE framing: the first data line is an empty keep-alive; take the JSON one.
            text = next((line[5:].strip() for line in text.splitlines()
                         if line.startswith("data:") and line[5:].strip()), "")
        data = json.loads(text)
        if "error" in data:
            raise RuntimeError(f"MCP {method} failed: {data['error']}")
        return data

    def initialize(self):
        """Opens the MCP session (idempotent)."""
        if self.session_id:
            return
        res = self._post("initialize", {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "VideoAI-Automator", "version": "1.1.0"},
        })
        self.protocol = res.get("result", {}).get("protocolVersion", PROTOCOL)
        self._post("notifications/initialized", notification=True)

    def list_tools(self) -> list:
        """Returns all tools supported by Epidemic Sound MCP Server."""
        self.initialize()
        res = self._post("tools/list", {})
        return res.get("result", {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Executes a tool call on Epidemic Sound MCP Server."""
        self.initialize()
        res = self._post("tools/call", {"name": tool_name, "arguments": arguments})
        return res.get("result", {})


if __name__ == '__main__':
    print("--- EPIDEMIC SOUND OFFICIAL MCP CLIENT TEST ---")
    client = EpidemicMCPClient()
    try:
        tools = client.list_tools()
        print(f"[+] Connected to Official Epidemic Sound MCP Server!")
        print(f"[+] Total Available MCP Tools: {len(tools)}")
        for t in tools:
            print(f"  • {t.get('name')}: {t.get('description')}")
    except Exception as e:
        print(f"[!] MCP Client Error: {e}")
