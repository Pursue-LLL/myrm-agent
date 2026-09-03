'use client';

/**
 * [INPUT]
 * @/store/chat/types::CitedMemoryReference (POS: Chat state and SSE event type definitions)
 * @/services/memory/sharedContexts::listSharedContexts (POS: Frontend Shared Context API client)
 *
 * [OUTPUT]
 * MemoryCitationsButton: Opens the unified evidence sheet (memories + message sources).
 *
 * [POS]
 * Chat message provenance action. Merges cited memory refs and SSE sources (web/mcp/conversation history) in one sheet.
 */

import { useEffect, useMemo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { MessageSquare, Copy, Check } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/primitives/sheet';
import { cn } from '@/lib/utils/classnameUtils';
import { IconBrain, IconFolder } from '@/components/features/icons/PremiumIcons';
import { listSharedContexts, type SharedContext } from '@/services/memory/sharedContexts';
import { SourceItem } from '@/components/features/message-actions/SourcesButton';
import type { CitedMemoryReference, Source } from '@/store/chat/types';
import { resolveSourceClickUrl } from '@/store/chat/types/sources';
import { normalizeCitationTitle } from '@/lib/citations/preprocessCitationMarkers';

interface MemoryCitationsButtonProps {
  memoryIds?: string[];
  references?: CitedMemoryReference[];
  sources?: Source[];
  degraded?: boolean;
  citationAudit?: { totalMarkers: number; valid: number; unresolved: number };
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
    if (ref.id) {
      byId.set(ref.id, ref);
    }
  }
  for (const id of memoryIds ?? []) {
    if (!byId.has(id)) {
      byId.set(id, { id });
    }
  }
  return [...byId.values()];
};

