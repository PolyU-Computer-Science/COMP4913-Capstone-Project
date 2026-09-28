import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2 } from 'lucide-react'

import { ConfirmDialog } from '@/components/confirm-dialog'
import { EmptyState } from '@/components/empty-state'
import { StatusBadge } from '@/components/status-badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  createCustomField,
  deleteCustomField,
  fetchCustomFields,
  updateCustomField,
} from '@/lib/api'
import type { CustomField, CustomFieldIn } from '@/lib/types'
import { toast } from 'sonner'

const SYSTEM_FIELDS = ['Status', 'Category', 'Priority', 'Urgency']

interface FormState {
  name: string
  type: string
  required: boolean
  options: string
  prompt: string
}

const EMPTY: FormState = {
  name: '',
  type: 'text',
  required: false,
  options: '',
  prompt: '',
}

export function FieldsTab({ mailboxId }: { mailboxId: number }) {
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY)
  const [toDelete, setToDelete] = useState<CustomField | null>(null)

  const { data: fields = [] } = useQuery({
    queryKey: ['mailbox-fields', mailboxId],
    queryFn: () => fetchCustomFields(mailboxId),
  })

  const saveMutation = useMutation({
    mutationFn: (payload: CustomFieldIn) =>
      editingId === null
        ? createCustomField(mailboxId, payload)
        : updateCustomField(editingId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailbox-fields', mailboxId] })
      setDialogOpen(false)
      toast.success('Field saved')
    },
    onError: () => toast.error('Failed to save field'),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteCustomField,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailbox-fields', mailboxId] })
      toast.success('Field deleted')
    },
    onError: () => toast.error('Failed to delete field'),
  })

  function openCreate() {
    setEditingId(null)
    setForm(EMPTY)
    setDialogOpen(true)
  }

  function openEdit(field: CustomField) {
    setEditingId(field.id)
    setForm({
      name: field.name,
      type: field.type,
      required: field.required,
      options: field.options,
      prompt: field.prompt,
    })
    setDialogOpen(true)
  }

  function payload(): CustomFieldIn {
    return { ...form, status: 'active' }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Custom fields are collected by the classifier for this mailbox.
        </p>
        <Button onClick={openCreate}>
          <Plus />
          Add Field
        </Button>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-6 pt-4">
          <div>
            <h3 className="mb-2 text-sm font-semibold">System Fields</h3>
            <div className="flex flex-wrap gap-2">
              {SYSTEM_FIELDS.map((name) => (
                <StatusBadge key={name} status="neutral" label={name} />
              ))}
            </div>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold">Custom Fields</h3>
            {fields.length === 0 ? (
              <EmptyState
                icon={Pencil}
                title="No custom fields"
                description="Add fields to capture extra data from this mailbox."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Required</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-20" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {fields.map((field) => (
                    <TableRow key={field.id}>
                      <TableCell className="font-medium">{field.name}</TableCell>
                      <TableCell className="capitalize">{field.type}</TableCell>
                      <TableCell>{field.required ? 'Yes' : 'No'}</TableCell>
                      <TableCell>
                        <StatusBadge status={field.status} />
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => openEdit(field)}
                          >
                            <Pencil />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => setToDelete(field)}
                          >
                            <Trash2 />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingId === null ? 'Add Field' : 'Edit Field'}
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="Customer ID"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Type</Label>
              <Select
                value={form.type}
                onValueChange={(v) => setForm((p) => ({ ...p, type: v ?? 'text' }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="text">Text</SelectItem>
                  <SelectItem value="select">Select</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {form.type === 'select' && (
              <div className="flex flex-col gap-1.5">
                <Label>Options</Label>
                <Input
                  value={form.options}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, options: e.target.value }))
                  }
                  placeholder="Option A, Option B"
                />
              </div>
            )}
            <div className="flex flex-col gap-1.5">
              <Label>Prompt Hint</Label>
              <Textarea
                rows={3}
                value={form.prompt}
                onChange={(e) => setForm((p) => ({ ...p, prompt: e.target.value }))}
                placeholder="Extraction guidance, e.g. the order number found in the email body, format ORD-12345."
              />
              <p className="text-xs text-muted-foreground">
                Injected into the AI prompt when extracting this field.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={form.required}
                onCheckedChange={(v) => setForm((p) => ({ ...p, required: v }))}
              />
              <Label>Required</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => saveMutation.mutate(payload())}
              disabled={saveMutation.isPending || !form.name.trim()}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={toDelete !== null}
        onOpenChange={(open) => {
          if (!open) setToDelete(null)
        }}
        title={`Delete ${toDelete?.name ?? 'field'}?`}
        confirmLabel="Delete"
        destructive
        onConfirm={() => {
          if (toDelete) deleteMutation.mutate(toDelete.id)
        }}
      />
    </div>
  )
}
