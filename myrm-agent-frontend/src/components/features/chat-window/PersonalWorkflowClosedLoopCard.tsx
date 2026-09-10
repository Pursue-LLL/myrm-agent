'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: 多语言)
 * - lucide-react (POS: 图标)
 * - @/store/useChatStore (POS: 会话输入草稿写入)
 *
 * [OUTPUT]
 * - PersonalWorkflowClosedLoopCard: EmptyChat「待办-对账-周报」个人工作流闭环一体化引导卡片
 *
 * [POS]
 * 空聊天界面高频工作流发现卡片。
 * 提供 Kanban 看板待办、DailyJournal 每日对账日志与 weekly_review 自动化智能周报的一键贯通。
 */

import React, { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { ListTodo, BookOpenCheck, FileText, ArrowRight, Sparkles } from 'lucide-react';
import useChatStore from '@/store/useChatStore';
import { cn } from '@/lib/utils/classnameUtils';

interface PersonalWorkflowClosedLoopCardProps {
  className?: string;
}

export const PersonalWorkflowClosedLoopCard = memo(function PersonalWorkflowClosedLoopCard({
  className,
}: PersonalWorkflowClosedLoopCardProps) {
  const t = useTranslations('chat.personalClosedLoop');
  const setInputMessage = useChatStore((state) => state.setInputMessage);

  const handleSelectPrompt = useCallback(
    (promptText: string) => {
      setInputMessage(promptText);
      const textarea = document.querySelector<HTMLTextAreaElement>('textarea[data-chat-input]');
      if (textarea) {
        textarea.focus();
      }
    },
    [setInputMessage],
  );

  const steps = [
    {
      id: 'step1',
      title: t('step1Title'),
      desc: t('step1Desc'),
      prompt: t('step1Prompt'),
      Icon: ListTodo,
      color: 'text-sky-500 bg-sky-500/10 border-sky-500/20',
    },
    {
      id: 'step2',
      title: t('step2Title'),
      desc: t('step2Desc'),
      prompt: t('step2Prompt'),
      Icon: BookOpenCheck,
      color: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
    },
    {
      id: 'step3',
      title: t('step3Title'),
      desc: t('step3Desc'),
      prompt: t('step3Prompt'),
      Icon: FileText,
      color: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
    },
  ];

  return (
    <div
      data-testid="personal-workflow-closed-loop-card"
      className={cn(
        'w-full rounded-2xl border border-border/60 bg-gradient-to-br from-card/80 to-secondary/30 backdrop-blur-sm p-4 sm:p-5 space-y-4 shadow-xs',
        className,
      )}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/40 pb-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-primary/10 text-primary border border-primary/20">
              <Sparkles size={11} />
              {t('badge')}
            </span>
            <h3 className="text-sm font-semibold text-foreground tracking-tight">{t('title')}</h3>
          </div>
          <p className="text-xs text-muted-foreground/90 max-w-2xl">{t('desc')}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {steps.map((step, idx) => {
          const { Icon } = step;
          return (
            <button
              key={step.id}
              type="button"
              onClick={() => handleSelectPrompt(step.prompt)}
              className="group relative flex flex-col justify-between p-3.5 rounded-xl border border-border/50 bg-background/60 hover:bg-background hover:border-primary/40 hover:shadow-xs transition-all text-left cursor-pointer"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className={cn('p-2 rounded-lg border', step.color)}>
                    <Icon size={16} />
                  </div>
                  <span className="text-[11px] font-mono text-muted-foreground/60 group-hover:text-primary transition-colors">
                    0{idx + 1}
                  </span>
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-foreground group-hover:text-primary transition-colors">
                    {step.title}
                  </h4>
                  <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2 leading-relaxed">
                    {step.desc}
                  </p>
                </div>
              </div>

              <div className="mt-3 pt-2.5 border-t border-border/30 flex items-center justify-between text-[11px] font-medium text-muted-foreground group-hover:text-primary transition-colors">
                <span>{t('oneClickAction')}</span>
                <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
});

PersonalWorkflowClosedLoopCard.displayName = 'PersonalWorkflowClosedLoopCard';
export default PersonalWorkflowClosedLoopCard;