export default function MemoryCitationsButton({
  memoryIds,
  references,
  sources,
  degraded,
  citationAudit,
}: MemoryCitationsButtonProps) {
  const t = useTranslations('memoryCitations');
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [contextsById, setContextsById] = useState<Map<string, SharedContext>>(new Map());
  const citationRefs = useMemo(() => uniqueReferences(memoryIds, references), [memoryIds, references]);
  const messageSources = useMemo(() => sources ?? [], [sources]);
  const evidenceCount = citationRefs.length + messageSources.length;
  const showUnresolvedBadge = (citationAudit?.unresolved ?? 0) > 0;
  const sharedContextIds = useMemo(
    () => citationRefs.map(sharedContextIdFromRef).filter((id): id is string => id !== null),
    [citationRefs],
  );

  const handleCopyMarkdown = useCallback(async () => {
    const lines: string[] = [];
    if (citationRefs.length > 0) {
      lines.push(`### ${t('sectionMemories')}`);
      citationRefs.forEach((ref, idx) => {
        const rawTitle = ref.content || ref.id;
        const cleanTitle = rawTitle.replace(/\s*\n+\s*/g, ' ').trim();
        lines.push(`- [${idx + 1}] ${cleanTitle}`);
      });
    }
    if (messageSources.length > 0) {
      if (lines.length > 0) {
        lines.push('');
      }
      lines.push(`### ${t('sectionSources')}`);
      messageSources.forEach((src) => {
        const url = resolveSourceClickUrl(src) || src.url || '';
        const rawTitle = src.title || src.filename || src.kb_name || '';
        const title = normalizeCitationTitle(rawTitle, url);
        const entry = url ? `[${title}](${url})` : title;
        lines.push(`- [${src.index}] ${entry}`);
      });
    }
    if (lines.length === 0) {
      return;
    }
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(lines.join('\n'));
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch {
      // ignore
    }
  }, [citationRefs, messageSources, t]);

  useEffect(() => {
    if (!open || sharedContextIds.length === 0) {
      return;
    }

    let cancelled = false;
    listSharedContexts()
      .then((response) => {
        if (cancelled) {
          return;
        }
        setContextsById(new Map(response.items.map((context) => [context.id, context])));
      })
      .catch(() => {
        if (!cancelled) {
          setContextsById(new Map());
        }
      });

    return () => {
      cancelled = true;
    };
  }, [open, sharedContextIds]);

  if (evidenceCount === 0) {
    if (!degraded) {
      return null;
    }
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border/30 text-xs',
          'bg-muted/50 text-muted-foreground',
        )}
        title={t('degradedNoticeTitle')}
      >
        <IconBrain className="h-3.5 w-3.5" />
        {t('degradedNotice')}
      </span>
    );
  }

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
          aria-label={t('buttonAria', { count: evidenceCount })}
        >
          <IconBrain className="h-4 w-4" />
          <span className="text-xs font-semibold whitespace-nowrap">{t('button', { count: evidenceCount })}</span>
          {showUnresolvedBadge && (
            <Badge
              variant="outline"
              className="border-amber-500/40 bg-amber-100/80 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
              title={t('unresolvedCitationsTitle', { count: citationAudit?.unresolved ?? 0 })}
            >
              {t('unresolvedCitations', { count: citationAudit?.unresolved ?? 0 })}
            </Badge>
          )}
        </button>
      </SheetTrigger>

      <SheetContent side="right" className="w-[400px] sm:w-[540px] overflow-y-auto">
        <SheetHeader>
          <div className="flex items-center justify-between gap-2">
            <SheetTitle className="flex items-center gap-2">
              <IconBrain className="h-5 w-5 text-amber-600 dark:text-amber-300" />
              {t('title')}
            </SheetTitle>
            <button
              type="button"
              onClick={handleCopyMarkdown}
              className={cn(
                'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
                'border border-border/40 hover:bg-muted text-muted-foreground hover:text-foreground',
                copied && 'text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
              )}
              title={t('copyMarkdown')}
              aria-label={t('copyMarkdown')}
            >
              {copied ? (
                <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
              <span>{copied ? t('copied') : t('copyMarkdown')}</span>
            </button>
          </div>
          <SheetDescription>{t('description')}</SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-6">
          {citationRefs.length > 0 && (
            <section className="space-y-3">
              {messageSources.length > 0 && (
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {t('sectionMemories')}
                </h3>
              )}
              {citationRefs.map((ref, index) => {
                const rawTitle = ref.content || ref.id;
                const cleanTitle = rawTitle.replace(/\s*\n+\s*/g, ' ').trim();
                return (
                  <div key={ref.id} className="relative group">
                    <MemoryCitationItem
                      index={index + 1}
                      reference={ref}
                      namespace={namespaceLabel(ref, contextsById)}
                      onNavigate={(chatId, messageId) => {
                        setOpen(false);
                        const url = messageId ? `/${chatId}?highlight=${messageId}` : `/${chatId}`;
                        router.push(url);
                      }}
                    />
                    <div className="absolute top-2.5 right-2.5 z-10">
                      <SingleCopyButton
                        text={cleanTitle}
                        title={t('copyMarkdown')}
                        ariaLabel={`${t('copyMarkdown')} [${index + 1}]`}
                      />
                    </div>
                  </div>
                );
              })}
            </section>
          )}

          {messageSources.length > 0 && (
            <section className="space-y-3">
              {citationRefs.length > 0 && (
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {t('sectionSources')}
                </h3>
              )}
              {messageSources.map((source, index) => {
                const url = resolveSourceClickUrl(source) || source.url || '';
                const rawTitle = source.title || source.filename || source.kb_name || '';
                const title = normalizeCitationTitle(rawTitle, url);
                const singleMarkdown = url ? `[${title}](${url})` : title;
                return (
                  <div key={`${source.index}-${index}`} className="relative group">
                    <SourceItem source={source} />
                    <div className="absolute top-2.5 right-2.5 z-10">
                      <SingleCopyButton
                        text={singleMarkdown}
                        title={t('copyMarkdown')}
                        ariaLabel={`${t('copyMarkdown')} [${source.index}]`}
                      />
                    </div>
                  </div>
                );
              })}
            </section>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function SingleCopyButton({
  text,
  title,
  ariaLabel,
}: {
  text: string;
  title: string;
  ariaLabel: string;
}) {
  const t = useTranslations('memoryCitations');
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(
    async (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!text) {
        return;
      }
      try {
        if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }
      } catch {
        // ignore
      }
    },
    [text],
  );

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={cn(
        'inline-flex items-center justify-center p-1 rounded-md transition-all',
        'opacity-0 group-hover:opacity-100 focus:opacity-100',
        'bg-background/80 hover:bg-muted border border-border/40 text-muted-foreground hover:text-foreground',
        copied && 'opacity-100 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
      )}
      title={copied ? t('copied') : title}
      aria-label={copied ? t('copied') : ariaLabel}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </button>
  );
}

function MemoryCitationItem({
  index,
  reference,
  namespace,
  onNavigate,
}: {
  index: number;
  reference: CitedMemoryReference;
  namespace: string | null;
  onNavigate: (chatId: string, messageId?: string) => void;
}) {
  const t = useTranslations('memoryCitations');
  const score = typeof reference.score === 'number' ? Math.round(reference.score * 100) : null;
  const memoryTypeLabel =
    reference.memoryType && MEMORY_TYPE_KEYS.has(reference.memoryType)
      ? t(`types.${reference.memoryType}`)
      : reference.memoryType;

  return (
    <article className="relative group rounded-2xl border border-border/60 bg-card p-4">
      <div className="flex items-center justify-between gap-2">
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
        <SingleCopyButton
          text={reference.content?.trim() || reference.id}
          title={t('copyMarkdown')}
          ariaLabel={`${t('copyMarkdown')} #${index}`}
        />
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

      {reference.sourceChatId && (
        <div className="mt-3 pt-3 border-t border-border/50">
          <button
            onClick={() => {
              if (reference.sourceChatId) {
                onNavigate(reference.sourceChatId, reference.sourceMessageId);
              }
            }}
            className="flex items-center gap-1.5 text-xs text-primary/70 hover:text-primary transition-colors"
          >
            <MessageSquare size={12} />
            <span>{t('viewSourceChat')}</span>
          </button>
        </div>
      )}
    </article>
  );
}
