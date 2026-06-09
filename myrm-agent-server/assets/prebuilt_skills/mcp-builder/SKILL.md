---
name: mcp-builder
description: >-
  Build production-quality MCP servers that integrate external APIs and services.
  Covers research, implementation (Python FastMCP / TypeScript), testing,
  security validation, and Myrm registration. Use when users want to connect
  custom tools, internal APIs, or third-party services to their agent.
version: 1.0.0
category: development
tags:
  - mcp
  - integration
  - api
  - server
  - development
  - tools
allowed-tools: bash_code_execute_tool file_read_tool grep_tool web_search_tool
contract:
  steps:
    - "Phase 1: Research — understand the target API, plan tools, choose transport"
    - "Phase 2: Implementation — build the MCP server with proper typing, error handling, and annotations"
    - "Phase 3: Verify — confirm server starts, tools are listed, security scan passes"
    - "Phase 4: Register — add to Myrm config, test tool invocations in conversation"
  potential_traps:
    - description: "Building many tools at once without incremental testing"
      mitigation: "Start with 1-2 core tools, verify they work, then add more"
      severity: medium
    - description: "Missing tool annotations — all tools default to requiring approval"
      mitigation: "Always set readOnlyHint:true on read operations so they auto-approve"
      severity: high
    - description: "Ignoring error handling — agent receives raw exceptions"
      mitigation: "Catch all exceptions and return actionable error messages"
      severity: medium
  verification_steps:
    - step_id: server_starts
      description: "MCP server starts and responds to initialize handshake"
      validation_method: "Run verification script that connects and lists tools"
      is_required: true
    - step_id: annotations_set
      description: "All tools have correct readOnlyHint/destructiveHint annotations"
      validation_method: "Inspect tool metadata, verify read-only operations are marked"
      is_required: true
    - step_id: myrm_registered
      description: "Server is registered and accessible in conversation"
      validation_method: "Call a tool through the agent and verify response"
      is_required: true
  success_criteria: "MCP server is registered, tools work in conversation, read-only tools auto-approve"
  estimated_duration_seconds: 2400
---

# MCP Server Builder

Build MCP servers that connect external services to the agent. Quality is measured by: tools work reliably, annotations enable smooth approval flow, errors are actionable.

---

## Phase 1: Research & Planning

### 1.1 Understand the Target API

Use `web_search_tool` to find the service's API documentation. Identify:

- Authentication method (API key, OAuth, bearer token)
- Base URL and versioning
- Rate limits and pagination patterns
- Key endpoints the user needs

### 1.2 Plan Tools

List tools to implement, prioritizing the user's stated needs:

| Tool Name | Description | Read-Only? | Destructive? |
|-----------|-------------|:----------:|:------------:|
| `list_items` | List items with filtering | Yes | No |
| `get_item` | Get single item by ID | Yes | No |
| `create_item` | Create new item | No | No |
| `delete_item` | Delete item by ID | No | Yes |

### 1.3 Choose Transport

| Transport | When to Use |
|-----------|-------------|
| **stdio** | Local servers, CLI tools, fastest startup |
| **streamable_http** | Remote servers, deployed services |
| **sse** | Legacy remote servers (prefer streamable_http) |

For most custom integrations, **stdio** is correct (server runs in the user's sandbox).

---

## Phase 2: Implementation

### Python with FastMCP (Recommended)

```python
"""MCP server for [ServiceName].

Run: python server.py
"""

import os

from fastmcp import FastMCP

mcp = FastMCP(
    "[service-name]",
    description="[Concise description of what this server provides]",
)

API_KEY = os.environ.get("[SERVICE]_API_KEY", "")
BASE_URL = "https://api.service.com/v1"


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": True},
)
async def list_items(query: str = "", limit: int = 20) -> list[dict]:
    """List items matching the query.

    Args:
        query: Search filter (empty = all items)
        limit: Maximum results (1-100)
    """
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/items",
            params={"q": query, "limit": min(limit, 100)},
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["items"]


@mcp.tool(
    annotations={"readOnlyHint": False, "destructiveHint": True},
)
async def delete_item(item_id: str) -> str:
    """Delete an item permanently.

    Args:
        item_id: The item identifier to delete
    """
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{BASE_URL}/items/{item_id}",
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return f"Deleted item {item_id}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### TypeScript with MCP SDK

```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({
  name: "[service-name]",
  version: "1.0.0",
});

server.tool(
  "list_items",
  "List items matching a query",
  { query: z.string().optional(), limit: z.number().min(1).max(100).default(20) },
  async ({ query, limit }) => {
    const resp = await fetch(`${BASE_URL}/items?q=${query}&limit=${limit}`, {
      headers: { Authorization: `Bearer ${API_KEY}` },
    });
    const data = await resp.json();
    return { content: [{ type: "text", text: JSON.stringify(data.items) }] };
  },
  { annotations: { readOnlyHint: true, openWorldHint: true } }
);

const transport = new StdioServerTransport();
await server.connect(transport);
```

### Key Implementation Rules

1. **Type all parameters** with Pydantic (Python) or Zod (TypeScript)
2. **Set timeouts** on all HTTP requests (30s default)
3. **Return actionable errors** — include what went wrong and how to fix it
4. **Paginate large results** — never return unbounded lists
5. **Use environment variables** for secrets — never hardcode

---

## Common Patterns

### Authentication

```python
import os
API_KEY = os.environ.get("SERVICE_API_KEY", "")
if not API_KEY:
    raise ValueError("Set SERVICE_API_KEY environment variable")
```

### Pagination (Cursor-Based)

```python
@mcp.tool(annotations={"readOnlyHint": True})
async def list_all(cursor: str | None = None, limit: int = 50) -> dict:
    """List with pagination. Returns items and next_cursor."""
    params = {"limit": limit}
    if cursor:
        params["cursor"] = cursor
    resp = await client.get(f"{BASE_URL}/items", params=params)
    data = resp.json()
    return {"items": data["items"], "next_cursor": data.get("next_cursor")}
```

### Retry with Backoff

```python
import asyncio
import httpx

async def request_with_retry(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    """HTTP request with exponential backoff on rate limits."""
    for attempt in range(3):
        resp = await client.request(method, url, **kwargs)
        if resp.status_code == 429:
            wait = 2 ** attempt
            await asyncio.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    raise httpx.HTTPStatusError("Rate limited after 3 retries", request=resp.request, response=resp)
```

---

## Phase 3: Verify & Security

### 3.1 Quick Verification

Run this to confirm the server starts and lists tools:

```python
import asyncio
import subprocess
import json

async def verify_server(command: list[str]):
    """Verify MCP server starts and responds to initialize."""
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    init_request = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05",
                   "capabilities": {}, "clientInfo": {"name": "verify", "version": "1.0"}}
    }) + "\n"

    proc.stdin.write(init_request.encode())
    await proc.stdin.drain()

    line = await asyncio.wait_for(proc.stdout.readline(), timeout=10.0)
    result = json.loads(line)
    assert "result" in result, f"Initialize failed: {result}"
    print(f"Server: {result['result']['serverInfo']['name']}")

    list_request = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n"
    proc.stdin.write(list_request.encode())
    await proc.stdin.drain()

    line = await asyncio.wait_for(proc.stdout.readline(), timeout=10.0)
    tools = json.loads(line)["result"]["tools"]
    print(f"Tools ({len(tools)}):")
    for t in tools:
        annotations = t.get("annotations", {})
        ro = "R" if annotations.get("readOnlyHint") else "W"
        print(f"  [{ro}] {t['name']}: {t.get('description', '')[:60]}")

    proc.terminate()
    print("PASS: Server verified successfully")

