import axios from 'axios'

import type {
  AIConfig,
  AIConfigIn,
  Case,
  CaseField,
  Connector,
  ConnectorIn,
  CustomField,
  CustomFieldIn,
  EmailItem,
  KnowledgeSource,
  KnowledgeSourceIn,
  MailAccount,
  MailAccountIn,
  Mailbox,
  MailboxConnector,
  MailboxIn,
  ProcessingRun,
  ProcessingTrace,
  RetrievalResponse,
  StagesSettings,
  Stats,
  TestResult,
  ToolDescriptor,
  Topic,
  TopicIn,
} from '@/lib/types'

const client = axios.create({ baseURL: '/api' })

interface EmailsResponse {
  emails: EmailItem[]
  count: number
}

interface SyncResponse {
  synced: number
  emails: EmailItem[]
  count: number
}

interface CasesResponse {
  cases: Case[]
  count: number
}

interface ProcessResponse {
  case: Case
}

export async function fetchEmails(mailboxId?: number): Promise<EmailItem[]> {
  const { data } = await client.get<EmailsResponse>('/emails', {
    params: mailboxId !== undefined ? { mailbox_id: mailboxId } : undefined,
  })
  return data.emails
}

export async function syncEmails(mailboxId?: number): Promise<{
  synced: number
  emails: EmailItem[]
}> {
  const { data } = await client.post<SyncResponse>(
    '/emails/sync',
    mailboxId !== undefined ? { mailbox_id: mailboxId } : undefined,
  )
  return { synced: data.synced, emails: data.emails }
}

export async function processEmail(id: string): Promise<Case> {
  const { data } = await client.post<ProcessResponse>(`/emails/${id}/process`)
  return data.case
}

export async function processAllEmails(mailboxId?: number): Promise<{
  queued: number
  processed: number
  failed: string[]
}> {
  const { data } = await client.post<{
    queued: number
    processed: number
    failed: string[]
  }>('/emails/process-all', undefined, {
    params: mailboxId !== undefined ? { mailbox_id: mailboxId } : undefined,
  })
  return data
}

export async function fetchCases(mailboxId?: number): Promise<Case[]> {
  const { data } = await client.get<CasesResponse>('/cases', {
    params: mailboxId !== undefined ? { mailbox_id: mailboxId } : undefined,
  })
  return data.cases
}

export async function updateCaseDraft(id: string, draft: string): Promise<Case> {
  const { data } = await client.patch<Case>(`/cases/${id}`, { draft })
  return data
}

export async function sendCase(id: string): Promise<Case> {
  const { data } = await client.post<Case>(`/cases/${id}/send`)
  return data
}

export async function fetchCaseFields(id: string): Promise<CaseField[]> {
  const { data } = await client.get<CaseField[]>(`/cases/${id}/fields`)
  return data
}

export async function updateCaseFields(
  id: string,
  values: Record<string, unknown>,
): Promise<CaseField[]> {
  const { data } = await client.put<CaseField[]>(`/cases/${id}/fields`, {
    values,
  })
  return data
}

export async function fetchStats(mailboxId?: number): Promise<Stats> {
  const { data } = await client.get<Stats>('/stats', {
    params: mailboxId !== undefined ? { mailbox_id: mailboxId } : undefined,
  })
  return data
}

export async function fetchAIConfigs(): Promise<AIConfig[]> {
  const { data } = await client.get<AIConfig[]>('/settings/ai')
  return data
}

export async function createAIConfig(payload: AIConfigIn): Promise<AIConfig> {
  const { data } = await client.post<AIConfig>('/settings/ai', payload)
  return data
}

export async function updateAIConfig(
  id: number,
  payload: AIConfigIn,
): Promise<AIConfig> {
  const { data } = await client.put<AIConfig>(`/settings/ai/${id}`, payload)
  return data
}

export async function deleteAIConfig(id: number): Promise<void> {
  await client.delete(`/settings/ai/${id}`)
}

export async function activateAIConfig(id: number): Promise<AIConfig> {
  const { data } = await client.post<AIConfig>(`/settings/ai/${id}/activate`)
  return data
}

export async function testAIConfig(payload: AIConfigIn): Promise<TestResult> {
  const { data } = await client.post<TestResult>('/settings/ai/test', payload)
  return data
}

export async function testSavedAIConfig(id: number): Promise<TestResult> {
  const { data } = await client.post<TestResult>(`/settings/ai/${id}/test`)
  return data
}

