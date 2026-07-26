import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

EPIDEMIC_SOUND_API_KEY = os.getenv('EPIDEMIC_SOUND_API_KEY')
MCP_URL = "https://www.epidemicsound.com/a/mcp-service/mcp"

class EpidemicMCPClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('EPIDEMIC_SOUND_API_KEY')
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream'
        }
        self.req_id = 1

    def _post(self, method: str, params: dict = None) -> dict:
        self.req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.req_id,
            "method": method,
            "params": params or {}
        }
        res = requests.post(MCP_URL, json=payload, headers=self.headers, timeout=20)
        res.raise_for_status()
        text = res.text
        if text.startswith("data: "):
            text = text[6:].strip()
        return json.loads(text)

    def initialize(self):
        """Initializes MCP session with Epidemic Sound Remote MCP Server."""
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "VideoAI-Automator", "version": "1.0.0"}
            }
        }
        res = requests.post(MCP_URL, json=init_payload, headers=self.headers, timeout=10)
        res.raise_for_status()

    def list_tools(self) -> list:
        """Returns all tools supported by Epidemic Sound MCP Server."""
        self.initialize()
        res = self._post("tools/list")
        return res.get("result", {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Executes a tool call on Epidemic Sound MCP Server."""
        self.initialize()
        res = self._post("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
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
