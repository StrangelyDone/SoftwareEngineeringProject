---
title: "MCP Architecture"
author: "StrangelyDone"
created: 2026-11-26
tags: [youtube-mcp, resource, mcp-architecture]
type: resource
---

# Model Context Protocol (MCP) Architecture

## Summary
MCP standardizes how AI applications connect to external data and capabilities through JSON-RPC 2.0. An application host manages a separate client connection to each MCP server, keeping orchestration, permissions, and conversation context under host control. This gives the YouTube project a common interface for exposing read operations and user-approved actions to clients such as Claude Desktop.

## Key Technical Details
- **Host, client, server:** The host is the AI application and coordinator; its MCP client communicates with one server; the server exposes focused capabilities. Servers do not receive the host's full conversation or access other servers' connections.
- **JSON-RPC messages:** MCP messages use JSON-RPC 2.0. A request has an `id` and `method` (and may include `params`); its response carries the matching `id`. A notification has no `id` and does not expect a response. Examples include `tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, and `prompts/get`. In the 2026-07-28 specification, request metadata includes protocol version and client capabilities.
- **Tools — model-invoked actions:** A tool has a name, description, and JSON Schema input; it returns a result and may define a structured output schema. Typical operations for this project could include finding similar videos or preparing a playlist. Tools that change a user's account must remain behind an explicit confirmation step.
- **Resources — application-selected context:** A resource is data addressed by a URI and read through `resources/read`; hosts decide how to present or add it as context. For example, `youtube://videos/{video_id}/metadata` could identify read-only video metadata, but this is an illustrative project URI, not an implemented endpoint or MCP-reserved scheme.
- **Prompts — user-selected templates:** A server can list reusable prompt templates and return a selected prompt with its arguments. They help users start workflows but are distinct from tools, which execute actions.
- **stdio — local process:** The client launches the server as a subprocess and exchanges newline-delimited JSON-RPC messages over stdin/stdout. Only protocol messages may be written to stdout; diagnostics belong on stderr.
- **Streamable HTTP — network service:** The server runs independently and exchanges MCP messages over HTTP. Replies may be JSON or an SSE event stream. The former HTTP+SSE transport was replaced by Streamable HTTP; SSE remains an optional streaming mechanism within it.
- **Claude Desktop integration:** Claude Desktop acts as the host. Its `mcpServers` configuration maps a server name to a command and arguments; for a local server, Desktop launches that command over stdio and exposes the server's declared capabilities after restart. The project guidance targets a Python FastMCP server in `src/server.py` backed by provider interfaces and the official YouTube Data API v3. The current repository contains only a package scaffold, so this connection is a target architecture, not a working integration yet.

## Project Traceability & Connections
- **Related Requirements:** FR-1 (similar-video capability), FR-5 (playlist creation only after explicit user confirmation), SE-7 (document MCP client setup), CON-1 (use only the official YouTube Data API v3).
- **Related Notes:** [[index]], [[provider-pattern-isolation]], [[youtube-api-quota-system]]
- **Source:**
  - [MCP Architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture)
  - [MCP Transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
  - [MCP Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), [Resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources), and [Prompts](https://modelcontextprotocol.io/specification/2026-07-28/server/prompts)
  - [Build an MCP server and connect it to Claude Desktop](https://modelcontextprotocol.io/docs/2026-07-28/develop/build-server)
  - Project architecture and constraints: `AGENTS.md`
