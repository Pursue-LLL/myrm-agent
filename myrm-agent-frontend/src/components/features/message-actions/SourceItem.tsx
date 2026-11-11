'use client';

/**
 * [INPUT]
 * @/store/chat/types::Source (POS: Chat state and SSE event type definitions)
 * @/lib/citations/sourceName::sourceKind, sourceName (POS: which kind a source is and what it is called)
 * @/services/wiki/sectionLabels::wikiSectionLabeler (POS: how a wiki section is worded)
 * @/services/chat::deleteChat, updateChatRecallExclusion (POS: Chat API client)
 * @/hooks/agent/useAgentName::useAgentName (POS: Resolve agent_id to human-friendly name)
 *
 * [OUTPUT]
 * SourceItem: One source as a card: a web page, a wiki hit, an MCP skill or a past conversation.
 *
 * [POS]
 * Source row component. Renders the provenance of one source and lets users navigate to, exclude or delete a
 * conversation-history source without mixing it into memory feedback.
 */

/* eslint-disable @next/next/no-img-element */
import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils/classnameUtils';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { deleteChat, updateChatRecallExclusion } from '@/services/chat';
import { toast } from '@/hooks/shared/useToast';
import type { Source } from '@/store/chat/types';
import { resolveSourceClickUrl } from '@/store/chat/types/sources';
import { sourceKind, sourceName } from '@/lib/citations/sourceName';
import { wikiSectionLabeler } from '@/services/wiki/sectionLabels';
import { buildWikiAssetUrl } from '@/services/wikiService';
import { Database, ExternalLink, EyeOff, Globe, Plug, Trash2, BookOpen } from 'lucide-react';
import { useAgentName } from '@/hooks/agent/useAgentName';

/**
 * 单个来源项组件
 */
