"""Phase 6C — MCP runtime tests (mocked transport, no network)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store
from email_assistant.core.mcp_runtime import MCPClientManager
from email_assistant.core.mcp_transport import (
    MCPConnectionError,
    MCPProtocolError,
    MCPToolError,
    MCPTimeoutError,
    StreamableHttpTransport,
)
from email_assistant.core.observability_store import ObservabilityStore
from email_assistant.core.settings_store import SettingsStore
from email_assistant.core.structured_classification import ClassificationContract
from email_assistant.core.structured_llm import OpenAICompatibleStructuredClient
from email_assistant.core.tool_executor import ToolExecutionGateway
from email_assistant.core.tool_planner import ActionProposal, ToolPlanner
from email_assistant.core.tool_permissions import default_risk_level

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.setenv("SQLITE_EMAIL_DB", str(tmp_path / "emails.db"))
    monkeypatch.setenv("OBSERVABILITY_DB", str(tmp_path / "observability.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    store.clear()
    ObservabilityStore().clear()
    yield


# ---- transport tests ----

class _FakeHttpResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json, headers):
        self.calls.append((url, json))
        return self.responses.pop(0)


def test_transport_lists_tools() -> None:
    http = _FakeHttpClient([
        _FakeHttpResponse(200, {"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "serverInfo": {"name": "mtr", "version": "1.0.0"},
        }}),
        _FakeHttpResponse(200, {"jsonrpc": "2.0", "id": 1, "result": {
            "tools": [{"name": "mtr_get_station", "inputSchema": {"type": "object"}}]
        }}),
    ])
    transport = StreamableHttpTransport(transport=http)
    tools = transport.list_tools("https://example.com/mcp")
    assert len(tools) == 1
    assert tools[0]["name"] == "mtr_get_station"


def test_transport_server_error_raises() -> None:
    http = _FakeHttpClient([
        _FakeHttpResponse(200, {"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "serverInfo": {"name": "mtr", "version": "1.0.0"},
        }}),
        _FakeHttpResponse(500, {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "boom"}}),
    ])
    transport = StreamableHttpTransport(transport=http)
    with pytest.raises(MCPConnectionError):
        transport.list_tools("https://example.com/mcp")


def test_transport_invalid_json_raises() -> None:
    class _BadResponse:
        status_code = 200
        def json(self):
            raise ValueError("bad")

    http = _FakeHttpClient([
        _FakeHttpResponse(200, {"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "serverInfo": {"name": "mtr", "version": "1.0.0"},
        }}),
        _BadResponse(),
    ])
    transport = StreamableHttpTransport(transport=http)
    with pytest.raises(MCPProtocolError):
        transport.list_tools("https://example.com/mcp")


def test_transport_tool_error_raises() -> None:
    http = _FakeHttpClient([
        _FakeHttpResponse(200, {"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "serverInfo": {"name": "mtr", "version": "1.0.0"},
        }}),
        _FakeHttpResponse(200, {"jsonrpc": "2.0", "id": 1, "result": {"isError": True}}),
    ])
    transport = StreamableHttpTransport(transport=http)
    with pytest.raises(MCPToolError):
        transport.call_tool("https://example.com/mcp", "mtr_get_station", {"station": "x"})


# ---- planner tests ----

class _FakeStructuredResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data
        self.text = ""

    def json(self):
        return self._json


class _FakeStructuredTransport:
    def __init__(self, handler):
        self.handler = handler

    def post(self, url, json):
        return self.handler(json)


def test_planner_produces_action_proposal() -> None:
    transport = _FakeStructuredTransport(
        lambda payload: _FakeStructuredResponse(
            200,
            {
                "model": "xiaomi/mimo-v2.5-pro",
                "choices": [{"message": {"content": (
                    '{"needs_tool": true, "connector_id": 3, '
                    '"tool_name": "mtr_next_trains", '
                    '"arguments": {"station": "ADM"}, "reason": "live train time"}'
                )}}],
                "usage": {},
            },
        )
    )
    llm = OpenAICompatibleStructuredClient(api_key="k", transport=transport)
    planner = ToolPlanner(llm)

    allowed = [{"connector_id": 3, "name": "mtr_next_trains", "description": "next trains"}]
    plan = planner.plan("When is the next train from Admiralty?", allowed)
    assert plan.valid is True
    assert plan.proposal.needs_tool is True
    assert plan.proposal.tool_name == "mtr_next_trains"


# ---- permission gateway tests ----

class _FakeMCPManager:
    def __init__(self, tools_by_server=None, results=None):
        self.tools_by_server = tools_by_server or {}
        self.results = results or {}
        self.executions = []

    def discover_tools(self, connector):
        server = connector.get("server", "")
        from email_assistant.core.mcp_runtime import ToolDescriptor

        return [
            ToolDescriptor(
                connector_id=connector["id"],
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("input_schema", {}),
                risk_level=t.get("risk_level", "read"),
            )
            for t in self.tools_by_server.get(server, [])
        ]

    def execute_tool(self, connector, tool_name, arguments):
        self.executions.append((tool_name, arguments))
        if tool_name in self.results:
            return self.results[tool_name]
        raise RuntimeError("tool failed")


def _setup_mailbox_connector_tool(
    mailbox_id, connector_id, tool_name, risk="read", enabled=True, input_schema=None
):
    settings = SettingsStore()
    settings.replace_connector_tools(connector_id, [
        {"name": tool_name, "description": "d", "input_schema": input_schema or {"type": "object", "properties": {"station": {"type": "string"}}, "required": ["station"]}, "risk_level": risk}
    ])
    settings.set_tool_permissions(mailbox_id, connector_id, {
        tool_name: {"enabled": enabled, "permission_level": risk}
    })


def test_gateway_executes_read_tool() -> None:
    manager = _FakeMCPManager(results={"mtr_get_station": {"content": [{"type": "text", "text": "ADM"}]}})
    settings = SettingsStore()
    mailbox_id = settings.create_mailbox({"name": "MTR", "address": "mtr@x.com"})["id"]
    connector_id = settings.create_connector({"name": "MTR", "type": "mcp", "server": "https://x"})["id"]
    settings.assign_connector(mailbox_id, connector_id, {"enabled": True})
    _setup_mailbox_connector_tool(mailbox_id, connector_id, "mtr_get_station", "read")

    gateway = ToolExecutionGateway(manager=manager, settings=settings)
    result = gateway.execute(
        mailbox_id=mailbox_id, connector_id=connector_id,
        tool_name="mtr_get_station", arguments={"station": "ADM"},
    )
    assert result.ok is True
    assert manager.executions == [("mtr_get_station", {"station": "ADM"})]


def test_gateway_denies_disabled_tool() -> None:
    manager = _FakeMCPManager()
    settings = SettingsStore()
    mailbox_id = settings.create_mailbox({"name": "MTR", "address": "mtr@x.com"})["id"]
    connector_id = settings.create_connector({"name": "MTR", "type": "mcp", "server": "https://x"})["id"]
    settings.assign_connector(mailbox_id, connector_id, {"enabled": True})
    _setup_mailbox_connector_tool(mailbox_id, connector_id, "mtr_get_station", "read", enabled=False)

    gateway = ToolExecutionGateway(manager=manager, settings=settings)
    result = gateway.execute(
        mailbox_id=mailbox_id, connector_id=connector_id,
        tool_name="mtr_get_station", arguments={"station": "ADM"},
    )
    assert result.denied is True
    assert manager.executions == []


def test_gateway_rejects_invalid_arguments() -> None:
    manager = _FakeMCPManager()
    settings = SettingsStore()
    mailbox_id = settings.create_mailbox({"name": "MTR", "address": "mtr@x.com"})["id"]
    connector_id = settings.create_connector({"name": "MTR", "type": "mcp", "server": "https://x"})["id"]
    settings.assign_connector(mailbox_id, connector_id, {"enabled": True})
    _setup_mailbox_connector_tool(mailbox_id, connector_id, "mtr_get_station", "read")

    gateway = ToolExecutionGateway(manager=manager, settings=settings)
    result = gateway.execute(
        mailbox_id=mailbox_id, connector_id=connector_id,
        tool_name="mtr_get_station", arguments={},
    )
    assert result.denied is True
    assert manager.executions == []


def test_gateway_write_tool_requires_approval() -> None:
    manager = _FakeMCPManager()
    settings = SettingsStore()
    mailbox_id = settings.create_mailbox({"name": "MTR", "address": "mtr@x.com"})["id"]
    connector_id = settings.create_connector({"name": "MTR", "type": "mcp", "server": "https://x"})["id"]
    settings.assign_connector(mailbox_id, connector_id, {"enabled": True})
    _setup_mailbox_connector_tool(
        mailbox_id, connector_id, "mtr_plan_route", "write",
        input_schema={"type": "object", "properties": {"from": {"type": "string"}, "to": {"type": "string"}}, "required": ["from", "to"]},
    )

    gateway = ToolExecutionGateway(manager=manager, settings=settings)
    result = gateway.execute(
        mailbox_id=mailbox_id, connector_id=connector_id,
        tool_name="mtr_plan_route", arguments={"from": "ADM", "to": "TST"},
    )
    assert result.requires_approval is True
    assert manager.executions == []

    # With approval, it executes.
    result = gateway.execute(
        mailbox_id=mailbox_id, connector_id=connector_id,
        tool_name="mtr_plan_route", arguments={"from": "ADM", "to": "TST"},
        approved=True,
    )
    assert manager.executions == [("mtr_plan_route", {"from": "ADM", "to": "TST"})]


def test_gateway_cross_mailbox_connector_denied() -> None:
    manager = _FakeMCPManager()
    settings = SettingsStore()
    mtr_mailbox = settings.create_mailbox({"name": "MTR", "address": "mtr@x.com"})["id"]
    other_mailbox = settings.create_mailbox({"name": "Support", "address": "s@x.com"})["id"]
    connector_id = settings.create_connector({"name": "MTR", "type": "mcp", "server": "https://x"})["id"]
    # Assign connector ONLY to mtr_mailbox.
    settings.assign_connector(mtr_mailbox, connector_id, {"enabled": True})
    _setup_mailbox_connector_tool(mtr_mailbox, connector_id, "mtr_get_station", "read")

    gateway = ToolExecutionGateway(manager=manager, settings=settings)
    result = gateway.execute(
        mailbox_id=other_mailbox, connector_id=connector_id,
        tool_name="mtr_get_station", arguments={"station": "ADM"},
    )
    assert result.denied is True
    assert manager.executions == []


def test_default_risk_level_for_mtr_tools_is_read() -> None:
    for name in ("mtr_list_lines", "mtr_get_station", "mtr_next_trains", "mtr_plan_route"):
        assert default_risk_level(name) == "read"
