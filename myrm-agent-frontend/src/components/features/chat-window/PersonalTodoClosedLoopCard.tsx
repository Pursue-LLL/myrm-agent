'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: 多语言国际化)
 * - @/store/useChatStore (POS: 聊天状态与输入框接入)
 * - lucide-react (POS: 矢量图标)
 *
 * [OUTPUT]
 * - PersonalTodoClosedLoopCard: 个人工作流「待办 - 对账 - 周报」三位一体一键启动卡片
 *
 * [POS]
 * 空聊天界面 (EmptyChat) 核心场景化特征包组件。
 * 串联 Kanban、DailyJournal 与 WeeklyReview Blueprint，形成闭环工作流引导。
 */

import React, { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { CheckSquare, BookOpen, FileText, ArrowRight, Sparkles } from 'lucide-react';
import useChatStore from '@/store/useChatStore';
import { cn } from '@/lib/utils/classnameUtils';

interface PersonalTodoClosedLoopCardProps {
  className?: string;
}

export const PersonalTodoClosedLoopCard: React.FC<PersonalTodoClosedLoopCardProps> = memo(
  ({ className }) => {
    const t = useTranslations('chat.personalClosedLoop');
    const setInputMessage = useChatStore((s) => s.setInputMessage);

    const handleSelectPrompt = useCallback(
      (prompt: string) => {
        setInputMessage(prompt);
        // 自动聚焦输入框
        requestAnimationFrame(() => {
          const textarea = document.querySelector<HTMLTextAreaElement>('textarea[data-chat-input]');
          if (textarea) {
            textarea.focus();
            textarea.setSelectionRange(textarea.value.length, textarea.value.length);
          }
        });
      },
      [setInputMessage],
    );

    const steps = [
      {
        id: 'todo',
        icon: CheckSquare,
        color: 'text-blue-500 bg-blue-500/10 border-blue-500/20',
        title: t('step1Title'),
        desc: t('step1Desc'),
        prompt: t('step1Prompt'),
      },
      {
        id: 'log',
        icon: BookOpen,
        color: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
        title: t('step2Title'),
        desc: t('step2Desc'),
        prompt: t('step2Prompt'),
      },
      {
        id: 'report',
        icon: FileText,
        color: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
        title: t('step3Title'),
        desc: t('step3Desc'),
        prompt: t('step3Prompt'),
      },
    ];

    return (
      <div
        className={cn(
          'w-full rounded-2xl border border-border/70 bg-card/60 backdrop-blur-xs p-3.5 sm:p-4 shadow-xs transition-all hover:border-border',
          className,
        )}
      >
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-primary/10 text-primary border border-primary/20 shrink-0">
              <Sparkles className="w-3 h-3" />
              {t('badge')}
            </span>
            <h3 className="text-xs sm:text-sm font-semibold text-foreground truncate">{t('title')}</h3>
          </div>
        </div>
        <p className="text-[11px] sm:text-xs text-muted-foreground mb-3 leading-relaxed">{t('desc')}</p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-2.5">
          {steps.map((step) => {
            const Icon = step.icon;
            return (
              <button
                key={step.id}
                type="button"
                onClick={() => handleSelectPrompt(step.prompt)}
                className="group flex flex-col items-start p-2.5 sm:p-3 rounded-xl border border-border/50 bg-background/50 hover:bg-muted/60 hover:border-primary/30 transition-all text-left cursor-pointer"
              >
                <div className="flex items-center justify-between w-full mb-1.5">
                  <div className={cn('p-1.5 rounded-lg border', step.color)}>
                    <Icon className="w-3.5 h-3.5" />
                  </div>
                  <ArrowRight className="w-3 h-3 text-muted-foreground/40 group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
                </div>
                <div className="text-xs font-medium text-foreground mb-0.5">{step.title}</div>
                <div className="text-[11px] text-muted-foreground line-clamp-1">{step.desc}</div>
              </button>
            );
          })}
        </div>
      </div>
    );
  },
);

PersonalTodoClosedLoopCard.displayName = 'PersonalTodoClosedLoopCard';
export default PersonalTodoClosedLoopCard;