export async function fetchStages(): Promise<StagesSettings> {
  const { data } = await client.get<StagesSettings>('/settings/stages')
  return data
}

export async function saveStages(
  payload: StagesSettings,
): Promise<StagesSettings> {
  const { data } = await client.put<StagesSettings>('/settings/stages', payload)
  return data
}

export async function fetchStageMigrationWarnings(): Promise<string[]> {
  const { data } = await client.get<string[]>(
    '/settings/stages/migration-warnings',
  )
  return data
}

export async function fetchMailAccounts(): Promise<MailAccount[]> {
  const { data } = await client.get<MailAccount[]>('/settings/mail')
  return data
}

export async function createMailAccount(
  payload: MailAccountIn,
): Promise<MailAccount> {
  const { data } = await client.post<MailAccount>('/settings/mail', payload)
  return data
}

export async function updateMailAccount(
  id: number,
  payload: MailAccountIn,
): Promise<MailAccount> {
  const { data } = await client.put<MailAccount>(`/settings/mail/${id}`, payload)
  return data
}

export async function deleteMailAccount(id: number): Promise<void> {
  await client.delete(`/settings/mail/${id}`)
}

// ---- mailboxes ----

export async function fetchMailboxes(): Promise<Mailbox[]> {
  const { data } = await client.get<Mailbox[]>('/mailboxes')
  return data
}

export async function fetchMailbox(id: number): Promise<Mailbox> {
  const { data } = await client.get<Mailbox>(`/mailboxes/${id}`)
  return data
}

export async function createMailbox(payload: MailboxIn): Promise<Mailbox> {
  const { data } = await client.post<Mailbox>('/mailboxes', payload)
  return data
}

export async function updateMailbox(
  id: number,
  payload: MailboxIn,
): Promise<Mailbox> {
  const { data } = await client.put<Mailbox>(`/mailboxes/${id}`, payload)
  return data
}

export async function deleteMailbox(id: number): Promise<void> {
  await client.delete(`/mailboxes/${id}`)
}

export async function testMailbox(id: number): Promise<TestResult> {
  const { data } = await client.post<TestResult>(`/mailboxes/${id}/test`)
  return data
}

// ---- topics ----

export async function fetchTopics(mailboxId: number): Promise<Topic[]> {
  const { data } = await client.get<Topic[]>(`/mailboxes/${mailboxId}/topics`)
  return data
}

export async function createTopic(
  mailboxId: number,
  payload: TopicIn,
): Promise<Topic> {
  const { data } = await client.post<Topic>(
    `/mailboxes/${mailboxId}/topics`,
    payload,
  )
  return data
}

export async function updateTopic(id: number, payload: TopicIn): Promise<Topic> {
  const { data } = await client.put<Topic>(`/mailboxes/topics/${id}`, payload)
  return data
}

export async function deleteTopic(id: number): Promise<void> {
  await client.delete(`/mailboxes/topics/${id}`)
}

// ---- custom fields ----

export async function fetchCustomFields(
  mailboxId: number,
): Promise<CustomField[]> {
  const { data } = await client.get<CustomField[]>(
    `/mailboxes/${mailboxId}/fields`,
  )
  return data
}

export async function createCustomField(
  mailboxId: number,
  payload: CustomFieldIn,
): Promise<CustomField> {
  const { data } = await client.post<CustomField>(
    `/mailboxes/${mailboxId}/fields`,
    payload,
  )
  return data
}

export async function updateCustomField(
  id: number,
  payload: CustomFieldIn,
): Promise<CustomField> {
  const { data } = await client.put<CustomField>(
    `/mailboxes/fields/${id}`,
    payload,
  )
  return data
}

export async function deleteCustomField(id: number): Promise<void> {
  await client.delete(`/mailboxes/fields/${id}`)
}

// ---- knowledge sources ----

export async function fetchKnowledgeSources(): Promise<KnowledgeSource[]> {
  const { data } = await client.get<KnowledgeSource[]>('/mailboxes/knowledge')
  return data
}

export async function createKnowledgeSource(
  payload: KnowledgeSourceIn,
): Promise<KnowledgeSource> {
  const { data } = await client.post<KnowledgeSource>(
    '/mailboxes/knowledge',
    payload,
  )
  return data
}

