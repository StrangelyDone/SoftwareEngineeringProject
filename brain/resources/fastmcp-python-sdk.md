---
title: "FastMCP for Python"
author: "@StrangelyDone"
created: 2026-11-26
tags: [youtube-mcp, resource, fastmcp, python]
type: resource
---

# FastMCP for Python

## Summary
FastMCP is the high-level server API in the MCP Python SDK v1.x, providing decorators and Python type-driven schemas for MCP tools, resources, and prompts. It can expose Streamable HTTP as a Starlette ASGI application, allowing an application to host MCP alongside ordinary HTTP routes such as the project's read-only health check. SDK version matters: v2 is now the stable line and renames `FastMCP` to `MCPServer`.

## Key Technical Details
- **High-level server:** In SDK v1.x, import `FastMCP` from `mcp.server.fastmcp` and create an instance, for example `mcp = FastMCP("YouTube MCP")`. Register a normal Python function with `@mcp.tool()`; the function name and docstring provide its tool identity and description.
- **Input schemas and validation:** FastMCP derives the tool input JSON Schema from annotated Python parameters, including required and optional arguments. Pydantic types and models can express richer input constraints; the SDK validates tool arguments against the generated schema before invoking the function. MCP clients use that schema to present and call tools.
- **Structured output:** Annotated return types can produce an output schema and structured result. Supported return forms include Pydantic `BaseModel`, `TypedDict`, dataclasses and annotated classes, JSON-serializable dictionaries, and primitive or generic types. Output is checked against its generated schema. Use `CallToolResult` when the handler needs direct control over content or structured error details.
- **ASGI integration:** `mcp.streamable_http_app()` in the v1.x SDK returns a Starlette ASGI app. Mount it into a parent Starlette app using `Mount`, or attach it to a compatible ASGI application such as FastAPI, and serve the composed app with an ASGI server. This lets MCP use its own Streamable HTTP path while the same host exposes a separate `GET /api/v1/health` route returning ordinary HTTP JSON. The health route is not an MCP tool or resource.
- **Error mapping:** Raise `ToolError` for expected tool failures; the SDK returns a tool result with `isError=True`. Unhandled exceptions are also converted into tool errors, but their exception text may reach the caller. For safe, predictable user-facing errors, catch known provider/domain exceptions and map them to concise remediation text; return a `CallToolResult` with `isError=True` when custom content or a structured error payload is needed. Avoid exposing tracebacks, credentials, or raw provider details.
- **Version compatibility:** The v1.x import path is `from mcp.server.fastmcp import FastMCP`; pin the dependency below v2 (for example, `mcp>=1.28,<2`) if code depends on it. The official SDK v2 documentation says the class and module were renamed to `MCPServer` and `mcp.server`, respectively. Confirm the selected SDK major version before copying examples or writing dependency constraints.
- **Project application:** The project specifies FastMCP in `AGENTS.md`, isolates YouTube API calls behind provider interfaces (`SE-6`), and describes the local health route in its SRS (`SE-7`). A typed tool for finding similar videos can implement `FR-1`; the repository currently has a package scaffold rather than this server or mounted app, so these are integration patterns, not implemented behavior.

## Project Traceability & Connections
- **Related Requirements:** SE-6, SE-7, SK-4, FR-1
- **Related Notes:** [[index]], [[mcp-architecture]], [[provider-pattern-isolation]]
- **Source:**
  - [Official MCP Python SDK v1.x documentation](https://py.sdk.modelcontextprotocol.io/v1/)
  - [v1.x server guide: tools, errors, structured output](https://py.sdk.modelcontextprotocol.io/v1/server/)
  - [Official v1.x Starlette mount example](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/examples/snippets/servers/streamable_starlette_mount.py)
  - [Official SDK v2 migration guide](https://py.sdk.modelcontextprotocol.io/migration/)
  - Project architecture and health endpoint requirements: `AGENTS.md` and `SE_SRS.pdf`
