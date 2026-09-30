import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Loader2, Plug } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { testMailbox, updateMailbox } from '@/lib/api'
import type { Mailbox, MailboxIn } from '@/lib/types'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

export function ConnectionTab({ mailbox }: { mailbox: Mailbox }) {
  const queryClient = useQueryClient()
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [form, setForm] = useState({
    imap_host: mailbox.imap_host,
    imap_port: String(mailbox.imap_port),
    imap_security: mailbox.imap_security,
    imap_folder: mailbox.imap_folder,
    smtp_host: mailbox.smtp_host,
    smtp_port: String(mailbox.smtp_port),
    smtp_security: mailbox.smtp_security,
    password: '',
    max_emails: String(mailbox.max_emails),
  })

  const saveMutation = useMutation({
    mutationFn: (payload: MailboxIn) => updateMailbox(mailbox.id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailbox', mailbox.id] })
      toast.success('Connection saved')
    },
    onError: () => toast.error('Failed to save connection'),
  })

  const testMutation = useMutation({
    mutationFn: () => testMailbox(mailbox.id),
    onSuccess: (result) => {
      if (result.ok) toast.success(result.message)
      else toast.error(result.message)
    },
    onError: () => toast.error('Test failed'),
  })

  function handleTest() {
    if (!mailbox.has_password && !form.password) {
      toast.error('Enter your password and save before testing the connection.')
      return
    }
    testMutation.mutate()
  }

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function buildPayload(): MailboxIn {
    return {
      ...mailbox,
      imap_host: form.imap_host,
      imap_port: Number(form.imap_port),
      imap_security: form.imap_security,
      imap_folder: form.imap_folder,
      smtp_host: form.smtp_host,
      smtp_port: Number(form.smtp_port),
      smtp_security: form.smtp_security,
      password: form.password,
      max_emails: Number(form.max_emails),
      classifier_config_id: mailbox.classifier_config_id,
      drafter_config_id: mailbox.drafter_config_id,
      classifier_temperature: mailbox.classifier_temperature,
      classifier_max_tokens: mailbox.classifier_max_tokens,
      drafter_temperature: mailbox.drafter_temperature,
      drafter_max_tokens: mailbox.drafter_max_tokens,
      use_knowledge: mailbox.use_knowledge,
      instructions: mailbox.instructions,
    }
  }

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Incoming Mail</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Field label="Email address">
            <Input value={mailbox.address} disabled />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="IMAP Server">
              <Input
                value={form.imap_host}
                onChange={(e) => set('imap_host', e.target.value)}
              />
            </Field>
            <Field label="Port">
              <Input
                type="number"
                value={form.imap_port}
                onChange={(e) => set('imap_port', e.target.value)}
              />
            </Field>
            <Field label="Security">
              <Select
                value={form.imap_security}
                onValueChange={(v) => set('imap_security', v ?? 'ssl')}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ssl">SSL/TLS</SelectItem>
                  <SelectItem value="starttls">STARTTLS</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Password">
              <Input
                type="password"
                value={form.password}
                onChange={(e) => set('password', e.target.value)}
                placeholder={mailbox.has_password ? '•••••• (leave blank to keep)' : 'app password'}
              />
            </Field>
          </div>

          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronDown className={cn('size-4 transition-transform', showAdvanced && 'rotate-180')} />
            Advanced settings
          </button>

          {showAdvanced && (
            <div className="flex flex-col gap-3 rounded-lg border p-3">
              <Field label="Source folder">
                <Input
                  value={form.imap_folder}
                  onChange={(e) => set('imap_folder', e.target.value)}
                  placeholder="INBOX"
                />
              </Field>
              <p className="text-xs text-muted-foreground">
                Choose which IMAP folder this mailbox should monitor. Most
                accounts should use Inbox.
              </p>
              <Field label="Max messages / sync">
                <Input
                  type="number"
                  value={form.max_emails}
                  onChange={(e) => set('max_emails', e.target.value)}
                />
              </Field>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Outgoing Mail</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3">
          <Field label="SMTP Server">
            <Input
              value={form.smtp_host}
              onChange={(e) => set('smtp_host', e.target.value)}
            />
          </Field>
          <Field label="Port">
            <Input
              type="number"
              value={form.smtp_port}
              onChange={(e) => set('smtp_port', e.target.value)}
            />
          </Field>
          <Field label="Security">
            <Select
              value={form.smtp_security}
              onValueChange={(v) => set('smtp_security', v ?? 'starttls')}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ssl">SSL/TLS</SelectItem>
                <SelectItem value="starttls">STARTTLS</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testMutation.isPending}
        >
          {testMutation.isPending ? (
            <Loader2 className="animate-spin" />
          ) : (
            <Plug />
          )}
          Test Connection
        </Button>
        <Button
          onClick={() => saveMutation.mutate(buildPayload())}
          disabled={saveMutation.isPending}
        >
          {saveMutation.isPending ? <Loader2 className="animate-spin" /> : null}
          Save Changes
        </Button>
      </div>
    </div>
  )
}

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  )
}