export async function updateKnowledgeSource(
  id: number,
  payload: KnowledgeSourceIn,
): Promise<KnowledgeSource> {
  const { data } = await client.put<KnowledgeSource>(
    `/mailboxes/knowledge/${id}`,
    payload,
  )
  return data
}

export async function deleteKnowledgeSource(id: number): Promise<void> {
  await client.delete(`/mailboxes/knowledge/${id}`)
}

export async function fetchMailboxKnowledge(
  mailboxId: number,
): Promise<KnowledgeSource[]> {
  const { data } = await client.get<KnowledgeSource[]>(
    `/mailboxes/${mailboxId}/knowledge`,
  )
  return data
}

export async function assignKnowledge(
  mailboxId: number,
  sourceId: number,
): Promise<void> {
  await client.post(`/mailboxes/${mailboxId}/knowledge/${sourceId}`)
}

export async function unassignKnowledge(
  mailboxId: number,
  sourceId: number,
): Promise<void> {
  await client.delete(`/mailboxes/${mailboxId}/knowledge/${sourceId}`)
}

export async function indexKnowledgeSource(
  mailboxId: number,
  sourceId: number,
): Promise<{ status: string; chunks: number; skipped?: boolean; error?: string }> {
  const { data } = await client.post(
    `/mailboxes/${mailboxId}/knowledge/sources/${sourceId}/index`,
  )
  return data
}

export async function searchKnowledge(
  mailboxId: number,
  query: string,
  topK = 5,
): Promise<RetrievalResponse> {
  const { data } = await client.post<RetrievalResponse>(
    `/mailboxes/${mailboxId}/knowledge/search`,
    { query, top_k: topK },
  )
  return data
}

// ---- connectors ----

export async function fetchConnectors(): Promise<Connector[]> {
  const { data } = await client.get<Connector[]>('/mailboxes/connectors')
  return data
}

export async function createConnector(payload: ConnectorIn): Promise<Connector> {
  const { data } = await client.post<Connector>('/mailboxes/connectors', payload)
  return data
}

export async function updateConnector(
  id: number,
  payload: ConnectorIn,
): Promise<Connector> {
  const { data } = await client.put<Connector>(
    `/mailboxes/connectors/${id}`,
    payload,
  )
  return data
}

export async function deleteConnector(id: number): Promise<void> {
  await client.delete(`/mailboxes/connectors/${id}`)
}

export async function fetchMailboxConnectors(
  mailboxId: number,
): Promise<MailboxConnector[]> {
  const { data } = await client.get<MailboxConnector[]>(
    `/mailboxes/${mailboxId}/connectors`,
  )
  return data
}

export async function assignConnector(
  mailboxId: number,
  connectorId: number,
  payload: { enabled: boolean; allowed_tools: string },
): Promise<void> {
  await client.put(`/mailboxes/${mailboxId}/connectors/${connectorId}`, payload)
}

export async function unassignConnector(
  mailboxId: number,
  connectorId: number,
): Promise<void> {
  await client.delete(`/mailboxes/${mailboxId}/connectors/${connectorId}`)
}

export async function discoverConnectorTools(
  mailboxId: number,
  connectorId: number,
): Promise<ToolDescriptor[]> {
  const { data } = await client.post<ToolDescriptor[]>(
    `/mailboxes/${mailboxId}/connectors/${connectorId}/discover`,
  )
  return data
}

export async function updateConnectorPermissions(
  mailboxId: number,
  connectorId: number,
  permissions: { tool_name: string; enabled: boolean; permission_level: string }[],
): Promise<void> {
  await client.put(
    `/mailboxes/${mailboxId}/connectors/${connectorId}/permissions`,
    { permissions },
  )
}

export async function fetchProcessingRuns(
  mailboxId: number,
): Promise<ProcessingRun[]> {
  const { data } = await client.get<ProcessingRun[]>(
    `/mailboxes/${mailboxId}/processing-runs`,
  )
  return data
}

export async function fetchProcessingTraces(
  mailboxId: number,
): Promise<ProcessingTrace[]> {
  const { data } = await client.get<ProcessingTrace[]>(
    `/mailboxes/${mailboxId}/processing-traces`,
  )
  return data
}

export async function fetchProcessingStats(mailboxId: number): Promise<{
  processed: number
  success_rate: number
  average_latency_ms: number
  total_tokens: number
}> {
  const { data } = await client.get(`/mailboxes/${mailboxId}/processing-stats`)
  return data
}
