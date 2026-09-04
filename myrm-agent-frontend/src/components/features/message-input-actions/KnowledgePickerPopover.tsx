'use client';

/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天状态源，读取/操作当前绑定的知识库)
 * - @/services/memory/sharedContexts (POS: 共享上下文/知识库 REST 客户端)
 * - @/components/primitives/popover / switch / tooltip (POS: 基础交互容器)
 * - next-intl::useTranslations (POS: 双语国际化)
 *
 * [OUTPUT]
 * - KnowledgePickerPopover: 聊天输入区会话级知识库选择与即时挂载浮层
 *
 * [POS]
 * 输入控制栏知识库挂载入口。支持会话级多库即时切换、6 个防爆硬门禁、搜索过滤与空状态导流。
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { BookOpen, Search, ExternalLink, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { Switch } from '@/components/primitives/switch';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import {
  listSharedContexts,
  listSharedContextBindingsForTarget,
  createSharedContextBinding,
  deleteSharedContextBinding,
  deleteSharedContextBindingByTarget,
  type SharedContext,
} from '@/services/memory/sharedContexts';
import { toast } from '@/lib/utils/toast';

const MAX_MOUNTED_KNOWLEDGE_BASES = 6;

export default function KnowledgePickerPopover() {
  const t = useTranslations('chat.knowledgePicker');
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [contexts, setContexts] = useState<SharedContext[]>([]);
  const [bindingsMap, setBindingsMap] = useState<Record<string, string>>({});
  const [pendingId, setPendingId] = useState<string | null>(null);

  const {
    chatId,
    activeKnowledgeBaseIds,
    activeKnowledgeBaseNames,
    setActiveKnowledgeBaseIds,
    setActiveKnowledgeBaseNames,
    removeActiveKnowledgeBase,
    incognitoMode,
  } = useChatStore(
    useShallow((s) => ({
      chatId: s.chatId,
      activeKnowledgeBaseIds: s.activeKnowledgeBaseIds,
      activeKnowledgeBaseNames: s.activeKnowledgeBaseNames,
      setActiveKnowledgeBaseIds: s.setActiveKnowledgeBaseIds,
      setActiveKnowledgeBaseNames: s.setActiveKnowledgeBaseNames,
      removeActiveKnowledgeBase: s.removeActiveKnowledgeBase,
      incognitoMode: s.incognitoMode,
    })),
  );

  const activeCount = activeKnowledgeBaseIds.length;
  const isMounted = activeCount > 0;

  // 加载可用知识库与当前会话绑定关系
  const loadKnowledgeData = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      try {
        const listRes = await listSharedContexts('active');
        const loadedContexts = listRes.items || [];
        setContexts(loadedContexts);

        // 如果当前存在真实会话 ID 且非隐私模式，拉取其已有绑定并同步
        if (chatId && !incognitoMode) {
          const bindRes = await listSharedContextBindingsForTarget('conversation', chatId);
          const map: Record<string, string> = {};
          const activeIds: string[] = [];
          const activeNames: Record<string, string> = {};

          bindRes.items.forEach((b) => {
            map[b.context_id] = b.id;
            activeIds.push(b.context_id);
            const matched = loadedContexts.find((c) => c.id === b.context_id);
            if (matched) {
              activeNames[b.context_id] = matched.name;
            }
          });

          // 解决冷启动时序竞态：如果远端已有绑定，以远端权威同步；
          // 若远端暂为空但本地 store 中有新会话预选的库，保留本地状态并防止覆盖冲刷
          if (activeIds.length > 0) {
            setBindingsMap(map);
            setActiveKnowledgeBaseIds(activeIds);
            setActiveKnowledgeBaseNames(activeNames);
          } else {
            const currentStoreIds = useChatStore.getState().activeKnowledgeBaseIds;
            if (currentStoreIds.length === 0) {
              setBindingsMap({});
              setActiveKnowledgeBaseIds([]);
              setActiveKnowledgeBaseNames({});
            }
          }
        }
      } catch (err) {
        console.error('[KnowledgePicker] Failed to load data:', err);
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [chatId, incognitoMode, setActiveKnowledgeBaseIds, setActiveKnowledgeBaseNames],
  );

  // 会话切换时自动同步已绑定知识库
  useEffect(() => {
    if (chatId && !incognitoMode) {
      void loadKnowledgeData(true);
    }
  }, [chatId, incognitoMode, loadKnowledgeData]);

  // 打开弹窗时刷新
  useEffect(() => {
    if (open) {
      void loadKnowledgeData(false);
    }
  }, [open, loadKnowledgeData]);

  // 切换单项挂载状态
  const handleToggle = useCallback(
    async (context: SharedContext) => {
      const isCurrentlyActive = activeKnowledgeBaseIds.includes(context.id);
      setPendingId(context.id);

      try {
        if (isCurrentlyActive) {
          // 解绑
          if (chatId && !incognitoMode) {
            const bindingId = bindingsMap[context.id];
            if (bindingId) {
              await deleteSharedContextBinding(context.id, bindingId);
            } else {
              await deleteSharedContextBindingByTarget(context.id, 'conversation', chatId);
            }
            setBindingsMap((prev) => {
              const copy = { ...prev };
              delete copy[context.id];
              return copy;
            });
          }
          removeActiveKnowledgeBase(context.id);
        } else {
          // 挂载前检查上限
          if (activeKnowledgeBaseIds.length >= MAX_MOUNTED_KNOWLEDGE_BASES) {
            toast.error(t('maxLimitReached', { max: MAX_MOUNTED_KNOWLEDGE_BASES }));
            return;
          }

          if (chatId && !incognitoMode) {
            const binding = await createSharedContextBinding(context.id, {
              target_type: 'conversation',
              target_id: chatId,
            });
            setBindingsMap((prev) => ({ ...prev, [context.id]: binding.id }));
          }

          setActiveKnowledgeBaseIds([...activeKnowledgeBaseIds, context.id]);
          setActiveKnowledgeBaseNames({
            ...activeKnowledgeBaseNames,
            [context.id]: context.name,
          });
        }
      } catch (err) {
        console.error('[KnowledgePicker] Toggle error:', err);
        toast.error(t('operationFailed'));
      } finally {
        setPendingId(null);
      }
    },
    [
      activeKnowledgeBaseIds,
      activeKnowledgeBaseNames,
      bindingsMap,
      chatId,
      incognitoMode,
      removeActiveKnowledgeBase,
      setActiveKnowledgeBaseIds,
      setActiveKnowledgeBaseNames,
      t,
    ],
  );

  const filteredContexts = useMemo(() => {
    const q = searchKeyword.trim().toLowerCase();
    if (!q) return contexts;
    return contexts.filter(
      (c) => c.name.toLowerCase().includes(q) || (c.description && c.description.toLowerCase().includes(q)),
    );
  }, [contexts, searchKeyword]);

  return (
    <TooltipProvider delayDuration={300}>
      <Popover open={open} onOpenChange={setOpen}>
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild>
              <button
                type="button"
                data-testid="knowledge-picker-toggle"
                onClick={() => setOpen((prev) => !prev)}
                aria-label={t('ariaLabel')}
                className={cn(
                  'flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors shrink-0',
                  isMounted
                    ? 'bg-violet-500/10 text-violet-600 dark:text-violet-400 hover:bg-violet-500/20'
                    : 'text-muted-foreground/70 hover:text-muted-foreground hover:bg-muted/50',
                )}
              >
                <BookOpen size={14} />
                {isMounted && <span className="font-medium text-[11px]">{activeCount}</span>}
              </button>
            </PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent side="top">
            <p>{isMounted ? t('activeCount', { count: activeCount }) : t('tooltip')}</p>
          </TooltipContent>
        </Tooltip>

        <PopoverContent
          className="w-72 max-w-[calc(100vw-2rem)] p-0 shadow-lg border border-border/60"
          side="top"
          align="start"
          sideOffset={8}
        >
          {/* Header */}
          <div className="px-3 py-2.5 border-b border-border/50 flex items-center justify-between">
            <div className="flex items-center gap-1.5 min-w-0">
              <BookOpen size={14} className="text-violet-500 shrink-0" />
              <span className="text-xs font-semibold truncate text-foreground">{t('title')}</span>
            </div>
            <Link
              href="/settings/wiki"
              className="text-[11px] text-muted-foreground hover:text-foreground inline-flex items-center gap-0.5 shrink-0"
              onClick={() => setOpen(false)}
            >
              <span>{t('manage')}</span>
              <ExternalLink size={10} />
            </Link>
          </div>

          {/* Search Input */}
          <div className="px-2.5 py-2 border-b border-border/40">
            <div className="relative flex items-center">
              <Search size={13} className="absolute left-2.5 text-muted-foreground/60 pointer-events-none" />
              <input
                type="text"
                value={searchKeyword}
                onChange={(e) => setSearchKeyword(e.target.value)}
                placeholder={t('searchPlaceholder')}
                className="w-full bg-muted/40 hover:bg-muted/60 focus:bg-background text-xs pl-7 pr-2.5 py-1.5 rounded-md border border-border/40 focus:border-violet-500 focus:outline-none transition-colors"
              />
            </div>
          </div>

          {/* Context List */}
          <div className="max-h-[260px] overflow-y-auto py-1 divide-y divide-border/20">
            {loading ? (
              <div className="flex items-center justify-center py-6 text-muted-foreground gap-2 text-xs">
                <Loader2 size={14} className="animate-spin" />
                <span>Loading...</span>
              </div>
            ) : filteredContexts.length === 0 ? (
              <div className="px-4 py-6 text-center text-xs text-muted-foreground">
                <p>{contexts.length === 0 ? t('emptyKnowledgeBases') : t('noSearchResults')}</p>
                {contexts.length === 0 && (
                  <Link
                    href="/settings/wiki"
                    onClick={() => setOpen(false)}
                    className="mt-2.5 inline-block text-violet-600 dark:text-violet-400 font-medium hover:underline"
                  >
                    {t('manage')} &rarr;
                  </Link>
                )}
              </div>
            ) : (
              filteredContexts.map((ctx) => {
                const checked = activeKnowledgeBaseIds.includes(ctx.id);
                const isProcessing = pendingId === ctx.id;

                return (
                  <div
                    key={ctx.id}
                    className={cn(
                      'px-3 py-2 flex items-center justify-between gap-2.5 transition-colors text-xs',
                      checked ? 'bg-violet-500/5' : 'hover:bg-muted/30',
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-foreground truncate" title={ctx.name}>{ctx.name}</div>
                      {ctx.description && (
                        <div className="text-[11px] text-muted-foreground line-clamp-1 mt-0.5" title={ctx.description}>{ctx.description}</div>
                      )}
                    </div>
                    <Switch
                      checked={checked}
                      disabled={isProcessing}
                      onCheckedChange={() => void handleToggle(ctx)}
                      aria-label={ctx.name}
                    />
                  </div>
                );
              })
            )}
          </div>

          {incognitoMode && (
            <div className="px-3 py-1.5 border-t border-border/50 bg-amber-500/[0.05] text-[10px] text-amber-600 dark:text-amber-400">
              {t('incognitoNotice')}
            </div>
          )}
        </PopoverContent>
      </Popover>
    </TooltipProvider>
  );
}
