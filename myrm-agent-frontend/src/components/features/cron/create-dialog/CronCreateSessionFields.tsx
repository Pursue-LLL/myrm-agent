'use client';

/**
 * [INPUT] ./useCronCreateForm::CronCreateForm (POS: 表单状态), @/store/useChatStore (POS: 可绑定的会话列表), @/store/useProviderStore (POS: 默认模型)
 * [OUTPUT] CronCreateSessionFields: 会话模式（独立会话 / 绑定对话线程，含线程选择）与默认模型说明
 * [POS] 自定义创建流程的“在哪个会话里跑”区块：会话模式仅周期性 Agent 任务可选（单次任务总是独立会话）；从某个对话打开时线程固定为该对话；默认模型说明只在使用默认 Agent 且已配置主模型时出现。
 */

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Cpu, MessageCircle } from 'lucide-react';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import useChatStore from '@/store/useChatStore';
import useProviderStore from '@/store/useProviderStore';
import { DEFAULT_AGENT_ID, type DraftSessionTarget } from './cronCreateModel';
import type { CronCreateForm } from './useCronCreateForm';

interface CronCreateSessionFieldsProps {
  form: CronCreateForm;
  presetChatId?: string | null;
  presetChatTitle?: string | null;
}

export function CronCreateSessionFields({ form, presetChatId, presetChatTitle }: CronCreateSessionFieldsProps) {
  const t = useTranslations('cron');
  const { defaultModelConfig } = useProviderStore();
  const chatHistoryItems = useChatStore((s) => s.chatHistoryItems);
  const { draft, patch } = form;
  const { uiMode, scheduleKind, sessionTarget, selectedChatId, agentId } = draft;

  const defaultModel = useMemo(() => {
    const primary = defaultModelConfig.baseModel.primary;
    return primary ? { providerId: primary.providerId, model: primary.model } : null;
  }, [defaultModelConfig]);

  return (
    <>
      {/* Session Mode — only for recurring agent schedules */}
      {uiMode === 'agent' && scheduleKind !== 'once' && (
        <div className="space-y-1.5">
          <Label className="text-xs">{t('createSessionModeLabel')}</Label>
          <Select value={sessionTarget} onValueChange={(v) => patch({ sessionTarget: v as DraftSessionTarget })}>
            <SelectTrigger className="h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="isolated">{t('createSessionIsolated')}</SelectItem>
              <SelectItem value="main">{t('createSessionThread')}</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-[11px] text-muted-foreground">
            {sessionTarget === 'isolated' ? t('createSessionIsolatedDesc') : t('createSessionThreadDesc')}
          </p>
          {sessionTarget === 'main' && presetChatId && presetChatTitle && (
            <div className="rounded-full border border-primary/20 bg-primary/5 px-3 py-2 flex items-center gap-2">
              <MessageCircle className="h-3.5 w-3.5 text-primary shrink-0" />
              <span className="text-xs text-primary truncate">{presetChatTitle}</span>
            </div>
          )}
          {sessionTarget === 'main' && !presetChatId && (
            <Select value={selectedChatId} onValueChange={(value) => patch({ selectedChatId: value })}>
              <SelectTrigger className="h-8 text-sm">
                <SelectValue placeholder={t('createSessionSelectChat')} />
              </SelectTrigger>
              <SelectContent className="max-h-[200px]">
                {chatHistoryItems.map((chat) => (
                  <SelectItem key={chat.id} value={chat.id}>
                    <span className="truncate">{chat.title}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      )}

      {/* Default Model Info */}
      {uiMode === 'agent' && agentId === DEFAULT_AGENT_ID && defaultModel && (
        <div className="rounded-full border border-border bg-muted/30 px-3 py-2.5 flex gap-2">
          <Cpu className="h-4 w-4 shrink-0 mt-0.5 text-muted-foreground" />
          <p className="text-xs text-muted-foreground">
            {t('estDefaultModel', {
              provider: defaultModel.providerId,
              model: defaultModel.model,
            })}
          </p>
        </div>
      )}
    </>
  );
}
