import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FolderOpen, MoreHorizontal } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { CategoryBadge } from '@/components/category-badge'
import { EmptyState } from '@/components/empty-state'
import { PageHeader } from '@/components/page-header'
import { StatusBadge } from '@/components/status-badge'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { fetchCases, fetchMailboxes } from '@/lib/api'
import type { Case } from '@/lib/types'

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

function caseStatus(item: Case): string {
  return item.sent_at !== null ? 'sent' : 'draft'
}

export default function Cases() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [mailboxFilter, setMailboxFilter] = useState<string>('all')
  const activeMailboxId = mailboxFilter === 'all' ? undefined : Number(mailboxFilter)

  const { data: cases = [] } = useQuery<Case[]>({
    queryKey: ['cases', activeMailboxId],
    queryFn: () => fetchCases(activeMailboxId),
  })
  const { data: mailboxes = [] } = useQuery({
    queryKey: ['mailboxes'],
    queryFn: fetchMailboxes,
  })

  const filtered = cases.filter((item) => {
    if (!query) return true
    return `${item.email.subject} ${item.email.sender} ${item.classification.topic}`
      .toLowerCase()
      .includes(query.toLowerCase())
  })

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6">
      <PageHeader
        title="Cases"
        description="Processed emails with AI-generated drafts and approvals."
        action={
          <div className="flex items-center gap-2">
            <Input
              className="w-64"
              placeholder="Search cases…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <Select value={mailboxFilter} onValueChange={(v) => setMailboxFilter(v ?? 'all')}>
              <SelectTrigger className="w-44">
                <SelectValue placeholder="All Mailboxes" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Mailboxes</SelectItem>
                {mailboxes.map((mailbox) => (
                  <SelectItem key={mailbox.id} value={String(mailbox.id)}>
                    {mailbox.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        }
      />

      {cases.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title="No cases yet"
          description="Go to Inbox and process an email to create a case."
        />
      ) : (
        <Card>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Case</TableHead>
                  <TableHead>Mailbox</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Topic</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((item) => (
                  <TableRow
                    key={item.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/cases/${item.id}`)}
                  >
                    <TableCell className="font-medium">
                      #{item.id.slice(0, 6).toUpperCase()}
                    </TableCell>
                    <TableCell className="max-w-40 truncate">
                      {item.email.subject}
                    </TableCell>
                    <TableCell>
                      <CategoryBadge category={item.classification.category} />
                    </TableCell>
                    <TableCell>
                      {item.classification.topic ? (
                        <Badge variant="outline">{item.classification.topic}</Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="capitalize">
                      {item.classification.priority}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={caseStatus(item)} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDate(item.created_at)}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          render={
                            <Button variant="ghost" size="icon-sm">
                              <MoreHorizontal />
                            </Button>
                          }
                        />
                        <DropdownMenuContent align="end" side="bottom">
                          <DropdownMenuItem
                            onClick={() => navigate(`/cases/${item.id}`)}
                          >
                            Open
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
