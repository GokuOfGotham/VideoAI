import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
key = os.getenv('EPIDEMIC_SOUND_API_KEY')

mcp_url = "https://www.epidemicsound.com/a/mcp-service/mcp"
headers = {
    'Authorization': f'Bearer {key}',
    'Content-Type': 'application/json',
    'Accept': 'application/json, text/event-stream'
}

payload = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
}

try:
    res = requests.post(mcp_url, json=payload, headers=headers, timeout=10)
    print("MCP Tools List Status:", res.status_code)
    text = res.text
    if text.startswith("data: "):
        text = text[6:].strip()
    data = json.loads(text)
    tools = data.get("result", {}).get("tools", [])
    print(f"\n[+] SUCCESS! Epidemic Sound MCP Server returned {len(tools)} Official Tools:\n")
    for t in tools:
        print(f"  - Tool: {t.get('name')}")
        print(f"    Description: {t.get('description')}")
except Exception as e:
    print("MCP Tools List failed:", e, res.text)
