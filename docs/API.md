# API Reference

Base URL: `http://localhost:8000/api`

## Health

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Health check |

## Emails

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/emails?mailbox_id=` | List stored emails (optionally mailbox-scoped) |
| POST | `/emails/sync` | Fetch emails (all, read + unread, newest first) via IMAP. With `{mailbox_id}`: sync that mailbox only; without: sync every configured mailbox |
| POST | `/emails/process-all?mailbox_id=` | Queue-process all pending emails |
| POST | `/emails/{id}/process` | Run the AI pipeline (classify + retrieve + draft) on an email |
| GET | `/emails/{id}/attachments/{cid}` | Serve an inline attachment |

## Cases

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/cases?mailbox_id=` | List processed cases (optionally mailbox-scoped) |
| PATCH | `/cases/{id}` | Edit a draft reply |
| POST | `/cases/{id}/send` | Send the approved draft via SMTP |
| GET | `/cases/{id}/fields` | List the case's mailbox custom fields + values |
| PUT | `/cases/{id}/fields` | Bulk-update field values (server-side validation) |

## Mailboxes

| Method | Path | Purpose |
| --- | --- | --- |
| GET/POST | `/mailboxes` | List / create mailboxes |
| GET/PUT/DELETE | `/mailboxes/{id}` | Get / update / delete a mailbox |
| POST | `/mailboxes/{id}/test` | Test the mailbox's IMAP connection (login + folder select + NOOP only — no emails are fetched) |

### Topics

| Method | Path | Purpose |
| --- | --- | --- |
| GET/POST | `/mailboxes/{id}/topics` | List / create topics |
| PUT/DELETE | `/mailboxes/topics/{topic_id}` | Update / delete a topic |

### Custom fields

| Method | Path | Purpose |
| --- | --- | --- |
| GET/POST | `/mailboxes/{id}/fields` | List / create custom fields |
| PUT/DELETE | `/mailboxes/fields/{field_id}` | Update / delete a custom field |

### Knowledge

| Method | Path | Purpose |
| --- | --- | --- |
| GET/POST | `/mailboxes/knowledge` | List / create global knowledge sources |
| PUT/DELETE | `/mailboxes/knowledge/{source_id}` | Update / delete a knowledge source |
| GET | `/mailboxes/{id}/knowledge` | List sources assigned to a mailbox |
| POST/DELETE | `/mailboxes/{id}/knowledge/{source_id}` | Assign / unassign a source |
| POST | `/mailboxes/{id}/knowledge/sources/{source_id}/index` | Index a source (chunk + embed) |
| GET | `/mailboxes/{id}/knowledge/sources/{source_id}/documents` | List indexed documents |
| POST | `/mailboxes/{id}/knowledge/search` | Mailbox-scoped retrieval (`{query, top_k}`) |

### Connectors (MCP)

| Method | Path | Purpose |
| --- | --- | --- |
| GET/POST | `/mailboxes/connectors` | List / create connectors |
| PUT/DELETE | `/mailboxes/connectors/{connector_id}` | Update / delete a connector |
| GET | `/mailboxes/{id}/connectors` | List connectors assigned to a mailbox |
| PUT/DELETE | `/mailboxes/{id}/connectors/{connector_id}` | Enable / disable for a mailbox |
| POST | `/mailboxes/{id}/connectors/{connector_id}/discover` | Discover + persist tools (live) |
| GET | `/mailboxes/{id}/connectors/{connector_id}/tools` | List discovered tools |
| PUT | `/mailboxes/{id}/connectors/{connector_id}/permissions` | Set tool permissions |
| POST | `/mailboxes/{id}/connectors/{connector_id}/execute` | Execute a tool through the permission gateway |

### Observability

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/mailboxes/{id}/processing-traces` | Recent per-email traces: runs grouped by `trace_id` with email subject, stages, status, latency, tokens |
| GET | `/mailboxes/{id}/processing-runs` | Raw processing runs (latency, tokens, status) |
| GET | `/mailboxes/{id}/processing-stats` | Aggregate stats (success rate, avg latency, tokens); counts **emails** (distinct traces), not runs |
| GET | `/mailboxes/{id}/tool-audit` | MCP tool invocation audit log |

## Settings

| Method | Path | Purpose |
| --- | --- | --- |
| GET/POST | `/settings/ai` | List / create AI configs |
| PUT/DELETE | `/settings/ai/{id}` | Update / delete an AI config |
| POST | `/settings/ai/{id}/activate` | Set the active AI config (single-active) |
| POST | `/settings/ai/test` · `/settings/ai/{id}/test` | LLM connection test |
| GET/PUT | `/settings/stages` | Per-stage settings (classification / draft) |
| GET/POST | `/settings/mail` | List / create mail accounts |
| PUT/DELETE | `/settings/mail/{id}` | Update / delete a mail account |

## Stats

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/stats?mailbox_id=` | Dashboard statistics (optionally mailbox-scoped) |
