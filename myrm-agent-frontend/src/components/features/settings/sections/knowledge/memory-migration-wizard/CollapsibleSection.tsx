'use client';

import type { ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';

/**
 * Native `<details>` disclosure for the reference-only blocks of a long review
 * page: collapsing them keeps the decision summary in view, and the count badge
 * still tells the user how much is folded away.
 */
export function CollapsibleSection({
  title,
  badge,
  defaultOpen = false,
  className,
  children,
}: {
  title: string;
  badge?: string | number;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <details open={defaultOpen} className={cn('group rounded-xl border border-border/50 bg-secondary/20', className)}>
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
        <span className="min-w-0 flex-1">{title}</span>
        {badge !== undefined && (
          <Badge variant="secondary" className="text-[10px] tabular-nums">
            {badge}
          </Badge>
        )}
      </summary>
      <div className="space-y-2 px-4 pb-4">{children}</div>
    </details>
  );
}
