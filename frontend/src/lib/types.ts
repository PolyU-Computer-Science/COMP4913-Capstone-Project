export interface EmailItem {
  id: string
  sender: string
  subject: string
  body: string
  timestamp: string
  html: string
  status: string
  mailbox_id: number | null
}

export interface Classification {
  category: string
  topic: string
  priority: string
  summary: string
  custom: Record<string, unknown>
}

export interface Case {
  id: string
  email: EmailItem
  classification: Classification
  draft: string
  created_at: string
  sent_at: string | null
  mailbox_id: number | null
  topic_id: number | null
  topic_raw: string
  knowledge_refs: { source_id: number; chunk_id: number; score: number }[]
}

export interface CaseField {
  field_id: number
  key: string
  name: string
  type: string
  required: boolean
  options: string[]
  value: unknown
}

export interface CategoryDatum {
  name: string
  value: number
}

export interface RecentActivity {
  email: string
  topic: string
  category: string
  priority: string
  status: string
  time: string
}

export interface Stats {
  total_emails: number
  processed: number
  pending: number
  success_rate: number
  category_distribution: CategoryDatum[]
  recent_activity: RecentActivity[]
}

export interface AIConfig {
  id: number
  name: string
  provider: string
  model: string
  base_url: string
  api_key: string
  has_api_key: boolean
  timeout: number
  max_tokens: number
  temperature: number
  enabled: boolean
}

export interface AIConfigIn {
  name: string
  provider: string
  model: string
  base_url: string
  api_key: string
  timeout: number
  max_tokens: number
  temperature: number
  enabled: boolean
}

export interface StageConfig {
  role: string
  goal: string
  backstory: string
  prompt: string
  max_tokens: number | null
  temperature: number | null
}

export interface StagesSettings {
  classification: StageConfig
  draft: StageConfig
}

export interface TestResult {
  ok: boolean
  message: string
}

export interface MailAccount {
  id: number
  name: string
  address: string
  imap_host: string
  imap_port: number
  smtp_host: string
  smtp_port: number
  password: string
  has_password: boolean
  max_emails: number
  enabled: boolean
}

export interface MailAccountIn {
  name: string
  address: string
  imap_host: string
  imap_port: number
  smtp_host: string
  smtp_port: number
  password: string
  max_emails: number
  enabled: boolean
}

export interface Mailbox {
  id: number
  name: string
  address: string
  purpose: string
  status: string
  imap_host: string
  imap_port: number
  imap_security: string
  imap_folder: string
  smtp_host: string
  smtp_port: number
  smtp_security: string
  has_password: boolean
  max_emails: number
  auto_process: boolean
  generate_drafts: boolean
  human_approval: boolean
  classifier_config_id: number | null
  drafter_config_id: number | null
  classifier_temperature: number | null
  classifier_max_tokens: number | null
  drafter_temperature: number | null
  drafter_max_tokens: number | null
  use_knowledge: boolean
  instructions: string
  is_system: boolean
}

export interface MailboxIn {
  name: string
  address: string
  purpose: string
  status: string
  imap_host: string
  imap_port: number
  imap_security: string
  imap_folder: string
  smtp_host: string
  smtp_port: number
  smtp_security: string
  password: string
  max_emails: number
  auto_process: boolean
  generate_drafts: boolean
  human_approval: boolean
  classifier_config_id: number | null
  drafter_config_id: number | null
  classifier_temperature: number | null
  classifier_max_tokens: number | null
  drafter_temperature: number | null
  drafter_max_tokens: number | null
  use_knowledge: boolean
  instructions: string
}

export interface Topic {
  id: number
  mailbox_id: number
  name: string
  description: string
  status: string
}

export interface TopicIn {
  name: string
  description: string
  status: string
}

export interface CustomField {
  id: number
  mailbox_id: number
  name: string
  type: string
  required: boolean
  options: string
  prompt: string
  status: string
}

export interface CustomFieldIn {
  name: string
  type: string
  required: boolean
  options: string
  prompt: string
  status: string
}

export interface KnowledgeSource {
  id: number
  name: string
  type: string
  status: string
  chunks: number
  content: string
}

export interface KnowledgeSourceIn {
  name: string
  type: string
  status: string
  chunks: number
  content: string
}

export interface RetrievalResult {
  source_id: number
  source_name: string
  chunk_id: number
  document_id: number
  chunk_index: number
  score: number
  content: string
  metadata: Record<string, unknown>
}

export interface RetrievalResponse {
  query: string
  embedding: { provider: string; model: string; dim: number }
  stats: {
    top_k: number
    chunks_considered: number
    stale_chunks_skipped: number
    returned_count: number
    source_count: number
    latency_ms: number
    max_score: number
    min_returned_score: number
  }
  results: RetrievalResult[]
}

export interface ToolDescriptor {
  connector_id: number
  name: string
  description: string
  risk_level: string
  enabled: boolean
  permission_level: string
}

export interface ProcessingRun {
  id: number
  trace_id: string | null
  mailbox_id: number | null
  email_id: string | null
  case_id: string | null
  stage: string
  status: string
  provider: string | null
  model: string | null
  started_at: string | null
  completed_at: string | null
  latency_ms: number | null
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  metadata: Record<string, unknown>
  error_type: string | null
  error_message: string | null
}

export interface ProcessingTrace {
  trace_id: string
  email_id: string | null
  email_subject: string | null
  status: string
  total_latency_ms: number
  total_tokens: number
  model: string | null
  started_at: string | null
  runs: ProcessingRun[]
}

export interface Connector {
  id: number
  name: string
  type: string
  server: string
  status: string
}

export interface MailboxConnector extends Connector {
  enabled: boolean
  allowed_tools: string
}

export interface ConnectorIn {
  name: string
  type: string
  server: string
  status: string
}
