"""Pydantic schemas for the FastAPI layer."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmailItem(BaseModel):
    """A single fetched email."""

    id: str
    sender: str
    subject: str
    body: str
    timestamp: str
    html: str = ""
    status: str = "new"
    mailbox_id: int | None = None


class ProcessRequest(BaseModel):
    """Payload for processing a single email through the AI crew."""

    email: EmailItem


class ClassificationOut(BaseModel):
    """Structured classification result returned by the classifier agent."""

    category: str
    topic: str
    priority: str
    urgency_score: int
    summary: str
    custom: dict = Field(default_factory=dict)
    topic_id: int | None = None
    topic_raw: str = ""


class CaseOut(BaseModel):
    """A processed email case with its classification and draft reply."""

    id: str
    email: EmailItem
    classification: ClassificationOut
    draft: str
    created_at: str
    sent_at: str | None = None
    mailbox_id: int | None = None
    topic_id: int | None = None
    topic_raw: str = ""
    knowledge_refs: list[dict] = Field(default_factory=list)


class DraftIn(BaseModel):
    """Payload for updating a case's draft reply."""

    draft: str


class ProcessResponse(BaseModel):
    """Result of processing a single email."""

    case: CaseOut


class EmailsResponse(BaseModel):
    """List of fetched emails."""

    emails: list[EmailItem]
    count: int


class SyncResponse(BaseModel):
    """Result of syncing the inbox (fetch + persist)."""

    synced: int
    emails: list[EmailItem]
    count: int


class CasesResponse(BaseModel):
    """List of processed cases."""

    cases: list[CaseOut]
    count: int


class StatsOut(BaseModel):
    """Dashboard statistics computed from the case store."""

    total_emails: int
    processed: int
    pending: int
    success_rate: float
    category_distribution: list[dict]
    recent_activity: list[dict]


class AIConfig(BaseModel):
    """An AI configuration as exposed to the frontend (api key masked)."""

    id: int
    name: str = ""
    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    has_api_key: bool = False
    timeout: float = 120
    max_tokens: int = 8000
    temperature: float = 0.2
    enabled: bool = False


class AIConfigIn(BaseModel):
    """Payload for creating or updating an AI configuration."""

    name: str
    provider: str
    model: str
    base_url: str = ""
    api_key: str = ""
    timeout: float = 120
    max_tokens: int = 8000
    temperature: float = 0.2
    enabled: bool = False


class StageConfig(BaseModel):
    """Per-stage settings (system prompt, task prompt, generation params)."""

    role: str = ""
    goal: str = ""
    backstory: str = ""
    prompt: str = ""
    max_tokens: int | None = None
    temperature: float | None = None


class StagesSettings(BaseModel):
    """Global per-stage settings for classification and drafting."""

    classification: StageConfig
    draft: StageConfig


class TestResult(BaseModel):
    """Result of a settings test / connection check."""

    ok: bool
    message: str


class MailAccount(BaseModel):
    """A mail account as exposed to the frontend (password masked)."""

    id: int
    name: str = ""
    address: str
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587
    password: str = ""
    has_password: bool = False
    max_emails: int = 50
    enabled: bool = True


class MailAccountIn(BaseModel):
    """Payload for creating or updating a mail account."""

    name: str = ""
    address: str
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587
    password: str = ""
    max_emails: int = 50
    enabled: bool = True


# ---- mailboxes ----


class MailboxIn(BaseModel):
    """Payload for creating or updating a mailbox (business context)."""

    name: str
    address: str = ""
    purpose: str = ""
    status: str = "active"
    imap_host: str = ""
    imap_port: int = 993
    imap_security: str = "ssl"
    imap_folder: str = "INBOX"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "starttls"
    password: str = ""
    max_emails: int = 50
    auto_process: bool = False
    generate_drafts: bool = True
    human_approval: bool = True
    classifier_config_id: int | None = None
    drafter_config_id: int | None = None
    classifier_temperature: float | None = None
    classifier_max_tokens: int | None = None
    drafter_temperature: float | None = None
    drafter_max_tokens: int | None = None
    use_knowledge: bool = False
    instructions: str = ""
    is_system: bool = False


class MailboxOut(BaseModel):
    """A mailbox as exposed to the frontend (password never returned)."""

    id: int
    name: str
    address: str = ""
    purpose: str = ""
    status: str = "active"
    imap_host: str = ""
    imap_port: int = 993
    imap_security: str = "ssl"
    imap_folder: str = "INBOX"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "starttls"
    has_password: bool = False
    max_emails: int = 50
    auto_process: bool = False
    generate_drafts: bool = True
    human_approval: bool = True
    classifier_config_id: int | None = None
    drafter_config_id: int | None = None
    classifier_temperature: float | None = None
    classifier_max_tokens: int | None = None
    drafter_temperature: float | None = None
    drafter_max_tokens: int | None = None
    use_knowledge: bool = False
    instructions: str = ""
    is_system: bool = False


