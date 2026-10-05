"""MCP Streamable HTTP transport.

Implements ``MCPTransport`` against a stateless Streamable HTTP MCP server
(e.g. ``https://demo.solutionforest.net/mcp/mtr/``) using plain JSON-RPC over
POST. Transport errors are normalised into our own exception types so the rest
of the runtime never depends on the MCP SDK or HTTP library internals.

A ``NoopTransport`` is retained for offline tests/CI, so automated tests never
make network calls.

Server URLs are validated before any request is made (SSRF guard): only
``https://`` URLs on public hosts are allowed by default, with an optional
admin allowlist (``ALLOWED_MCP_SERVERS``) for exceptions.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
from urllib.parse import urlparse
from typing import Any

from email_assistant.core.mcp_runtime import MCPTransport, NoopTransport  # noqa: F401

MCP_PROTOCOL_VERSION = "2025-06-18"

DEFAULT_ALLOWED_MCP_SERVERS = (
    "https://demo.solutionforest.net/mcp/mtr/",
)


class MCPConnectionError(RuntimeError):
    """Could not connect / transport failure."""


class MCPServerNotAllowed(MCPConnectionError):
    """The server URL was rejected by the SSRF guard."""


def validate_server_url(server: str) -> str:
    """Validate an MCP server URL before any request is made.

    Rules (SSRF guard):
    - must be a valid ``https://`` URL (http is rejected; the allowlist can
      only relax the private-host rule, not the TLS rule);
    - the host must not resolve to a loopback, private, link-local, or
      unspecified address;
    - URLs on the ``ALLOWED_MCP_SERVERS`` allowlist (comma-separated env var,
      defaulted to the demo MTR endpoint) bypass the private-host check but
      never the https requirement.

    Returns the normalised URL, or raises ``MCPServerNotAllowed``.
    """
    raw = (server or "").strip()
    parsed = urlparse(raw)

    if parsed.scheme != "https" or not parsed.hostname:
        raise MCPServerNotAllowed(
            "MCP server URL must be an https:// URL with a hostname"
        )

    host = parsed.hostname
    normalised = f"https://{host}{parsed.path or '/'}"

    allowlist = [
        entry.strip().rstrip("/")
        for entry in os.environ.get(
            "ALLOWED_MCP_SERVERS",
            ",".join(DEFAULT_ALLOWED_MCP_SERVERS),
        ).split(",")
        if entry.strip()
    ]
    if normalised.rstrip("/") in allowlist:
        return normalised

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as error:
        raise MCPServerNotAllowed(
            f"MCP server host could not be resolved: {host}"
        ) from error

    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_unspecified
            or address.is_reserved
        ):
            raise MCPServerNotAllowed(
                f"MCP server host resolves to a non-public address ({address}); "
                "refusing to connect"
            )

    return normalised


class MCPTimeoutError(MCPConnectionError):
    """Request timed out."""


class MCPProtocolError(MCPConnectionError):
    """Malformed or unexpected protocol response."""


class MCPToolError(RuntimeError):
    """The server reported an error for a tool call."""


class StreamableHttpTransport(MCPTransport):
    """Stateless Streamable HTTP MCP transport via JSON-RPC over POST."""

    def __init__(self, timeout: float = 30.0, transport: Any = None) -> None:
        self._timeout = timeout
        self._transport = transport  # optional httpx client (for tests)

    def _client(self):
        if self._transport is not None:
            return self._transport
        import httpx

        return httpx.Client(timeout=self._timeout)

    def _rpc(self, server: str, method: str, params: dict | None) -> Any:
        import httpx

        server = validate_server_url(server)
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        }
        client = self._client()
        try:
            response = client.post(server, json=body, headers=headers)
        except httpx.TimeoutException as error:
            raise MCPTimeoutError(f"MCP request timed out: {error}") from error
        except httpx.RequestError as error:
            raise MCPConnectionError(f"MCP request failed: {error}") from error

        try:
            payload = response.json()
        except ValueError as error:
            raise MCPProtocolError(
                f"MCP invalid JSON response ({response.status_code})"
            ) from error

        if response.status_code >= 400:
            raise MCPConnectionError(
                f"MCP server error ({response.status_code}): {_snippet(str(payload))}"
            )

        if payload.get("error"):
            err = payload["error"]
            raise MCPProtocolError(
                f"MCP protocol error {err.get('code')}: {err.get('message')}"
            )

        return payload.get("result")

    def _initialize(self, server: str) -> None:
        # Stateless servers accept each request independently; initialize is
        # best-effort and only needed to negotiate capabilities.
        try:
            self._rpc(
                server,
                "initialize",
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "email-assistant", "version": "1.0.0"},
                },
            )
        except MCPConnectionError:
            # Some servers skip initialize; tools/list still works.
            pass

    def list_tools(self, server: str) -> list[dict[str, Any]]:
        self._initialize(server)
        result = self._rpc(server, "tools/list", {})
        tools = (result or {}).get("tools") or []
        return [
            {
                "name": str(t.get("name", "")),
                "title": str(t.get("title") or t.get("name", "")),
                "description": str(t.get("description") or ""),
                "input_schema": t.get("inputSchema") or {},
                "output_schema": t.get("outputSchema") or {},
                "annotations": _annotations_dict(t.get("annotations")),
            }
            for t in tools
        ]

    def call_tool(self, server: str, tool_name: str, arguments: dict) -> Any:
        self._initialize(server)
        result = self._rpc(
            server,
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
        )
        if result is None:
            return None
        if result.get("isError"):
            raise MCPToolError(
                f"MCP tool '{tool_name}' returned an error: {_snippet(str(result))}"
            )
        return result


def _annotations_dict(annotations: Any) -> dict:
    if annotations is None:
        return {}
    if hasattr(annotations, "model_dump"):
        return annotations.model_dump()
    if isinstance(annotations, dict):
        return annotations
    return {}


def _snippet(text: str) -> str:
    return (text or "")[:300]


class StreamableHttpTransportFactory:
    """Creates a real transport for a connector (used by the runtime)."""

    def __call__(self) -> StreamableHttpTransport:
        return StreamableHttpTransport()