export function SourceItem({ source }: { source: Source }) {
  const t = useTranslations('sources');
  const tWiki = useTranslations('settings.wiki.concepts');
  const tSections = useTranslations('MessageSources');
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const kind = sourceKind(source);
  const name = sourceName(source, wikiSectionLabeler(tSections));
  const agentName = useAgentName(kind === 'conversation' ? source.agent_id : null);

  if (kind === 'knowledge') {
    const title = name ?? 'LLM-Wiki';
    const description = source.snippet || source.summary;
    const assetThumbnailUrl =
      source.hit_kind === 'asset' && source.asset_filename
        ? buildWikiAssetUrl(source.asset_filename, source.agent_id)
        : null;

    return (
      <div className={cn('p-3 rounded-lg bg-accent hover:bg-muted transition-colors')}>
        <div className="flex items-start gap-3">
          {assetThumbnailUrl ? (
            <img
              src={assetThumbnailUrl}
              alt=""
              className="h-12 w-12 shrink-0 rounded-md border border-border/60 object-cover bg-muted"
            />
          ) : (
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300 flex items-center justify-center">
              <BookOpen className="w-4 h-4" />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono bg-primary/10 text-primary px-1.5 py-0.5 rounded">
                [{source.index}]
              </span>
              <span className="text-sm font-medium truncate flex-1">{title}</span>
              {source.kb_name && (
                <span className="text-[11px] font-medium px-1.5 py-0.5 rounded-full bg-violet-500/10 text-violet-700 dark:text-violet-300 border border-violet-500/20 shrink-0">
                  {source.kb_name}
                </span>
              )}
            </div>
            {description && <p className="text-xs text-muted-foreground mt-2 line-clamp-3">{description}</p>}
            {(source.snapshot_status || source.claim_confidence != null || source.superseded_from_uri) && (
              <div className="mt-2 space-y-1">
                {source.snapshot_status === 'verified' && (
                  <p className="text-[11px] text-emerald-700 dark:text-emerald-300">
                    {tWiki('evidenceSnapshotVerified')}
                  </p>
                )}
                {source.snapshot_status === 'stale' && (
                  <p className="text-[11px] text-amber-700 dark:text-amber-300">{tWiki('evidenceSnapshotStale')}</p>
                )}
                {source.snapshot_status === 'missing' && source.path && (
                  <p className="text-[11px] text-muted-foreground">{tWiki('evidenceSnapshotMissing')}</p>
                )}
                {source.claim_confidence != null && (
                  <p className="text-[11px] text-muted-foreground">
                    {tWiki('evidenceClaimConfidence', { value: Math.round(source.claim_confidence * 100) })}
                  </p>
                )}
                {source.superseded_from_uri && (
                  <p className="text-[11px] text-amber-700/90 dark:text-amber-300/90 font-mono break-all">
                    {tWiki('evidenceSupersededFrom', { uri: source.superseded_from_uri })}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (kind === 'conversation') {
    const chatId = source.conversation_id;
    const jumpToChat = () => {
      if (!chatId) {
        return;
      }
      const highlight = source.message_id ? `?highlight=${encodeURIComponent(source.message_id)}` : '';
      router.push(`/${chatId}${highlight}`);
    };
    const handleExclude = async () => {
      if (!chatId) {
        return;
      }
      setBusy(true);
      try {
        await updateChatRecallExclusion(chatId, true);
        toast({ title: t('conversation_excluded') });
      } catch (err: unknown) {
        const description = err instanceof Error ? err.message : t('operation_failed');
        toast({ title: t('operation_failed'), description, variant: 'destructive' });
      } finally {
        setBusy(false);
      }
    };
    const handleDelete = async () => {
      if (!chatId) {
        return;
      }
      setBusy(true);
      try {
        await deleteChat(chatId);
        toast({ title: t('conversation_deleted') });
      } catch (err: unknown) {
        const description = err instanceof Error ? err.message : t('operation_failed');
        toast({ title: t('operation_failed'), description, variant: 'destructive' });
        throw err;
      } finally {
        setBusy(false);
      }
    };

    const sourceDescription = source.summary || source.snippet;

    return (
      <div className={cn('p-3 rounded-lg bg-accent hover:bg-muted transition-colors')}>
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center">
            <Database className="w-4 h-4" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono bg-primary/10 text-primary px-1.5 py-0.5 rounded">
                [{source.index}]
              </span>
              <button
                type="button"
                className="text-sm font-medium truncate flex-1 text-left hover:text-primary"
                onClick={jumpToChat}
                disabled={!chatId}
              >
                {name ?? t('conversation_source')}
              </button>
              {chatId && <ExternalLink className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />}
            </div>

            <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-xs text-muted-foreground">
              {source.surface && <span>{source.surface}</span>}
              {agentName && <span>{agentName}</span>}
              {source.updated_at && <span>{formatSourceDate(source.updated_at)}</span>}
              {typeof source.score === 'number' && (
                <span>
                  {t('relevance_score')}: {Math.round(source.score * 100)}%
                </span>
              )}
            </div>

            {sourceDescription && (
              <p className="text-xs text-muted-foreground mt-2 line-clamp-3">{sourceDescription}</p>
            )}

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-full border border-border/50 px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-background"
                onClick={handleExclude}
                disabled={!chatId || busy}
              >
                <EyeOff className="w-3.5 h-3.5" />
                {t('exclude_conversation')}
              </button>
              <ConfirmDialog
                trigger={
                  <button
                    type="button"
                    className="inline-flex items-center gap-1.5 rounded-full border border-destructive/30 px-2 py-1 text-xs text-destructive-text hover:bg-destructive/10"
                    disabled={!chatId || busy}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    {t('delete_conversation')}
                  </button>
                }
                title={t('delete_conversation')}
                description={t('delete_conversation_desc')}
                confirmText={t('delete_confirm')}
                cancelText={t('delete_cancel')}
                loadingText={t('delete_loading')}
                variant="destructive"
                onConfirm={handleDelete}
              />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (kind === 'mcp') {
    return (
      <div className={cn('p-3 rounded-lg', 'bg-accent hover:bg-muted transition-colors')}>
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0">
            <Plug className="w-4 h-4 text-black/60 dark:text-white/60" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono bg-primary/10 text-primary px-1.5 py-0.5 rounded">
                [{source.index}]
              </span>
              <span className="text-sm font-medium truncate">{name ?? t('mcpSkillFallback')}</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {t('mcp_source')}
              {source.calls && source.calls.length > 0 && ` · ${source.calls.length} ${t('calls')}`}
            </p>
            {source.calls && source.calls.length > 0 && (
              <div className="mt-2 space-y-2">
                {source.calls.map((call, callIndex) => (
                  <div key={callIndex} className="bg-muted rounded-lg p-2 text-xs">
                    <div className="font-medium text-primary font-mono mb-1">{call.tool_name}</div>
                    {call.result_preview && (
                      <pre className="text-muted-foreground whitespace-pre-wrap break-all text-xs font-mono leading-relaxed line-clamp-6">
                        {call.result_preview}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Web 类型来源
  const clickUrl = resolveSourceClickUrl(source);

  const getDomain = (url: string) => {
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch {
      return url;
    }
  };

  const faviconUrl = clickUrl ? `https://www.google.com/s2/favicons?sz=64&domain=${getDomain(clickUrl)}` : '';
  const sourceDescription = source.summary || source.snippet;

  const content = (
    <div
      className={cn(
        'flex items-start gap-3 p-3 rounded-lg',
        'bg-accent hover:bg-muted transition-colors',
        clickUrl && 'cursor-pointer',
      )}
    >
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-white border border-border/30 overflow-hidden flex items-center justify-center">
        {faviconUrl ? (
          <img
            src={faviconUrl}
            alt=""
            width={24}
            height={24}
            className="w-6 h-6 object-contain"
            onError={(e) => {
              const img = e.target as HTMLImageElement;
              const parent = img.parentElement;
              if (parent) {
                parent.innerHTML =
                  '<svg class="w-4 h-4 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>';
              }
            }}
          />
        ) : (
          <Globe className="w-4 h-4 text-muted-foreground" />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono bg-primary/10 text-primary px-1.5 py-0.5 rounded">[{source.index}]</span>
          <span className="text-sm font-medium truncate flex-1">{name ?? t('untitled')}</span>
          {clickUrl && <ExternalLink className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />}
        </div>

        {clickUrl && <p className="text-xs text-muted-foreground mt-1 truncate">{getDomain(clickUrl)}</p>}

        {sourceDescription && <p className="text-xs text-muted-foreground mt-2 line-clamp-3">{sourceDescription}</p>}
      </div>
    </div>
  );

  if (clickUrl) {
    return (
      <a href={clickUrl} target="_blank" rel="noopener noreferrer" className="block">
        {content}
      </a>
    );
  }

  return content;
}

function formatSourceDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}
