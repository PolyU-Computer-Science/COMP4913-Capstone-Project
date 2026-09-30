import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Loader2, Send } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { CategoryBadge } from '@/components/category-badge'
import { CaseFields } from '@/components/case-fields'
import { EmailBody } from '@/components/email-body'
import { StatusBadge } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { fetchCases, sendCase, updateCaseDraft } from '@/lib/api'
import type { Case } from '@/lib/types'
import { useIsMobile } from '@/hooks/use-mobile'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { toast } from 'sonner'

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState('')
  const [contextTab, setContextTab] = useState('details')
  const [showMobileContext, setShowMobileContext] = useState(false)

  const { data: cases = [] } = useQuery<Case[]>({
    queryKey: ['cases'],
    queryFn: () => fetchCases(),
  })

  const caseItem = cases.find((item) => item.id === caseId)

  // Sync the editor whenever the case data arrives or changes (e.g. the
  // cases query was still refetching the processed draft on first render).
  useEffect(() => {
    if (caseItem) setDraft(caseItem.draft)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseItem?.id, caseItem?.draft])

  const saveDraftMutation = useMutation({
    mutationFn: ({ id, draft }: { id: string; draft: string }) =>
      updateCaseDraft(id, draft),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cases'] })
      toast.success('Draft saved')
    },
    onError: () => toast.error('Failed to save draft'),
  })

  const sendMutation = useMutation({
    mutationFn: sendCase,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cases'] })
      queryClient.invalidateQueries({ queryKey: ['emails'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      toast.success('Reply sent!')
    },
    onError: (error) => {
      const detail = (error as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      toast.error(detail ?? 'Failed to send')
    },
  })

  if (!caseItem) {
    return (
      <div className="flex items-center gap-2 py-12 text-muted-foreground">
        <Loader2 className="animate-spin" />
        <p className="text-sm">Loading case…</p>
      </div>
    )
  }

  const sent = caseItem.sent_at !== null
  const contextPanel = <ContextPanel caseItem={caseItem} tab={contextTab} onTabChange={setContextTab} />

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 items-start justify-between gap-3 border-b px-4 py-3 md:px-6">
        <div className="flex min-w-0 flex-col gap-1">
          <button
            className="flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
            onClick={() => navigate('/cases')}
          >
            <ChevronLeft className="size-4" />
            Cases
          </button>
          <h1 className="truncate text-xl font-bold tracking-tight">
            {caseItem.email.subject}
          </h1>
          <span className="text-xs text-muted-foreground">
            #{caseItem.id.slice(0, 6).toUpperCase()}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <StatusBadge status={sent ? 'sent' : 'draft'} />
          <Badge variant="outline" className="capitalize">
            {caseItem.classification.priority}
          </Badge>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        {isMobile ? (
          <>
            <MainWorkspace
              caseItem={caseItem}
              draft={draft}
              sent={sent}
              isMobile
              onDraftChange={setDraft}
              onSave={() =>
                saveDraftMutation.mutate({ id: caseItem.id, draft })
              }
              onSend={() => sendMutation.mutate(caseItem.id)}
              savePending={saveDraftMutation.isPending}
              sendPending={sendMutation.isPending}
            />
            <Sheet open={showMobileContext} onOpenChange={setShowMobileContext}>
              <SheetContent side="right" className="sm:max-w-sm">
                <SheetHeader>
                  <SheetTitle>Case details</SheetTitle>
                </SheetHeader>
                {contextPanel}
              </SheetContent>
            </Sheet>
          </>
        ) : (
          <ResizablePanelGroup orientation="horizontal">
            <ResizablePanel defaultSize={70} minSize={55}>
              <MainWorkspace
                caseItem={caseItem}
                draft={draft}
                sent={sent}
                onDraftChange={setDraft}
                onSave={() =>
                  saveDraftMutation.mutate({ id: caseItem.id, draft })
                }
                onSend={() => sendMutation.mutate(caseItem.id)}
                savePending={saveDraftMutation.isPending}
                sendPending={sendMutation.isPending}
              />
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={30} minSize={25} className="min-w-[280px]">
              <div className="h-full pl-1">{contextPanel}</div>
            </ResizablePanel>
          </ResizablePanelGroup>
        )}
      </div>

      {isMobile && (
        <Button variant="outline" className="lg:hidden" onClick={() => setShowMobileContext(true)}>
          View case details
        </Button>
      )}
    </div>
  )
}

function ContextPanel({
  caseItem,
  tab,
  onTabChange,
}: {
  caseItem: Case
  tab: string
  onTabChange: (value: string) => void
}) {
  return (
    <div className="flex min-h-0 flex-col">
      <Tabs value={tab} onValueChange={(v) => onTabChange(v ?? 'details')}>
        <TabsList variant="line" className="w-full">
          <TabsTrigger value="details" className="flex-1">
            Details
          </TabsTrigger>
          <TabsTrigger value="ai" className="flex-1">
            AI Context
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-4 p-4">
          {tab === 'details' ? (
            <>
              <Section title="Case">
                <Row label="Status">
                  <StatusBadge status={caseItem.sent_at !== null ? 'sent' : 'draft'} />
                </Row>
                <Row label="Category">
                  <CategoryBadge category={caseItem.classification.category} />
                </Row>
                <Row label="Topic">
                  {caseItem.classification.topic ? (
                    <Badge variant="outline">{caseItem.classification.topic}</Badge>
                  ) : (
                    <span className="text-sm text-muted-foreground">—</span>
                  )}
                </Row>
                <Row label="Priority">
                  <span className="capitalize">{caseItem.classification.priority}</span>
                </Row>
                <Row label="Mailbox">
                  <span>{caseItem.mailbox_id ?? '—'}</span>
                </Row>
              </Section>

              <Separator />

              <Section title="Custom Fields">
                <CaseFields caseId={caseItem.id} />
              </Section>
            </>
          ) : (
            <>
              <Section title="Classification">
                <div className="flex flex-wrap items-center gap-2">
                  <CategoryBadge category={caseItem.classification.category} />
                  {caseItem.classification.topic && (
                    <Badge variant="outline">{caseItem.classification.topic}</Badge>
                  )}
                  {caseItem.topic_id === null && caseItem.topic_raw && (
                    <Badge variant="outline" className="text-muted-foreground">
                      Unclassified
                    </Badge>
                  )}
                </div>
                <Row label="Urgency">
                  <span>{caseItem.classification.urgency_score}/10</span>
                </Row>
              </Section>

              {caseItem.classification.summary && (
                <>
                  <Separator />
                  <Section title="Summary">
                    <p className="text-sm text-muted-foreground">
                      {caseItem.classification.summary}
                    </p>
                  </Section>
                </>
              )}

              {caseItem.knowledge_refs && caseItem.knowledge_refs.length > 0 && (
                <>
                  <Separator />
                  <Section title="Knowledge Used">
                    <div className="flex flex-col gap-2">
                      {caseItem.knowledge_refs.map((ref) => (
                        <Collapsible
                          key={`${ref.source_id}-${ref.chunk_id}`}
                          className="rounded-lg border"
                        >
                          <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-sm">
                            <span className="truncate">
                              Source #{ref.source_id}
                            </span>
                            <span className="flex items-center gap-1 text-xs text-muted-foreground">
                              {ref.score.toFixed(3)}
                              <ChevronRight className="size-3" />
                            </span>
                          </CollapsibleTrigger>
                          <CollapsibleContent className="border-t px-3 py-2 text-xs text-muted-foreground">
                            <div className="flex flex-col gap-1">
                              <span>Chunk ID: {ref.chunk_id}</span>
                              <span>Score: {ref.score.toFixed(4)}</span>
                            </div>
                          </CollapsibleContent>
                        </Collapsible>
                      ))}
                    </div>
                  </Section>
                </>
              )}
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {children}
    </div>
  )
}

function MainWorkspace({
  caseItem,
  draft,
  sent,
  isMobile = false,
  onDraftChange,
  onSave,
  onSend,
  savePending,
  sendPending,
}: {
  caseItem: Case
  draft: string
  sent: boolean
  isMobile?: boolean
  onDraftChange: (value: string) => void
  onSave: () => void
  onSend: () => void
  savePending: boolean
  sendPending: boolean
}) {
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b px-4 py-3 md:px-6">
        <span className="truncate font-medium">{caseItem.email.sender}</span>
        <span className="text-sm text-muted-foreground">
          {formatDate(caseItem.email.timestamp)}
        </span>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="p-4 md:p-6">
          <EmailBody
            body={caseItem.email.body}
            html={caseItem.email.html}
            emailId={caseItem.email.id}
          />
        </div>
      </ScrollArea>

      <div className="flex shrink-0 flex-col gap-3 border-t px-4 py-3 md:px-6">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-semibold">AI Draft</span>
          <span className="text-xs text-muted-foreground">
            Replying to {caseItem.email.sender} · Re: {caseItem.email.subject}
          </span>
        </div>
        <Textarea
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          rows={isMobile ? 8 : 10}
          className="w-full"
          disabled={sent}
        />
        <div className="flex items-center justify-end gap-2">
          {sent ? (
            <StatusBadge status="sent" label={`Sent ${formatDate(caseItem.sent_at!)}`} />
          ) : (
            <>
              <Button variant="outline" onClick={onSave} disabled={savePending}>
                {savePending ? <Loader2 className="animate-spin" /> : null}
                Save Draft
              </Button>
              <Button onClick={onSend} disabled={sendPending || draft.trim().length === 0}>
                {sendPending ? <Loader2 className="animate-spin" /> : <Send />}
                Approve &amp; Send
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      {children}
    </div>
  )
}
