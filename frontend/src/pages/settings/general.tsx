import { useEffect, useState } from 'react'
import { Loader2, TriangleAlert } from 'lucide-react'

import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { fetchStageMigrationWarnings, fetchStages, saveStages } from '@/lib/api'
import type { StageConfig, StagesSettings } from '@/lib/types'
import { toast } from 'sonner'

interface StageForm {
  role: string
  goal: string
  backstory: string
  prompt: string
  max_tokens: string
  temperature: string
}

const EMPTY_STAGE: StageForm = {
  role: '',
  goal: '',
  backstory: '',
  prompt: '',
  max_tokens: '',
  temperature: '',
}

function toPayload(form: StageForm): StageConfig {
  return {
    role: form.role,
    goal: form.goal,
    backstory: form.backstory,
    prompt: form.prompt,
    max_tokens: form.max_tokens === '' ? null : Number(form.max_tokens),
    temperature: form.temperature === '' ? null : Number(form.temperature),
  }
}

function toForm(stage: StageConfig): StageForm {
  return {
    role: stage.role,
    goal: stage.goal,
    backstory: stage.backstory,
    prompt: stage.prompt,
    max_tokens: stage.max_tokens === null ? '' : String(stage.max_tokens),
    temperature: stage.temperature === null ? '' : String(stage.temperature),
  }
}

export default function GeneralPage() {
  const [classification, setClassification] = useState<StageForm>(EMPTY_STAGE)
  const [draft, setDraft] = useState<StageForm>(EMPTY_STAGE)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [migrationWarnings, setMigrationWarnings] = useState<string[]>([])

  useEffect(() => {
    fetchStages()
      .then((stages) => {
        setClassification(toForm(stages.classification))
        setDraft(toForm(stages.draft))
      })
      .catch(() => toast.error('Failed to load settings'))
      .finally(() => setLoading(false))
    fetchStageMigrationWarnings()
      .then(setMigrationWarnings)
      .catch(() => setMigrationWarnings([]))
  }, [])

  function setStage(
    stage: 'classification' | 'draft',
    key: keyof StageForm,
    value: string,
  ) {
    const setter = stage === 'classification' ? setClassification : setDraft
    setter((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSave() {
    setSaving(true)
    try {
      const payload: StagesSettings = {
        classification: toPayload(classification),
        draft: toPayload(draft),
      }
      await saveStages(payload)
      toast.success('Settings saved')
    } catch {
      toast.error('Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex max-w-3xl flex-col gap-4 p-4 md:p-6">
      <PageHeader
        title="General"
        description="Global prompt and parameter defaults for the classification and drafting stages. Per-topic guidance is configured in each mailbox's Topics tab."
        action={
          <Button onClick={handleSave} disabled={saving || loading}>
            {saving ? <Loader2 className="animate-spin" /> : null}
            Save Changes
          </Button>
        }
      />

      {migrationWarnings.map((warning) => (
        <div
          key={warning}
          className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400"
        >
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <span>{warning}</span>
        </div>
      ))}

      {loading ? (
        <div className="flex items-center gap-2 py-6 text-muted-foreground">
          <Loader2 className="animate-spin" /> Loading…
        </div>
      ) : (
        <Card>
          <CardContent className="pt-4">
            <Tabs defaultValue="classification">
              <TabsList>
                <TabsTrigger value="classification">Classification</TabsTrigger>
                <TabsTrigger value="draft">Drafting</TabsTrigger>
              </TabsList>

              <TabsContent value="classification" className="mt-4">
                <StageFormFields
                  form={classification}
                  onChange={(key, value) => setStage('classification', key, value)}
                  promptHint="Use {email_content} to inject the email content."
                />
              </TabsContent>

              <TabsContent value="draft" className="mt-4">
                <StageFormFields
                  form={draft}
                  onChange={(key, value) => setStage('draft', key, value)}
                  promptHint="Use {email_content} for the email and {knowledge_context} for retrieved knowledge."
                />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function StageFormFields({
  form,
  onChange,
  promptHint,
}: {
  form: StageForm
  onChange: (key: keyof StageForm, value: string) => void
  promptHint?: string
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="flex flex-col gap-1.5">
          <Label>Role</Label>
          <Input
            value={form.role}
            onChange={(e) => onChange('role', e.target.value)}
            placeholder="Email Classifier"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Goal</Label>
          <Input
            value={form.goal}
            onChange={(e) => onChange('goal', e.target.value)}
            placeholder="What this stage should achieve"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Backstory</Label>
          <Input
            value={form.backstory}
            onChange={(e) => onChange('backstory', e.target.value)}
            placeholder="Persona and experience"
          />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label>Task Prompt</Label>
        <Textarea
          value={form.prompt}
          onChange={(e) => onChange('prompt', e.target.value)}
          rows={10}
          className="font-mono text-sm"
        />
        {promptHint ? (
          <p className="text-xs text-muted-foreground">{promptHint}</p>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:max-w-xs">
        <div className="flex flex-col gap-1.5">
          <Label>Max Tokens</Label>
          <Input
            type="number"
            value={form.max_tokens}
            onChange={(e) => onChange('max_tokens', e.target.value)}
            placeholder="default"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Temperature</Label>
          <Input
            type="number"
            step="0.1"
            value={form.temperature}
            onChange={(e) => onChange('temperature', e.target.value)}
            placeholder="default"
          />
        </div>
      </div>
    </div>
  )
}
