'use client';

/**
 * [INPUT]
 * @/store/chat/types::Source (POS: Chat state and SSE event type definitions)
 * @/services/chat::deleteChat, updateChatRecallExclusion (POS: Chat API client)
 * @/hooks/useAgentName::useAgentName (POS: Resolve agent_id to human-friendly name)
 *
 * [OUTPUT]
 * SourcesButton: Message source sheet for Web, MCP and conversation history sources.
 *
 * [POS]
 * Message source action component. Renders source provenance and lets users inspect, navigate, exclude or delete
 * conversation-history sources without mixing them into memory feedback.
 */

/* eslint-disable @next/next/no-img-element */
import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils/classnameUtils';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/primitives/sheet';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { deleteChat, updateChatRecallExclusion } from '@/services/chat';
import { toast } from '@/hooks/useToast';
import type { Source } from '@/store/chat/types';
import { Database, ExternalLink, EyeOff, Globe, Plug, Trash2 } from 'lucide-react';
import { useAgentName } from '@/hooks/useAgentName';

interface SourcesButtonProps {
  sources: Source[];
}

/**
 * 来源按钮组件 - 显示重叠favicon和来源数量，点击打开右侧弹出层
 */
const SourcesButton: React.FC<SourcesButtonProps> = ({ sources }) => {
  const t = useTranslations('sources');
  const [open, setOpen] = useState(false);

  if (!sources || sources.length === 0) {
    return null;
  }

  // 获取唯一域名列表（用于显示favicon）
  const getUniqueDomains = () => {
    const domains: { domain: string; faviconUrl: string }[] = [];
    const seen = new Set<string>();

    for (const source of sources) {
      if (source.url && !source.skill_name) {
        try {
          const url = new URL(source.url);
          const domain = url.hostname;
          if (!seen.has(domain)) {
            seen.add(domain);
            domains.push({
              domain,
              faviconUrl: `https://www.google.com/s2/favicons?sz=128&domain=${domain}`,
            });
          }
        } catch {
          // 忽略无效URL
        }
      }
    }
    return domains.slice(0, 4); // 最多显示4个favicon
  };

  const uniqueDomains = getUniqueDomains();

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          className={cn(
            'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border/30',
            'bg-secondary/50 hover:bg-secondary',
            'text-black/60 dark:text-white/60 hover:text-black dark:hover:text-white',
            'active:scale-95 transition-all duration-200',
          )}
        >
          {/* 重叠的 Favicon 和 MCP 图标 */}
          <div className="relative flex shrink-0 items-center h-5">
            {/* MCP 来源检查 */}
            {sources.some((s) => s.type === 'mcp' || !!s.skill_name) && (
              <Plug className="w-4 h-4 text-black/60 dark:text-white/60" />
            )}
            {sources.some((s) => s.type === 'conversation_history') && (
              <Database className="w-4 h-4 text-black/60 dark:text-white/60" />
            )}

            {/* 重叠的 Favicon 图标 */}
            {uniqueDomains.length > 0 && (
              <div className="flex -space-x-1">
                {uniqueDomains.map((item, index) => (
                  <div
                    key={item.domain}
                    className={cn(
                      'relative shrink-0 overflow-hidden rounded-full',
                      'w-4 h-4 bg-white border border-border/30',
                    )}
                    style={{ zIndex: uniqueDomains.length - index }}
                  >
                    <img
                      src={item.faviconUrl}
                      alt={`${item.domain} favicon`}
                      width={16}
                      height={16}
                      className="w-full h-full object-contain"
                      onError={(e) => {
                        const img = e.target as HTMLImageElement;
                        img.style.display = 'none';
                      }}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 来源数量文案 */}
          <span className="text-xs font-semibold whitespace-nowrap">{t('count', { count: sources.length })}</span>
        </button>
      </SheetTrigger>

      <SheetContent side="right" className="w-[400px] sm:w-[540px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{t('title')}</SheetTitle>
        </SheetHeader>

        <div className="mt-6 space-y-3">
          {sources.map((source, index) => (
            <SourceItem key={`${source.index}-${index}`} source={source} />
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
};

/**
 * 单个来源项组件
 */
const SourceItem: React.FC<{ source: Source }> = ({ source }) => {
  const t = useTranslations('sources');
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const isMcp = source.type === 'mcp' || !!source.skill_name;
  const isConversation = source.type === 'conversation_history';
  const agentName = useAgentName(isConversation ? source.agent_id : null);

  if (isConversation) {
    const chatId = source.conversation_id;
    const jumpToChat = () => {
      if (!chatId) return;
      const highlight = source.message_id ? `?highlight=${encodeURIComponent(source.message_id)}` : '';
      router.push(`/${chatId}${highlight}`);
    };
    const handleExclude = async () => {
      if (!chatId) return;
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
      if (!chatId) return;
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
                {source.title || t('conversation_source')}
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

            {source.summary && <p className="text-xs text-muted-foreground mt-2 line-clamp-3">{source.summary}</p>}
            {source.snippet && <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{source.snippet}</p>}

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
                    className="inline-flex items-center gap-1.5 rounded-full border border-destructive/30 px-2 py-1 text-xs text-destructive hover:bg-destructive/10"
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

  if (isMcp) {
    return (
      <div className={cn('p-3 rounded-lg', 'bg-accent hover:bg-muted transition-colors')}>
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0">
            <Plug className="w-4 h-4 text-black/60 dark:text-white/60" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono bg-primary/10 text-primary px-1.5 py-0.5 rounded">[{source.index}]</span>
              <span className="text-sm font-medium truncate">{source.skill_name || 'MCP Skill'}</span>
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
  const getDomain = (url: string) => {
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch {
      return url;
    }
  };

  const faviconUrl = source.url ? `https://www.google.com/s2/favicons?sz=64&domain=${getDomain(source.url)}` : '';

  const content = (
    <div
      className={cn(
        'flex items-start gap-3 p-3 rounded-lg',
        'bg-accent hover:bg-muted transition-colors',
        source.url && 'cursor-pointer',
      )}
    >
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-white border border-border/30 overflow-hidden flex items-center justify-center">
        {faviconUrl ? (
          <img
            src={faviconUrl}
            alt="favicon"
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
          <span className="text-sm font-medium truncate flex-1">{source.title || t('untitled')}</span>
          {source.url && <ExternalLink className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />}
        </div>

        {source.url && <p className="text-xs text-muted-foreground mt-1 truncate">{getDomain(source.url)}</p>}

        {source.snippet && <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{source.snippet}</p>}
      </div>
    </div>
  );

  if (source.url) {
    return (
      <a href={source.url} target="_blank" rel="noopener noreferrer" className="block">
        {content}
      </a>
    );
  }

  return content;
};

function formatSourceDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export default SourcesButton;
