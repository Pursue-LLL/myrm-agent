'use client';

/**
 * [INPUT]
 * @/store/chat/types::CitedMemoryReference (POS: Chat state and SSE event type definitions)
 * @/services/memorySharedContexts::listSharedContexts (POS: Frontend Shared Context API client)
 *
 * [OUTPUT]
 * MemoryCitationsButton: Opens the memory citation sheet for one assistant message.
 *
 * [POS]
 * Chat message memory citation action. It turns cited memory IDs/refs into a readable provenance sheet.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/components/ui/badge';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { cn } from '@/lib/utils/classnameUtils';
import { IconBrain, IconFolder } from '@/components/ui/icons/PremiumIcons';
import { listSharedContexts, type SharedContext } from '@/services/memorySharedContexts';
import type { CitedMemoryReference } from '@/store/chat/types';

interface MemoryCitationsButtonProps {
  memoryIds?: string[];
  references?: CitedMemoryReference[];
}

const shortId = (id: string): string => (id.length > 8 ? `${id.slice(0, 8)}...` : id);

const MEMORY_TYPE_KEYS = new Set([
  'semantic',
  'episodic',
  'profile',
  'procedural',
  'conversation',
  'claim',
  'task_digest',
]);

const sharedContextIdFromRef = (ref: CitedMemoryReference): string | null => {
  const namespaces = [ref.primaryNamespace, ...(ref.namespaces ?? [])].filter(
    (namespace): namespace is string => typeof namespace === 'string' && namespace.length > 0,
  );
  const shared = namespaces.find((namespace) => namespace.startsWith('shared:'));
  return shared ? shared.slice('shared:'.length) : null;
};

const namespaceLabel = (ref: CitedMemoryReference, contextsById: Map<string, SharedContext>): string | null => {
  const sharedContextId = sharedContextIdFromRef(ref);
  if (sharedContextId) {
    return contextsById.get(sharedContextId)?.name ?? `shared:${shortId(sharedContextId)}`;
  }
  return ref.primaryNamespace ?? ref.namespaces?.[0] ?? null;
};

const uniqueReferences = (
  memoryIds: string[] | undefined,
  references: CitedMemoryReference[] | undefined,
): CitedMemoryReference[] => {
  const byId = new Map<string, CitedMemoryReference>();
  for (const ref of references ?? []) {
    if (ref.id) byId.set(ref.id, ref);
  }
  for (const id of memoryIds ?? []) {
    if (!byId.has(id)) byId.set(id, { id });
  }
  return [...byId.values()];
};

export default function MemoryCitationsButton({ memoryIds, references }: MemoryCitationsButtonProps) {
  const t = useTranslations('memoryCitations');
  const [open, setOpen] = useState(false);
  const [contextsById, setContextsById] = useState<Map<string, SharedContext>>(new Map());
  const citationRefs = useMemo(() => uniqueReferences(memoryIds, references), [memoryIds, references]);
  const sharedContextIds = useMemo(
    () => citationRefs.map(sharedContextIdFromRef).filter((id): id is string => id !== null),
    [citationRefs],
  );

  useEffect(() => {
    if (!open || sharedContextIds.length === 0) return;

    let cancelled = false;
    listSharedContexts()
      .then((response) => {
        if (cancelled) return;
        setContextsById(new Map(response.items.map((context) => [context.id, context])));
      })
      .catch(() => {
        if (!cancelled) setContextsById(new Map());
      });

    return () => {
      cancelled = true;
    };
  }, [open, sharedContextIds]);

  if (citationRefs.length === 0) return null;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          className={cn(
            'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border/30',
            'bg-amber-50/70 text-amber-700 hover:bg-amber-100',
            'dark:bg-amber-950/25 dark:text-amber-300 dark:hover:bg-amber-900/30',
            'active:scale-95 transition-all duration-200',
          )}
          aria-label={t('buttonAria', { count: citationRefs.length })}
        >
          <IconBrain className="h-4 w-4" />
          <span className="text-xs font-semibold whitespace-nowrap">{t('button', { count: citationRefs.length })}</span>
        </button>
      </SheetTrigger>

      <SheetContent side="right" className="w-[400px] sm:w-[540px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <IconBrain className="h-5 w-5 text-amber-600 dark:text-amber-300" />
            {t('title')}
          </SheetTitle>
          <SheetDescription>{t('description')}</SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-3">
          {citationRefs.map((ref, index) => (
            <MemoryCitationItem
              key={ref.id}
              index={index + 1}
              reference={ref}
              namespace={namespaceLabel(ref, contextsById)}
            />
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function MemoryCitationItem({
  index,
  reference,
  namespace,
}: {
  index: number;
  reference: CitedMemoryReference;
  namespace: string | null;
}) {
  const t = useTranslations('memoryCitations');
  const score = typeof reference.score === 'number' ? Math.round(reference.score * 100) : null;
  const memoryTypeLabel =
    reference.memoryType && MEMORY_TYPE_KEYS.has(reference.memoryType)
      ? t(`types.${reference.memoryType}`)
      : reference.memoryType;

  return (
    <article className="rounded-2xl border border-border/60 bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="font-mono">
          #{index}
        </Badge>
        {memoryTypeLabel && <Badge variant="outline">{memoryTypeLabel}</Badge>}
        {score !== null && (
          <Badge variant="outline" className="text-emerald-600 dark:text-emerald-300">
            {t('score', { score })}
          </Badge>
        )}
      </div>

      <p className="mt-3 text-sm leading-relaxed text-foreground">
        {reference.content?.trim() || t('unavailableContent')}
      </p>

      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        {namespace && (
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
            <IconFolder className="h-3 w-3" />
            {namespace}
          </span>
        )}
        <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1 font-mono">
          <span className="text-[11px] font-semibold leading-none">#</span>
          {shortId(reference.id)}
        </span>
      </div>
    </article>
  );
}