class TopicIn(BaseModel):
    name: str
    description: str = ""
    status: str = "active"


class TopicOut(BaseModel):
    id: int
    mailbox_id: int
    name: str
    description: str = ""
    status: str = "active"


class CustomFieldIn(BaseModel):
    name: str
    type: str = "text"
    required: bool = False
    options: str = ""
    prompt: str = ""
    status: str = "active"


class CustomFieldOut(BaseModel):
    id: int
    mailbox_id: int
    name: str
    type: str = "text"
    required: bool = False
    options: str = ""
    prompt: str = ""
    status: str = "active"


class KnowledgeSourceIn(BaseModel):
    name: str
    type: str = "document"
    status: str = "ready"
    chunks: int = 0
    content: str = ""


class KnowledgeSourceOut(BaseModel):
    id: int
    name: str
    type: str = "document"
    status: str = "ready"
    chunks: int = 0
    content: str = ""


class ConnectorIn(BaseModel):
    name: str
    type: str = "mcp"
    server: str = ""
    status: str = "disconnected"


class ConnectorOut(BaseModel):
    id: int
    name: str
    type: str = "mcp"
    server: str = ""
    status: str = "disconnected"


class MailboxConnectorOut(BaseModel):
    id: int
    name: str
    type: str = "mcp"
    server: str = ""
    status: str = "disconnected"
    enabled: bool = False
    allowed_tools: str = ""


class ConnectorAssignmentIn(BaseModel):
    enabled: bool = True
    allowed_tools: str = ""


# ---- case fields ----


class CaseFieldOut(BaseModel):
    """A mailbox custom field merged with its value for a specific case."""

    field_id: int
    key: str
    name: str
    type: str = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)
    value: object = None


class CaseFieldsIn(BaseModel):
    """Bulk update of case field values, keyed by field id."""

    values: dict[str, Any] = Field(default_factory=dict)


# ---- knowledge indexing / retrieval ----


class KnowledgeIndexResult(BaseModel):
    status: str
    document_id: int | None = None
    chunks: int = 0
    skipped: bool = False
    error: str | None = None


class KnowledgeDocumentOut(BaseModel):
    id: int
    mailbox_id: int
    source_id: int
    title: str = ""
    status: str = "pending"
    content_hash: str = ""
    indexed_at: str | None = None


class RetrievalRequest(BaseModel):
    query: str
    top_k: int = 8
    source_ids: list[int] | None = None


class RetrievalResultOut(BaseModel):
    source_id: int
    source_name: str = ""
    chunk_id: int
    document_id: int
    chunk_index: int = 0
    score: float
    content: str
    metadata: dict = Field(default_factory=dict)


class RetrievalEmbeddingOut(BaseModel):
    provider: str = ""
    model: str = ""
    dim: int = 0


class RetrievalStatsOut(BaseModel):
    top_k: int = 0
    chunks_considered: int = 0
    stale_chunks_skipped: int = 0
    returned_count: int = 0
    source_count: int = 0
    latency_ms: float = 0.0
    max_score: float = 0.0
    min_returned_score: float = 0.0


class RetrievalResponse(BaseModel):
    query: str
    embedding: RetrievalEmbeddingOut = Field(default_factory=RetrievalEmbeddingOut)
    stats: RetrievalStatsOut = Field(default_factory=RetrievalStatsOut)
    results: list[RetrievalResultOut]


# ---- connectors / MCP ----


class ToolDescriptorOut(BaseModel):
    connector_id: int
    name: str
    description: str = ""
    risk_level: str = "read"
    enabled: bool = False
    permission_level: str = "read"


class ToolPermissionIn(BaseModel):
    tool_name: str
    enabled: bool = False
    permission_level: str = "read"


class ConnectorPermissionsIn(BaseModel):
    permissions: list[ToolPermissionIn]


class ToolExecutionIn(BaseModel):
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    email_id: str | None = None
    case_id: str | None = None
    approved: bool = False


class ToolExecutionOut(BaseModel):
    ok: bool
    requires_approval: bool = False
    result: object = None
    error: str | None = None


# ---- observability ----


class ProcessingRunOut(BaseModel):
    id: int
    trace_id: str | None = None
    mailbox_id: int | None = None
    email_id: str | None = None
    case_id: str | None = None
    stage: str = "email_processing"
    status: str = "running"
    provider: str | None = None
    model: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    metadata: dict = Field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None


class ToolAuditOut(BaseModel):
    id: int
    mailbox_id: int | None = None
    email_id: str | None = None
    case_id: str | None = None
    connector_id: int | None = None
    tool_name: str = ""
    arguments_json_redacted: dict = Field(default_factory=dict)
    status: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    latency_ms: float | None = None
    result_summary: str = ""
    error_type: str | None = None
    error_message: str | None = None