# Usage: asyncio.run(verify_server(["python", "server.py"]))
```

### 3.2 Security Requirements

The framework automatically scans MCP servers on connection. Ensure:

| Requirement | What It Checks | How to Pass |
|-------------|---------------|-------------|
| **Clean tool names** | No injection characters in names | Use `snake_case` alphanumeric names only |
| **Safe descriptions** | No prompt injection patterns | Write factual, concise descriptions |
| **No exfiltration URLs** | Descriptions don't contain suspicious URLs | Don't embed URLs in tool descriptions |
| **Response size** | Tools don't return unbounded data | Paginate, limit response size |
| **Tool count** | Max 1000 tools per server | Keep focused — prefer fewer quality tools |

### 3.3 Annotations (Critical for UX)

| Annotation | Effect | When to Set |
|-----------|--------|-------------|
| `readOnlyHint: true` | Tool auto-approves (no user confirmation) | GET/list/search operations |
| `destructiveHint: true` | Extra warning shown to user | DELETE/overwrite operations |
| `idempotentHint: true` | Safe to retry on failure | PUT/upsert operations |
| `openWorldHint: true` | Tool accesses external network | Any API call |

**If you omit annotations, ALL tools require manual approval.** Always annotate.

---

## Phase 4: Register with Myrm

### 4.1 Configuration Format

Add to the agent's MCP configuration (via WebUI Settings > MCP Servers):

**Stdio (local server):**
```json
{
  "name": "my-service",
  "type": "stdio",
  "command": "python",
  "args": ["path/to/server.py"],
  "description": "Access MyService for project management"
}
```

**Streamable HTTP (remote server):**
```json
{
  "name": "my-service",
  "type": "streamable_http",
  "url": "https://my-server.example.com/mcp",
  "headers": {"Authorization": "Bearer {{secret:MY_SERVICE_TOKEN}}"},
  "description": "Access MyService for project management"
}
```

### 4.2 Configuration Fields

| Field | Required | Description |
|-------|:--------:|-------------|
| `name` | Yes | Unique identifier (alphanumeric + hyphens) |
| `type` | Yes | `stdio`, `sse`, or `streamable_http` |
| `command` | stdio | Executable command |
| `args` | stdio | Command arguments |
| `url` | http | Server URL |
| `description` | Recommended | Helps the agent understand when to use this tool |
| `headers` | Optional | HTTP headers (use `{{secret:KEY}}` for tokens) |
| `tool_include` | Optional | Whitelist specific tools by name |
| `tool_exclude` | Optional | Blacklist specific tools by name |
| `connect_timeout` | Optional | Connection timeout in seconds (default: 15) |
| `execute_timeout` | Optional | Tool call timeout in seconds (default: 120) |

### 4.3 Test in Conversation

After registration, verify the server works:

1. Start a new conversation
2. The agent discovers the MCP server tools automatically
3. Ask the agent to use a read-only tool first (should auto-approve)
4. Then test a write operation (should show approval dialog)

---

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| No annotations | Everything requires approval clicks | Set `readOnlyHint: true` on reads |
| Hardcoded secrets | Security risk, not portable | Use environment variables |
| Unbounded responses | Token explosion, slow agent | Paginate, limit to 50 items |
| Vague tool names | Agent picks wrong tool | Use `verb_noun` naming: `list_issues`, `create_project` |
| No error handling | Agent sees raw stack traces | Catch exceptions, return clear messages |
| Too many tools | Agent confused by choice overload | Keep under 20 tools per server |
