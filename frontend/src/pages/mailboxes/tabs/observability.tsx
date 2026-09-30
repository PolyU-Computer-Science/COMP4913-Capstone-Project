import { useQuery } from '@tanstack/react-query'
import { Activity, ChevronDown, Mail } from 'lucide-react'
import { useState } from 'react'

import { EmptyState } from '@/components/empty-state'
import { StatusBadge } from '@/components/status-badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { fetchProcessingStats, fetchProcessingTraces } from '@/lib/api'
import type { ProcessingRun, ProcessingTrace } from '@/lib/types'

function formatMs(ms: number | null): string {
  if (ms === null || ms === undefined) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}

function formatTokens(tokens: number | null): string {
  if (tokens === null || tokens === undefined) return '—'
  return tokens.toLocaleString()
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const STAGE_LABELS: Record<string, string> = {
  email_fetch: 'Fetch Mail',
  email_processing: 'AI Processing',
  knowledge_retrieval: 'Knowledge Retrieval',
  field_extraction: 'Field Extraction',
  classification: 'Classification',
  drafting: 'Drafting',
  mcp_tool: 'Tool Call',
}

const STAGE_ORDER = [
  'email_fetch',
  'knowledge_retrieval',
  'email_processing',
  'field_extraction',
  'classification',
  'drafting',
  'mcp_tool',
]

function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage
}

function stageRank(stage: string): number {
  const index = STAGE_ORDER.indexOf(stage)
  return index === -1 ? STAGE_ORDER.length : index
}

export function ObservabilityTab({ mailboxId }: { mailboxId: number }) {
  const { data: stats } = useQuery({
    queryKey: ['processing-stats', mailboxId],
    queryFn: () => fetchProcessingStats(mailboxId),
  })
  const { data: traces = [] } = useQuery({
    queryKey: ['processing-traces', mailboxId],
    queryFn: () => fetchProcessingTraces(mailboxId),
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Emails Processed" value={stats ? String(stats.processed) : '—'} />
        <Stat
          label="Success Rate"
          value={stats ? `${(stats.success_rate * 100).toFixed(1)}%` : '—'}
        />
        <Stat
          label="Avg Stage Latency"
          value={stats ? formatMs(stats.average_latency_ms) : '—'}
        />
        <Stat
          label="Total Tokens"
          value={stats ? formatTokens(stats.total_tokens) : '—'}
        />
      </div>

      {traces.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No activity yet"
          description="Sync and process emails to see their processing pipeline here."
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {traces.map((trace) => (
              <TraceCard key={trace.trace_id} trace={trace} />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function TraceCard({ trace }: { trace: ProcessingTrace }) {
  const [open, setOpen] = useState(false)
  const stages = [...trace.runs].sort(
    (a, b) => stageRank(a.stage) - stageRank(b.stage),
  )
  const failed = trace.status === 'failed'

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-lg border">
      <CollapsibleTrigger className="flex w-full items-center gap-3 p-3 text-left transition-colors hover:bg-muted/50">
        <Mail
          className={cn(
            'size-4 shrink-0',
            failed ? 'text-red-500' : 'text-muted-foreground',
          )}
        />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-sm font-medium">
            {trace.email_subject || '(unknown email)'}
          </span>
          <span className="text-xs text-muted-foreground">
            {formatTime(trace.started_at)} · {stages.length} step
            {stages.length === 1 ? '' : 's'} · {formatMs(trace.total_latency_ms)}
            {trace.total_tokens > 0 ? ` · ${formatTokens(trace.total_tokens)} tokens` : ''}
          </span>
        </div>
        <StatusBadge
          status={failed ? 'failed' : 'processed'}
          label={failed ? 'failed' : 'success'}
        />
        <ChevronDown
          className={cn(
            'size-4 shrink-0 text-muted-foreground transition-transform',
            open && 'rotate-180',
          )}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="flex flex-col gap-1 border-t px-3 py-2">
          {stages.map((run) => (
            <StageRow key={run.id} run={run} />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function StageRow({ run }: { run: ProcessingRun }) {
  return (
    <div className="flex items-center gap-3 rounded-md px-2 py-1.5 text-sm">
      <span className="w-40 shrink-0 text-muted-foreground">
        {stageLabel(run.stage)}
      </span>
      <StatusBadge
        status={run.status === 'success' ? 'processed' : 'failed'}
        label={run.status}
      />
      <span className="ml-auto text-xs text-muted-foreground">
        {formatMs(run.latency_ms)}
      </span>
      <span className="w-20 text-right text-xs text-muted-foreground">
        {run.total_tokens ? `${formatTokens(run.total_tokens)} tok` : ''}
      </span>
      <span className="w-40 truncate text-right text-xs text-muted-foreground">
        {run.model || ''}
      </span>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-0.5 pt-4">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-2xl font-bold">{value}</span>
      </CardContent>
    </Card>
  )
}
