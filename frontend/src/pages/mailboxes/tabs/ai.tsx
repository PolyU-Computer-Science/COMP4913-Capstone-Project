import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Info, Loader2 } from 'lucide-react'

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
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { fetchAIConfigs, updateMailbox } from '@/lib/api'
import type { Mailbox, MailboxIn } from '@/lib/types'
import { toast } from 'sonner'

export function AiTab({ mailbox }: { mailbox: Mailbox }) {
  const queryClient = useQueryClient()
  const { data: aiConfigs = [] } = useQuery({
    queryKey: ['ai-configs'],
    queryFn: fetchAIConfigs,
  })

  const [form, setForm] = useState({
    auto_process: mailbox.auto_process,
    generate_drafts: mailbox.generate_drafts,
    classifier_config_id: mailbox.classifier_config_id ?? null as number | null,
    classifier_temperature: mailbox.classifier_temperature?.toString() ?? '',
    classifier_max_tokens: mailbox.classifier_max_tokens?.toString() ?? '',
    drafter_config_id: mailbox.drafter_config_id ?? null as number | null,
    drafter_temperature: mailbox.drafter_temperature?.toString() ?? '',
    drafter_max_tokens: mailbox.drafter_max_tokens?.toString() ?? '',
    use_knowledge: mailbox.use_knowledge,
    instructions: mailbox.instructions,
  })

  const saveMutation = useMutation({
    mutationFn: (payload: MailboxIn) => updateMailbox(mailbox.id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailbox', mailbox.id] })
      toast.success('AI settings saved')
    },
    onError: () => toast.error('Failed to save AI settings'),
  })

  function buildPayload(): MailboxIn {
    return {
      ...mailbox,
      auto_process: form.auto_process,
      generate_drafts: form.generate_drafts,
      classifier_config_id: form.classifier_config_id,
      classifier_temperature: form.classifier_temperature
        ? Number(form.classifier_temperature)
        : null,
      classifier_max_tokens: form.classifier_max_tokens
        ? Number(form.classifier_max_tokens)
        : null,
      drafter_config_id: form.drafter_config_id,
      drafter_temperature: form.drafter_temperature
        ? Number(form.drafter_temperature)
        : null,
      drafter_max_tokens: form.drafter_max_tokens
        ? Number(form.drafter_max_tokens)
        : null,
      use_knowledge: form.use_knowledge,
      instructions: form.instructions,
      password: '',
    }
  }

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Processing</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ToggleRow
            label="Automatically process incoming mail"
            checked={form.auto_process}
            onChange={(v) => setForm((p) => ({ ...p, auto_process: v }))}
          />
          <ToggleRow
            label="Generate reply drafts"
            checked={form.generate_drafts}
            onChange={(v) => setForm((p) => ({ ...p, generate_drafts: v }))}
          />
          <div className="flex items-center justify-between rounded-lg border bg-muted/30 p-3">
            <div className="flex items-center gap-2">
              <span className="text-sm">Human approval before sending</span>
              <Info className="size-4 text-muted-foreground" />
            </div>
            <span className="text-xs font-medium text-muted-foreground">
              Required by system
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Classifier</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <ModelSelect
            label="Model"
            value={form.classifier_config_id}
            configs={aiConfigs}
            onChange={(id) =>
              setForm((p) => ({ ...p, classifier_config_id: id }))
            }
          />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Temperature">
              <Input
                type="number"
                step="0.1"
                value={form.classifier_temperature}
                onChange={(e) =>
                  setForm((p) => ({ ...p, classifier_temperature: e.target.value }))
                }
                placeholder="default"
              />
            </Field>
            <Field label="Max Tokens">
              <Input
                type="number"
                value={form.classifier_max_tokens}
                onChange={(e) =>
                  setForm((p) => ({ ...p, classifier_max_tokens: e.target.value }))
                }
                placeholder="default"
              />
            </Field>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Drafter</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <ModelSelect
            label="Model"
            value={form.drafter_config_id}
            configs={aiConfigs}
            onChange={(id) => setForm((p) => ({ ...p, drafter_config_id: id }))}
          />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Temperature">
              <Input
                type="number"
                step="0.1"
                value={form.drafter_temperature}
                onChange={(e) =>
                  setForm((p) => ({ ...p, drafter_temperature: e.target.value }))
                }
                placeholder="default"
              />
            </Field>
            <Field label="Max Tokens">
              <Input
                type="number"
                value={form.drafter_max_tokens}
                onChange={(e) =>
                  setForm((p) => ({ ...p, drafter_max_tokens: e.target.value }))
                }
                placeholder="default"
              />
            </Field>
          </div>
          <ToggleRow
            label="Use Knowledge"
            checked={form.use_knowledge}
            onChange={(v) => setForm((p) => ({ ...p, use_knowledge: v }))}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Instructions</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <Textarea
            rows={6}
            value={form.instructions}
            onChange={(e) =>
              setForm((p) => ({ ...p, instructions: e.target.value }))
            }
            placeholder="You are a customer-support email assistant. Use a professional and concise tone. Never invent refund eligibility."
          />
        </CardContent>
      </Card>

      <div className="flex justify-end">
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

function ModelSelect({
  label,
  value,
  configs,
  onChange,
}: {
  label: string
  value: number | null
  configs: { id: number; name: string; model: string }[]
  onChange: (id: number | null) => void
}) {
  const selected = configs.find((config) => config.id === value)

  return (
    <Field label={label}>
      <Select
        value={value === null ? undefined : String(value)}
        onValueChange={(v) => onChange(v ? Number(v) : null)}
      >
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Select a model…">
            {selected ? `${selected.name} · ${selected.model}` : undefined}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {configs.map((config) => (
            <SelectItem key={config.id} value={String(config.id)}>
              {config.name} · {config.model}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  )
}

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm">{label}</span>
      <Switch checked={checked} onCheckedChange={onChange} />
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
