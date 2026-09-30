import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const PRIORITY_STYLES: Record<string, string> = {
  urgent: 'bg-red-500/10 text-red-700 dark:text-red-400',
  high: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
  normal: 'bg-blue-500/10 text-blue-700 dark:text-blue-400',
  low: 'bg-slate-400/15 text-slate-600 dark:text-slate-400',
}

export function PriorityBadge({ priority }: { priority: string }) {
  const key = priority.toLowerCase()
  const className = PRIORITY_STYLES[key] ?? PRIORITY_STYLES.normal
  const label = priority.charAt(0).toUpperCase() + priority.slice(1)

  return <Badge className={cn('border-transparent capitalize', className)}>{label}</Badge>
}
