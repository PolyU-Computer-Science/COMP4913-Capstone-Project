# Configuration & Development Guide

## Configuration

Settings can be provided two ways: **`.env` defaults** and **runtime Settings
UI** (stored in `data/settings.db`, overriding env).

> **Startup seeding**: on first startup the backend seeds (a) a default AI
> config from `.env`, (b) stage prompt/parameter defaults from
> `core/stage_seeds.py`, and (c) a default mailbox with study/work topics and
> custom fields from `core/mailbox_seeds.py` (password from `EMAIL_PASSWORD`).
> After seeding, `data/settings.db` is the single source of truth — edit via
> the Settings UI or `GET/PUT /settings/stages`.

### LLM Provider Selection

Set `LLM_PROVIDER` to exactly one of `local`, `openai`, `openrouter`,
`anthropic`, `groq`, `deepseek`, or `google`. Only the selected provider is
validated, so local mode does not require remote API keys. The active
provider/model can also be switched at runtime in **System → AI Models**.

```dotenv
# Provider & safety guardrails
LLM_PROVIDER=local
LLM_TEMPERATURE=0.2
LLM_TIMEOUT=120
LLM_MAX_TOKENS=2000

# Local / OpenAI-compatible server (LM Studio, vLLM, llama.cpp, Ollama)
LOCAL_BASE_URL=http://localhost:11434/v1
LOCAL_MODEL=local-model
# LOCAL_API_KEY=sk-...           # Optional: for authenticated proxies/middleware

# OpenRouter (recommended runtime provider)
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=xiaomi/mimo-v2.5-pro
# OPENROUTER_API_KEY=sk-or-v1-...

# OpenAI Example
# OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-4o-mini

# Anthropic Example
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# Google Gemini Example
# GOOGLE_API_KEY=...
# GOOGLE_MODEL=gemini-2.0-flash

# (also supported: groq, deepseek — see .env.example)
```

### Embeddings (Knowledge / RAG)

```dotenv
# hashing (offline, deterministic, tests) | openrouter | openai | ollama | mistral | gemini | local
EMBEDDING_PROVIDER=ollama
EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_MODEL=qwen3-embedding-4b
EMBEDDING_BATCH_SIZE=32
```

- `hashing` is a deterministic offline client used by tests/CI.
- Hosted providers resolve the API key from their official env var
  (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `MISTRAL_API_KEY`, `GEMINI_API_KEY`);
  `ollama` and `local` need no key. A missing key raises
  `EmbeddingConfigurationError` (no silent fallback).
- Client: `core/openai_embeddings.py` (`OpenAICompatibleEmbeddingClient`,
  `build_openai_compatible_embedding_client(provider)`).
- The embedding dimension is discovered from the first response, never
  hardcoded. Changing provider/model/dimension marks existing indexes stale and
  triggers a reindex (see `core/embeddings.py`).

### Email Configuration (IMAP)

Mailboxes are the primary unit — each mailbox owns its own IMAP/SMTP
connection, topics, fields, knowledge, and connectors. Configure them in
**Mailboxes → Connection**. A default mailbox is seeded on first startup; its
password comes from `EMAIL_PASSWORD` in `.env`.

```dotenv
EMAIL_PASSWORD=your-app-password   # Google App Password (seeds the default mailbox)
```

> The legacy unscoped env-based sync path (`EMAIL_ENABLED` / `EMAIL_SERVER` /
> …) has been removed — `POST /emails/sync` always targets one or all mailboxes
> from the settings DB.

> **Folder naming:** use the exact IMAP mailbox name (e.g. `INBOX`).
> Sub-folders use the server's hierarchy separator (`INBOX.Subfolder` or
> `INBOX/Subfolder`) — not spaces.

### API Server

```dotenv
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Frontend (frontend/.env)
# VITE_PORT=5173
# VITE_API_TARGET=http://localhost:8000
```

### Persistence & Secrets

```dotenv
SQLITE_SETTINGS_DB=data/settings.db
# SQLITE_EMAIL_DB=data/emails.db          (default shown)
# KNOWLEDGE_DB=data/knowledge.db
# OBSERVABILITY_DB=data/observability.db
# SETTINGS_ENCRYPTION_KEY=...             # Optional Fernet key; auto-generated to data/.secret_key
```

All state is persisted in SQLite (auto-created on first run):

| Database | File | Contents |
| --- | --- | --- |
| **Email Store** | `data/emails.db` | Emails as tickets (sender, subject, body, classification fields, draft, sent timestamp, mailbox_id) + attachments + case field values + draft knowledge provenance. IDs are content-hashed with mailbox scope for dedupe. |
| **Settings Store** | `data/settings.db` | AI configs, stage settings, mailboxes, topics, custom fields, knowledge sources, connectors, tool permissions. |
| **Knowledge Store** | `data/knowledge.db` | Indexed knowledge documents + chunks (embedding vectors as JSON, mailbox-scoped). |
| **Observability Store** | `data/observability.db` | Processing runs (latency/tokens/status) + tool audit logs. |

**Secret handling:** API keys and mail passwords are encrypted at rest with
**Fernet** (`cryptography`). The key comes from `SETTINGS_ENCRYPTION_KEY` or is
auto-generated to `data/.secret_key`. Secrets are always masked in API
responses and redacted in tool audit logs.

---

## Usage

### Web UI (primary workflow)

1. **Mailboxes → Add Mailbox** — create a business context (a default mailbox with topics/fields is auto-seeded on first startup).
2. **Mailbox → Connection** — configure IMAP/SMTP, then *Test Connection* (login check only — no emails fetched).
3. **System → AI Models** — configure an LLM provider (use *Test Connection*), then activate it.
4. **Mailbox → Topics / Fields** — define the mailbox's taxonomy and custom fields.
5. **Mailbox → Knowledge** — add a source, *Index* it, then *Test Retrieval*.
6. **Mailbox → Connectors** — discover tools and set permissions (default deny).
7. **Inbox → Sync** — fetch all emails (newest first) via IMAP; without a selected mailbox this syncs all mailboxes.
8. **Inbox → Process** — run Classifier → Retrieval → Drafter on an email.
9. **Cases** — review the classification, fields, knowledge provenance and draft; edit if needed, then *Approve & Send*.

### CLI Mode

```bash
uv run run_crew
```

Runs the full pipeline: `fetch_emails()` → Classifier → Drafter. The
classification result is validated against the `EmailClassification` Pydantic
model (category, topic, priority, summary, custom_fields).

### Evaluation

```bash
# Regenerate the synthetic evaluation datasets (seeded, deterministic).
uv run python -m evaluation.generator

# Run a real evaluation against OpenRouter (consumes credit).
uv run python -m scripts.run_evaluation --limit 20 --experiments cls,ret,fe,draft
```

See `evaluation/README.md` for dataset methodology and `evaluation/results/`
(git-ignored) for raw runs.

---

## Development

### Run Tests

```bash
uv run pytest            # 284 tests (core + backend API), no real API calls required
```

### Lint & Format

```bash
# Frontend (uses oxlint)
cd frontend && npm run lint

# Python (ruff, if installed)
uv run ruff check .
uv run ruff format .
```

### Typecheck & Build (frontend)

```bash
cd frontend && npm run build   # tsc -b && vite build
```

### Dependency Management

```bash
uv add <package>         # Add a Python dependency
uv sync                  # Sync environment
```
