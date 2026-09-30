# PolyU — Agentic AI Email Assistant

> **Final Year Project · Department of Computing**

A human-supervised, multi-stage AI email assistant that combines
deterministic email processing with LLM-based reasoning.

The system retrieves emails through IMAP, classifies them using
schema-validated LLM outputs, generates response drafts, and requires
explicit human approval before SMTP delivery.

The project investigates the reliability, safety, and effectiveness of
agentic AI for practical email management, with structured output
validation, Human-in-the-Loop controls, and Retrieval-Augmented
Generation (RAG).

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![CrewAI](https://img.shields.io/badge/CrewAI-1.15.12-purple.svg)](https://docs.crewai.com/)
[![Pydantic](https://img.shields.io/badge/Pydantic-Structured_Output-e92063.svg)](https://docs.pydantic.dev/)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003B57.svg)](https://www.sqlite.org/)

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Problem Statement](#problem-statement)
3. [Research Questions & Measurable Objectives](#research-questions--measurable-objectives)
4. [Key Contributions](#key-contributions)
5. [System Architecture](#system-architecture)
6. [Why This Architecture?](#why-this-architecture)
7. [Multi-Mailbox Context Model](#multi-mailbox-context-model)
8. [Agentic Workflow](#agentic-workflow)
9. [Safety & Threat Model](#safety--threat-model)
10. [Evaluation Methodology](#evaluation-methodology)
11. [Preliminary / Final Results](#preliminary--final-results)
12. [Current Implementation Status](#current-implementation-status)
13. [Quick Start](#quick-start)
14. [Project Structure](#project-structure)
15. [Limitations](#limitations)
16. [Roadmap](#roadmap)
17. [References](#references)

---

## Project Overview

This project builds a **multi-mailbox agentic AI email assistant** that
separates deterministic software operations from probabilistic LLM reasoning.
Each **mailbox is an isolated business context** — with its own topics, custom
fields, knowledge base, connectors, and AI behaviour — so the same engine
serves Support, Sales, HR, etc. without cross-context leakage.

- **Python Fetcher (`core/email_fetcher.py`):** Deterministic per-mailbox IMAP retrieval via `imap-tools` — no LLM tokens spent on mechanical operations.
- **CrewAI Engine:** Staged LLM reasoning (Classifier → Drafter) with Pydantic-validated structured outputs.
- **Knowledge / RAG:** Mailbox-scoped indexing, chunking, embeddings, and retrieval that grounds the drafter.
- **Attachment Intelligence (planned):** Safely processes case-specific attachments (PDFs, images, structured files and archives) into normalized context for classification, field extraction and drafting, without mixing customer attachments into the shared knowledge base.
- **MCP Runtime:** Connector tool discovery with default-deny permissions and audit logging.
- **Routing Engine:** Deterministic case routing maps mailbox-scoped classifications and extracted fields to operational teams, then assigns work to eligible agents using configurable manual, round-robin, or balanced strategies.
- **FastAPI Backend (`backend/app/`):** REST API for email sync, AI processing, case management, and runtime settings — all state persisted in SQLite.
- **React Frontend (`frontend/`):** Human-in-the-Loop UI for reviewing, editing, approving, and sending AI-generated drafts.
- **Observability:** Per-stage processing runs recording latency, token usage, and failures.

### Research Focus

This project investigates three central challenges in practical
LLM-based email automation:

- the **reliability** of structured AI outputs;
- **grounding** generated replies in organisational knowledge;
- **safe control** of AI-generated external actions.

---

## Problem Statement

Email remains an important communication channel in modern organisations,
but managing high volumes of messages can create significant information and
workflow overhead.

Existing LLM-based email assistants introduce several technical challenges:

1. **Unreliable structured output** — free-form LLM responses may produce
   malformed or inconsistent data that cannot safely drive downstream
   workflows.

2. **Hallucination and insufficient grounding** — generated replies may
   contain information unsupported by organisational knowledge.

3. **Excessive AI autonomy** — allowing an LLM to directly perform external
   actions such as sending email can introduce safety risks.

4. **Unnecessary use of LLM reasoning** — deterministic operations such as
   email retrieval do not require probabilistic AI reasoning.

5. **Manual triage and unclear ownership** — classification alone does not
   ensure that an incoming request reaches the appropriate operational team or
   an available human agent.

This project investigates a hybrid architecture that separates deterministic
operations from LLM reasoning and introduces structured validation, knowledge
grounding, and human approval.

---

## Research Questions & Measurable Objectives

### Research Questions

This project investigates the following questions:

**RQ1 — Classification Reliability**  
How accurately can LLMs classify incoming emails into predefined operational
categories?

**RQ2 — Structured Output Reliability**  
Does schema-constrained structured output reduce invalid or unparseable AI
responses compared with unconstrained generation?

**RQ3 — Retrieval-Augmented Generation**  
Does grounding email drafting with retrieved organisational knowledge improve
factual faithfulness and response relevance?

**RQ4 — Model Trade-offs**  
What trade-offs exist between classification quality, response quality,
latency, token usage, and cost across local and hosted LLMs?

**RQ5 — Safety**  
Can a Human-in-the-Loop architecture restrict potentially harmful agent
actions while preserving useful AI automation?

**RQ6 — Operational Routing**  
Can AI-derived email classifications be reliably transformed into
deterministic team and agent assignments under configurable routing policies?

### Measurable Objectives

| ID | Objective | Evaluation |
|---|---|---|
| O1 | Classify emails into question, incident, problem, task and spam | Accuracy, Precision, Recall, Macro-F1 |
| O2 | Produce machine-readable classification output reliably | Structured-output validity rate |
| O3 | Generate useful and contextually appropriate reply drafts | Human evaluation + response relevance |
| O4 | Ground replies using organisational knowledge | Faithfulness, context precision and relevance |
| O5 | Prevent AI-generated replies from being sent without human approval | Safety/integration tests |
| O6 | Evaluate different LLM configurations | Quality, latency, token usage and cost |
| O7 | Route classified cases to the appropriate team and available agent using configurable deterministic policies | Team-routing accuracy, assignment success rate, unassigned rate, workload distribution |

---

## Key Contributions

The main contributions of this project are:

- A **hybrid deterministic–agentic architecture** separating mechanical email
  operations from LLM reasoning.
- A **multi-mailbox context model** where each mailbox is an isolated business
  context (topics, custom fields, knowledge, connectors, AI behaviour), enforced
  at the data, retrieval, tool, and observability layers.
- A **staged Classifier → Drafter workflow** with independently configurable
  LLM settings.
- **Schema-validated classification** using Pydantic with fallback handling
  for non-standard local-model outputs.
- **AI topic + custom-field extraction** with server-side validation and
  partial-success handling; manual values are protected from AI overwrites.
- **Retrieval-Augmented Generation** grounded in mailbox-scoped, indexed
  knowledge with provenance tracking and injection-safe prompts.
- **MCP tool permissions** with default-deny enforcement and audit logging.
- A **safe multimodal attachment-processing pipeline** (planned) that separates
  deterministic file parsing from AI-based visual understanding and preserves
  case-level data isolation.
- A deterministic **Team & Agent Routing Engine** that transforms AI-derived
  topics, priorities, and structured fields into auditable work assignments
  without delegating personnel decisions directly to the LLM.
- A **Human-in-the-Loop approval workflow** that separates AI-generated drafts
  from external email actions.
- **Runtime-selectable local and hosted LLM providers.**
- **Encrypted persistence** of email and AI configuration.
- An **observability layer** (per-stage latency and token usage) and an
  **evaluation framework** for classification, structured-output reliability,
  RAG quality, model latency, and safety.

---

## System Architecture

```mermaid
flowchart TB
    subgraph UI["React Frontend (Human-in-the-Loop)"]
        Dashboard["Dashboard"]
        Inbox["Inbox & Review"]
        Cases["Cases & Drafts"]
        Mailboxes["Mailboxes<br/>(Topics / Fields / Knowledge / Connectors)"]
    end

    subgraph API["FastAPI Backend (backend/app)"]
        Routers["REST API Routers<br/>(emails / cases / mailboxes / knowledge / connectors / observability)"]
        Store[("CaseStore<br/>(SQLite)")]
    end

    subgraph Core["Core Engine (src/email_assistant)"]
        Fetcher["Email Fetcher<br/>(IMAP, per-mailbox)"]
        Crew["CrewAI Pipeline<br/>Classifier --> Drafter"]
        Routing["Routing Engine<br/>(rules → team → agent)"]
        RAG["Knowledge Retrieval<br/>(mailbox-scoped)"]
        MCP["MCP Runtime<br/>(permissions + audit)"]
        Sender["Email Sender<br/>(SMTP)"]
    end

    subgraph Data["Persistence"]
        EmailsDB[("data/emails.db")]
        SettingsDB[("data/settings.db<br/>(Fernet-encrypted secrets)")]
        KnowledgeDB[("data/knowledge.db<br/>(documents + chunks)")]
        ObsDB[("data/observability.db<br/>(runs + audit)")]
        ChromaDB[("Chroma (planned)<br/>(vector index)")]
    end

    UI -->|HTTP /api| Routers
    Routers --> Fetcher
    Routers --> Crew
    Routers --> Routing
    Routers --> RAG
    Routers --> MCP
    Routers --> Sender
    Routers --> Store
    Store --> EmailsDB
    SettingsDB -.->|LLM & mail config| Core
    RAG --> KnowledgeDB
    RAG -.->|"planned: vectors"| ChromaDB
    MCP --> ObsDB
    Fetcher -.-> IMAP["IMAP Server"]
    Sender -.-> SMTP["SMTP Server"]
```

### How Data Flows

1. **Sync** — the backend triggers the deterministic per-mailbox fetcher, which
   fetches all emails (read + unread, newest first) via IMAP and stores them as
   deduplicated tickets tagged with `mailbox_id`. Syncing without a selected
   mailbox syncs every configured mailbox.
2. **Attachment Processing (planned)** — case-specific attachments are safely
   parsed (PDF / DOCX / CSV / XLSX / image / ZIP) into normalized attachment
   context that feeds the classifier and field extraction.
3. **Process** — the staged pipeline runs mailbox-scoped: the Classifier uses
   the mailbox's topics and attachment context; knowledge is retrieved from the
   mailbox's own index; the Drafter grounds its reply in that context.
4. **Route** — the deterministic routing engine maps the case's classification
   and fields to a team (first-match routing rules), then the team's assignment
   strategy selects an eligible agent.
5. **Review & Send** — the human edits/approves the draft in the UI, then the
   backend sends it via SMTP using the enabled mail account.

### Storage Strategy: SQLite (source of truth) + Chroma (vector index)

The system separates transactional business state from semantic retrieval:

| Data | Store |
| --- | --- |
| Mailboxes / Emails / Cases / Topics / Fields / Teams / Agents / Routing | SQLite |
| AI & mail settings | SQLite |
| Observability / MCP audit | SQLite |
| Knowledge document metadata | SQLite |
| Chunk text + embedding vectors | Chroma (planned) |
| Semantic top-K retrieval | Chroma (planned) |

SQLite remains the authoritative transactional store; Chroma is a specialised
vector index for mailbox-scoped RAG. Embeddings are generated by
`OpenAICompatibleEmbeddingClient` (`core/openai_embeddings.py`) and provided directly to
Chroma — Chroma never calls an embedding provider. This keeps the existing
embedding compatibility layer, atomic reindex, and mailbox isolation intact
while replacing only the brute-force cosine loop with a nearest-neighbour index.

Planned isolation is **defense in depth**: one Chroma collection per mailbox
(e.g. `mailbox_1_support`, `mailbox_2_sales`) plus `mailbox_id` in chunk
metadata, and generation-based collections so a failed reindex never replaces
the active index.

---

## Why This Architecture?

### Why is email fetching deterministic?

Email retrieval through IMAP is a predictable software operation and does not
require semantic reasoning. Keeping it outside the LLM pipeline reduces
unnecessary model calls, latency, token usage, and non-deterministic behaviour.

### Why separate classification and drafting?

Classification and drafting have different objectives and evaluation criteria.
Separating them makes each stage independently observable, configurable,
testable, and replaceable.

### Why validate classification output?

Downstream application logic depends on predictable fields such as category,
priority and topic. Structured validation creates an explicit contract
between the probabilistic LLM and deterministic application code.

### Why Human-in-the-Loop?

Generating a draft and performing an external action are treated as different
trust boundaries. The AI may propose a response, but the user retains
authority over sending it.

The pipeline is therefore **hybrid deterministic–agentic**, not "everything is
AI":

```text
deterministic (IMAP fetch)
        ↓
AI reasoning (classify → draft)
        ↓
deterministic (SMTP send, after human gate)
```

---

## Multi-Mailbox Context Model

A mailbox is an **isolated business context**, not just an email account. Each
mailbox owns its own taxonomy and grounding, and `mailbox_id` is enforced as a
hard boundary at every layer:

```text
Mailbox
  ├── Topics        → constrain the classifier (resolve + validate)
  ├── Custom Fields → typed, validated, partial-success extraction
  ├── Knowledge     → mailbox-scoped indexing + retrieval (RAG)
  ├── Connectors    → default-deny tool permissions + audit
  ├── AI Behaviour  → per-stage model / temperature / instructions
  └── Routing Rules → map classified work to teams
                        ↓
                      Teams
                        ↓
                      Agents
```

This means a Support mailbox sees only Support topics, retrieves only Support
knowledge, and can only invoke tools permitted to Support — verified by
cross-mailbox isolation tests. Topics describe *what* an email is; teams
describe *who* is responsible; routing rules map the former to the latter
(rather than coupling topics directly to teams).

---

## Agentic Workflow

The email processing pipeline consists of a deterministic fetch layer followed
by a staged crew of two LLM-backed stages:

### Pre-Processing: Email Fetcher

Email retrieval is handled by `core/email_fetcher.py` — a plain Python module
that:

- connects to IMAP (folder and max-emails configurable per mailbox) and fetches
  all emails (read + unread), newest first;
- extracts structured metadata (sender, subject, body, timestamp) and inline
  attachments;
- passes cleaned data to the AI pipeline.

This keeps LLM calls focused purely on reasoning tasks.

### Attachment Processing (planned)

Attachments are treated as **case-specific untrusted evidence**, distinct from
the organisation-controlled knowledge base. A deterministic processing layer
detects MIME type, safely extracts content, and normalizes it into an
attachment context block that the classifier, field extraction, and drafter can
consume — without the model needing to know which parser produced it:

- **PDF / DOCX / XLSX / CSV / TXT / Markdown** → deterministic text/table extraction;
- **Images (PNG / JPG / WEBP)** → multimodal vision analysis via a configurable
  vision model (e.g. `xiaomi/mimo-v2.5`), separate from the reasoning model;
- **ZIP** → safe, bounded expansion with path-traversal / zip-bomb / size
  guards, then recursive per-child processing.

Attachment context is never merged into the shared knowledge base — it is scoped
to the originating email/case to prevent cross-case data leakage.

### Agent Roles

| Stage | Task | Goal | Tools |
| --- | --- | --- | --- |
| **Classifier** | `classify_email_task` | Determine category (question/incident/problem/task/spam), topic, priority, summary, and custom field values. | None (LLM reasoning) |
| **Drafter** | `draft_reply_task` | Generate context-aware reply drafts matching professional tone, grounded in retrieved knowledge. | RAG knowledge context |

Each stage gets its own LLM instance with **per-stage overrides** (temperature,
max tokens, even role/backstory) stored in the settings DB. Built-in defaults
live in `core/stage_seeds.py` (Python constants) and are **seeded once** into
the settings DB on first startup — the DB is the single source of truth.

### Structured Validation

The classification task uses **Pydantic Structured Outputs**, forcing the LLM
to return strictly validated JSON. A tolerant fallback parser
(`core/classification_parser.py`) recovers classifications from local models
(e.g. Qwen3) that emit Python-literal style output instead of clean JSON.

```python
from pydantic import BaseModel, Field


class EmailClassification(BaseModel):
    category: str = Field(description="question, incident, problem, task, or spam")
    topic: str = Field(description="What the email is about, e.g. refund, bug_report, password_reset")
    priority: str = Field(description="low, normal, high, or urgent")
    summary: str = Field(description="1-sentence summary of the email content")
    custom: dict = Field(description="Per-mailbox custom field values")
```

> **Note:** `status` is intentionally **not** part of the AI classification
> output — it is a workflow state managed by humans/automations, not something
> the LLM should decide.

### Email (Ticket) Data Model

Each incoming email is treated as a **ticket**:

| Field | Meaning | Values | Set by |
| --- | --- | --- | --- |
| **status** | Lifecycle stage of the ticket | `new` → `processed` → `sent` (workflow states in DB) | Workflow (not AI) |
| **priority** | How urgent it is | `low` / `normal` / `high` / `urgent` | AI suggests, human can override |
| **category** | What *kind* of request it is (stable, small set) | `question` / `incident` / `problem` / `task` / `spam` | AI (classifier) |
| **topic** | What the email is *about* (open-ended subject matter) | `refund`, `bug_report`, `password_reset`, `lead`, … | AI (classifier) |
| **summary** | 1-sentence summary of the email | text | AI (classifier) |
| **custom fields** | Extracted per-mailbox field values (Deadline, Action Required, …) | typed by field definition | AI (classifier) + validation |
| **topic_id / topic_raw** | Resolved topic (id + raw model output) | integer / text | Resolver |

### Classification Categories

The **category** field is kept small and stable:

| Category | Description | Auto-Reply Strategy |
| --- | --- | --- |
| **question** | A question or request for information | Draft reply grounded in mailbox knowledge (RAG) |
| **incident** | A single occurrence of a problem | Flag for human review, draft holding response |
| **problem** | A larger issue affecting many | Flag for human review |
| **task** | Assignable action item | Draft acceptance/tentative response |
| **spam** | Unsolicited or promotional | Flag, no reply |

---

## Safety & Threat Model

Incoming emails, retrieved knowledge documents, and tool results are treated as
**untrusted input**. Each mailbox is a hard security boundary.

### Main Risks

| Risk | Mitigation |
|---|---|
| Prompt injection in email content | Email text is treated as data, not trusted system instructions |
| Prompt injection in knowledge / tool results | Knowledge and tool output are wrapped as data, not instructions |
| Hallucinated classification | Structured schema validation |
| Hallucinated topic / field values | Topic resolution + server-side field validation (partial success) |
| Hallucinated reply content | Human review + RAG grounding with provenance |
| Excessive agent authority | AI cannot directly send email; MCP tools default-deny |
| Cross-mailbox data leakage | `mailbox_id` enforced across emails, cases, knowledge, connectors, runs |
| Credential disclosure | Secrets encrypted at rest, masked in API responses, redacted in audit |
| Runaway model execution | Token limits and request timeouts |
| External-model privacy | Provider is configurable; local models are supported |
| Incorrect AI-driven personnel assignment | LLM only supplies validated classification; deterministic routing rules select teams and agents |
| Assignment outside team membership | Backend membership validation before assignment |
| Agent overload | Capacity-aware assignment / unassigned team queue |
| Malicious attachments | MIME validation, size limits, no execution |
| ZIP bombs / path traversal | archive depth, extracted-size and safe-path controls |
| Attachment prompt injection | extracted attachment content treated as untrusted data |
| Cross-case attachment leakage | attachment context scoped to originating email/case |

The system follows a **least-authority** design: AI components may propose
actions, while external side effects remain under deterministic application and
human control.

---

## Evaluation Methodology

| Experiment | Baseline / Comparison | Metrics |
| --- | --- | --- |
| Email Classification | Different models / prompts | Accuracy, Macro-F1, Precision, Recall, Confusion Matrix |
| Structured Output | Free-form vs JSON prompt vs schema validation | Valid-output rate, parse failures |
| Draft Generation | LLM-only vs RAG | Correctness, relevance, completeness |
| RAG Retrieval | Different retrieval settings | Context Precision / Recall |
| RAG Generation | No-RAG vs RAG | Faithfulness, Answer Relevancy |
| Model Comparison | Local vs hosted LLM | Quality, latency, tokens, estimated cost |
| Case Routing | Topic/priority rules + assignment strategies | Routing accuracy, assignment success, unassigned rate |
| Workload Assignment | Round Robin vs Balanced | Distribution variance, max workload, unassigned rate |
| Attachment-assisted classification | Body-only vs body+attachment context | Accuracy, Macro-F1 |
| Attachment field extraction | Body-only vs body+attachment context | Field precision / recall / exact match |
| Archive processing safety | Malformed / oversized / malicious archives | Rejection rate, safe-extraction tests |
| Safety | Adversarial / prompt-injection test cases | Unsafe-action rate, approval-bypass rate |

RAG is introduced as an **experimental grounding mechanism** rather than merely
an additional feature. The planned comparison is:

```text
No RAG:  Email → LLM → Draft
   vs.
RAG:     Email → Retrieve company knowledge → LLM → Draft
```

Evaluation will use RAG-specific metrics such as `context_precision`,
`faithfulness`, and `answer_relevancy` (via Ragas).

---

## Preliminary / Final Results

The evaluation harness (`evaluation/`) runs real experiments against the frozen
test split using OpenRouter (`xiaomi/mimo-v2.5-pro` for classification and
drafting, `qwen/qwen3-embedding-8b` for retrieval). The results below are a
**preliminary sample** (20 test records per experiment) and are reproduced with
`scripts/run_evaluation.py`; raw per-record results are written under
`evaluation/results/` (git-ignored).

### Classification (Support mailbox)

| Metric | Value |
| --- | --- |
| Category accuracy | 0.00 |
| Topic accuracy | 0.90 |
| Topic resolution rate | 0.90 |

**Finding:** MiMo's out-of-box category output is not constrained to the
predefined enum (question/incident/problem/task/spam) — it emits free-form
labels such as "Technical Support" or "Customer Inquiry". This directly
motivates the structured-output validation + tolerant fallback parser in the
classification pipeline (RQ2). Topic extraction and resolution, by contrast,
are strong (0.90).

### Custom-field extraction (Support mailbox)

| Field | Accuracy |
| --- | --- |
| `order_id` | 1.00 |
| `severity` | 1.00 |
| `product` | 0.00 |
| Exact match (all fields) | 0.65 |

### Knowledge retrieval (Support mailbox)

| Metric | Value |
| --- | --- |
| Recall@1 | 1.00 |
| Recall@3 | 1.00 |
| Recall@5 | 1.00 |
| MRR | 0.75 |

### Drafting (RAG, Support mailbox)

| Metric | Value |
| --- | --- |
| Required-fact coverage | 0.00 (substring match) |
| Unsupported-claim rate | 0.00 |

The drafting coverage metric uses strict substring matching and does not yet
reward paraphrases; this is a known limitation of the current automated proxy
and will be replaced with a faithfulness rubric for the final report.

> These are preliminary sample results, not a full run. The full test split is
> 320 / 160 / 96 / 80 records for classification / field-extraction /
> retrieval / drafting respectively.

---

## Current Implementation Status

| Component | Status | Evaluation |
| --- | --- | --- |
| IMAP email retrieval (per-mailbox) | ✅ Implemented | Unit / integration tested |
| Multi-mailbox isolation | ✅ Implemented | Cross-mailbox isolation tested |
| Email classification | ✅ Implemented | 🔄 Evaluation pending |
| Structured output | ✅ Implemented | 🔄 Comparative evaluation pending |
| Topic resolution | ✅ Implemented | Unit tested |
| Custom fields (typed + validated) | ✅ Implemented | Unit tested |
| AI field extraction (partial success) | ✅ Implemented | Unit tested |
| Knowledge indexing / chunking | ✅ Implemented | Unit tested |
| Knowledge retrieval (mailbox-scoped) | ✅ Implemented | ✅ Preliminary benchmark (Recall@1/3/5 = 1.00) |
| RAG → Drafter | ✅ Implemented | 🔄 Evaluation pending |
| Human approval | ✅ Implemented | 🔄 Safety testing pending |
| SMTP delivery | ✅ Implemented | Integration tested |
| MCP permissions / audit | ✅ Implemented | Unit tested |
| Real MCP transport | ✅ Implemented | Live-verified against MTR MCP |
| Observability (runs / latency / tokens) | ✅ Implemented | Unit tested |
| Real semantic embedding provider | ✅ Implemented | OpenRouter `qwen/qwen3-embedding-8b` |
| Vector store | ✅ SQLite (brute-force) | 📋 Chroma planned (Sprint 10) |
| Attachment ingestion (inline) | ✅ Implemented | Unit tested |
| Attachment analysis (PDF/image/archive) | 📋 Planned | Sprint 11 (not yet implemented) |
| Teams / Agents / Routing | 📋 Planned | Sprint 9 (not yet implemented) |
| Long-term memory | 📋 Planned | Not evaluated |

---

## Quick Start

### Prerequisites

- Python ≥ 3.10 with [uv](https://docs.astral.sh/uv/)
- Node.js ≥ 20 (for the frontend)

### 1. Clone & Install

```bash
git clone <repo-url>
cd email_assistant

# Install Python runtime and test dependencies using uv (creates .venv automatically)
uv sync --group dev

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials — or configure everything (LLM + mail
accounts) at runtime through the Settings UI.

> **First startup auto-seeds**: a default AI config (from `.env`), stage
> prompt/parameter defaults (`core/stage_seeds.py`), and a default mailbox
> with study/work topics + custom fields (`core/mailbox_seeds.py`). The
> seeded mailbox's IMAP password comes from the `EMAIL_PASSWORD` env var.

### 3. Run

```bash
# Terminal 1 — backend API (http://localhost:8000)
uv run api

# Terminal 2 — frontend dev server (http://localhost:5173, proxies /api to :8000)
cd frontend && npm run dev
```

Open `http://localhost:5173`.

### Run Tests

```bash
uv run pytest            # 284 tests (core + backend API), no real API calls required
```

For the full configuration reference, API reference, and development workflow,
see [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) and [`docs/API.md`](docs/API.md).

---

## Project Structure

```plaintext
email_assistant/
├── .env.example                    # Environment variable template
├── .env                            # Active environment config (git-ignored)
├── pyproject.toml                  # Python dependencies (managed by uv)
├── pytest.ini
├── knowledge/
│   └── user_preference.txt         # Static knowledge base content
├── docs/
│   ├── API.md                      # API reference
│   └── DEVELOPMENT.md              # Configuration & development guide
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory, CORS, entry point (uv run api)
│   │   ├── schemas.py              # Pydantic request/response schemas
│   │   ├── store.py                # CaseStore wrapper over the email database
│   │   └── routers/
│   │       ├── emails.py           # Sync (IMAP fetch) + AI process endpoints
│   │       ├── cases.py            # Case listing, draft editing, field values, SMTP send
│   │       ├── mailboxes.py        # Mailboxes / topics / fields / knowledge / connectors
│   │       ├── knowledge.py        # Knowledge indexing + retrieval endpoints
│   │       ├── connectors.py       # MCP discovery / permissions / audit
│   │       ├── teams.py            # Teams / agents / membership (planned, Sprint 9)
│   │       ├── routing.py          # Routing rules (planned, Sprint 9)
│   │       ├── observability.py    # Processing runs, per-email traces + stats
│   │       ├── stats.py            # Dashboard statistics
│   │       └── settings.py         # AI configs / stage settings / mail accounts CRUD
│   └── tests/                      # FastAPI API tests (TestClient, temp DBs)
├── frontend/                       # React 19 + Vite + Tailwind 4 + shadcn/ui
│   ├── package.json                # npm scripts (dev / build / lint)
│   ├── vite.config.ts              # Dev server + /api proxy to backend
│   └── src/
│       ├── App.tsx                 # Route registration
│       ├── components/             # Sidebar, header, category/priority badges, case fields, empty state
│       ├── lib/                    # API client, shared types
│       └── pages/
│           ├── dashboard.tsx       # Stats + category chart + recent activity
│           ├── inbox.tsx           # Email list (master-detail), sync, AI process
│           ├── cases.tsx           # Cases table (Category + Topic columns) + merged Details panel
│           ├── mailboxes/          # Mailbox detail tabs (routing planned)
│           ├── teams/              # Teams + members (planned, Sprint 9)
│           ├── agents/             # Agents (planned, Sprint 9)
│           └── settings/           # ai-models.tsx, general.tsx (Classification / Drafting tabs)
├── tests/                          # Core unit tests (fetcher, database, parser, …)
└── src/
    └── email_assistant/
        ├── main.py                 # CLI entry points (run, train, test, replay)
        ├── models.py               # Pydantic models (EmailClassification)
        ├── service.py              # Multi-provider LLM configuration & validation
        ├── agents/
        │   └── crew.py             # EmailAssistant crew (Classifier & Drafter); stage config from settings DB
        ├── core/
        │   ├── email_fetcher.py    # Deterministic per-mailbox IMAP retrieval
        │   ├── email_sender.py     # SMTP sending (SSL / STARTTLS)
        │   ├── database.py         # SQLite email store (tickets, field values)
        │   ├── settings_store.py   # SQLite settings store (encrypted secrets)
        │   ├── mailbox_context.py  # MailboxRuntimeContext service
        │   ├── topics.py           # Topic resolution + validation
        │   ├── field_validation.py # Custom field value validation
        │   ├── extraction.py       # AI extraction client abstraction
        │   ├── extraction_service.py # Topic + field extraction (partial success)
        │   ├── chunking.py         # Knowledge chunking
        │   ├── embeddings.py       # Embedding client abstraction + compat
        │   ├── knowledge_store.py  # Knowledge documents + chunks (SQLite; Chroma planned)
        │   ├── vector_store.py     # VectorStore abstraction (SQLite now, Chroma planned)
        │   ├── knowledge_indexing.py # Indexing service (atomic replace)
        │   ├── knowledge_retrieval.py # Mailbox-scoped retrieval
        │   ├── attachments.py       # Attachment processors (PDF/image/archive) (planned)
        │   ├── attachments.py      # Attachment processors (PDF/image/archive) (planned, Sprint 11)
│   ├── rag.py              # Retrieval query builder + context format
        │   ├── mcp_runtime.py      # MCP client manager (transport abstraction)
        │   ├── tool_permissions.py # Default-deny tool permissions
        │   ├── observability.py    # Observer context manager
        │   ├── observability_store.py # Processing runs, traces + tool audit
        │   ├── migrations.py       # Legacy mailbox backfill
        │   ├── classification_parser.py  # Tolerant classifier output parser
        │   ├── stage_seeds.py      # Built-in stage defaults (classification + draft)
        │   ├── stage_defaults.py   # Stage defaults + DB override merging
        │   ├── mailbox_seeds.py    # Default mailbox seed (Gmail + study/work topics + fields)
        │   ├── openai_embeddings.py # OpenAI-compatible embedding client (multi-provider)
        │   ├── structured_llm.py   # OpenAI-compatible structured LLM client
        │   └── structured_classification.py # Structured classifier + business validation
        └── tools/
            └── custom_tool.py      # Placeholder (to be replaced with real tools)
```

---

## Limitations

- The five-category classification taxonomy may not generalise to all
  organisations.
- Draft quality depends on the selected LLM and prompt configuration.
- Out-of-box MiMo category output is not constrained to the enum; the
  classification pipeline relies on structured-output validation + fallback
  parsing to compensate (see Preliminary Results).
- The `hashing` embedding client is retained for offline tests; semantic
  retrieval requires `EMBEDDING_PROVIDER=openrouter` and an API key.
- Semantic retrieval currently uses a brute-force cosine scan over SQLite-stored
  vectors; a Chroma vector index is planned to scale to larger knowledge bases.
- Attachments are ingested (inline) but their *content* is not yet analyzed;
  PDF / image / archive understanding is planned.
- The MTR MCP connector is an external demo dependency; automated tests use a
  mock transport so CI does not depend on it.
- External LLM providers may introduce privacy and data-governance
  considerations.
- The current prototype does not provide enterprise-grade RBAC or multi-tenant
  isolation beyond the mailbox boundary.
- Human evaluation of generated drafts may contain subjective bias.

---

## Roadmap

- [x] Refactor to pure CrewAI structure (`crewai create crew`)
- [x] Multi-provider LLM configuration with timeout & token safety guards
- [x] Stage defaults as Python constants (`core/stage_seeds.py`) seeded into the settings DB (YAML config removed)
- [x] Pydantic structured output (`EmailClassification`) + tolerant fallback parser
- [x] Real IMAP email retrieval (`imap-tools`, per-mailbox)
- [x] FastAPI backend + React frontend
- [x] SQLite email store (content-hash dedupe, mailbox-scoped)
- [x] SQLite settings store — AI configs, stage settings, mail accounts
- [x] Encrypted secret storage (Fernet) for API keys & mail passwords
- [x] SMTP sending of approved drafts (SSL / STARTTLS)
- [x] Multi-mailbox context model (`mailbox_id` as data boundary)
- [x] Topics → classifier runtime (resolve + validate)
- [x] Custom fields → case runtime (typed validation, cross-mailbox reject)
- [x] AI topic + custom-field extraction (partial success, manual-value protection)
- [x] Knowledge indexing — chunking + embeddings + atomic replace
- [x] Knowledge retrieval — mailbox-scoped + retrieval test UI
- [x] Embedding compatibility safety (model change → reindex)
- [x] RAG → Drafter with provenance + injection-safe prompt
- [x] MCP runtime — discovery, permissions, audit (default-deny)
- [x] Observability — processing runs, latency, token usage
- [x] Multi-provider OpenAI-compatible semantic embedding client (`core/openai_embeddings.py`)
- [x] Real MCP transport (Streamable HTTP) — live-verified against MTR MCP
- [x] MiMo structured runtime contract (`xiaomi/mimo-v2.5-pro`)
- [x] Evaluation dataset v1 (950 records) + harness (metrics, runners)
- [ ] VectorStore abstraction + ChromaVectorStore (SQLite now)
- [ ] Per-mailbox / generation-based Chroma collections
- [ ] Atomic generation switching (failed reindex keeps active index)
- [ ] Retrieval + provenance integration over Chroma
- [ ] Migration / rebuild command
- [ ] Optional SQLite-vs-Chroma retrieval benchmark
- [ ] Teams / Agents / Membership (DB + CRUD)
- [ ] Case team ownership + assignee + assignment history
- [ ] Mailbox routing rules (first-match, configurable)
- [ ] Assignment engine (manual / round-robin / balanced)
- [ ] Teams / Agents / Routing UI
- [ ] Routing evaluation dataset + metrics
- [ ] Attachment ingestion + MIME/type detection
- [ ] PDF / DOCX / CSV / XLSX text extraction
- [ ] Image attachment analysis via configurable vision model
- [ ] Safe ZIP expansion + recursive attachment processing
- [ ] Attachment → classifier / field extraction context
- [ ] Attachment provenance in cases
- [ ] Attachment isolation + archive security tests
- [ ] Full test-split evaluation run (preliminary sample complete)
- [ ] CrewAI long-term memory via SQLite (`memory=True`)
- [ ] Final FYP Report

---

## References

1. [About the repository README file — GitHub Docs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes)
2. [Managing Email Overload in the Workplace — McMurtry, 2014](https://onlinelibrary.wiley.com/doi/10.1002/pfi.21424)
3. [CrewAI Documentation](https://docs.crewai.com/core-concepts/Agents)
4. [LLM01:2025 Prompt Injection — OWASP Gen AI Security Project](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
5. [AI Risk Management Framework: Generative AI Profile — NIST](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence)
6. [Context Precision — Ragas](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/)
7. [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks — Lewis et al., 2020](https://arxiv.org/abs/2005.11401)
8. [Organize team inboxes — Intercom](https://www.intercom.com/help/en/articles/197-organize-team-inboxes)
9. [About omnichannel routing — Zendesk](https://support.zendesk.com/hc/en-us/articles/4409149119514-About-omnichannel-routing)
10. [Organize Agents into Groups — Freshdesk](https://support.freshdesk.com/support/solutions/articles/37604-organize-agents-into-groups)
11. [Manage Collections — Chroma Docs](https://docs.trychroma.com/docs/collections/manage-collections)
12. [Metadata Filtering — Chroma Docs](https://docs.trychroma.com/docs/querying-collections/metadata-filtering)
13. [MiMo-V2.5 — OpenRouter](https://openrouter.ai/xiaomi/mimo-v2.5)
14. [MiMo-V2.5-Pro — OpenRouter](https://openrouter.ai/xiaomi/mimo-v2.5-pro)
