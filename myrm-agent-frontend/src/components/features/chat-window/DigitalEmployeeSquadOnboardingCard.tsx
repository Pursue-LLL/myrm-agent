'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: chat.squadOnboarding 多语言字典)
 * - @/store/useChatStore (POS: 聊天输入状态总线，用于注入 starter prompt)
 * - sonner::toast (POS: 战队组建成功交互反馈)
 * - lucide-react::{Users, Network, ShieldCheck, Code, FileSearch, Sparkles, ArrowRight, AtSign} (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - DigitalEmployeeSquadOnboardingCard: 数字员工战队编排入门卡视图组件。
 *
 * [POS]
 * EmptyChat 首屏数字员工战队编排入门卡（Onboarding Hub）。阐释 Delegate 协作范式，
 * 呈现典型 Squad 战队配置，支持一键组建与 @Agent 交互联动。
 */

import React, { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Users, Network, ShieldCheck, Code, FileSearch, Sparkles, ArrowRight, AtSign } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';

interface SquadPresetItem {
  id: 'rnd' | 'research' | 'strategy';
  icon: React.ComponentType<{ className?: string }>;
  accentColor: string;
}

const SQUAD_PRESETS: SquadPresetItem[] = [
  {
    id: 'rnd',
    icon: Code,
    accentColor: 'text-blue-500 bg-blue-500/10 border-blue-500/20 group-hover:border-blue-500/40',
  },
  {
    id: 'research',
    icon: FileSearch,
    accentColor: 'text-purple-500 bg-purple-500/10 border-purple-500/20 group-hover:border-purple-500/40',
  },
  {
    id: 'strategy',
    icon: ShieldCheck,
    accentColor: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20 group-hover:border-emerald-500/40',
  },
];

interface DigitalEmployeeSquadOnboardingCardProps {
  className?: string;
}

export const DigitalEmployeeSquadOnboardingCard = memo(function DigitalEmployeeSquadOnboardingCard({
  className,
}: DigitalEmployeeSquadOnboardingCardProps) {
  const t = useTranslations('chat.squadOnboarding');
  const setInputMessage = useChatStore((s) => s.setInputMessage);

  const handleAssembleSquad = useCallback(
    (presetId: SquadPresetItem['id']) => {
      const name = t(`squads.${presetId}.name`);
      const prompt = t(`squads.${presetId}.prompt`);

      setInputMessage(prompt);
      toast.success(t('squadReady', { name }));

      // Focus the chat message input textarea
      const textarea = document.querySelector('textarea') as HTMLTextAreaElement | null;
      if (textarea) {
        textarea.focus();
      }
    },
    [setInputMessage, t],
  );

  const handleQuickMention = useCallback(() => {
    const currentInput = useChatStore.getState().inputMessage || '';
    const nextInput = currentInput.endsWith('@') ? currentInput : currentInput ? `${currentInput} @` : '@';
    setInputMessage(nextInput);

    const textarea = document.querySelector('textarea') as HTMLTextAreaElement | null;
    if (textarea) {
      textarea.focus();
      const len = nextInput.length;
      textarea.setSelectionRange(len, len);
    }
  }, [setInputMessage]);

  return (
    <section
      data-testid="digital-employee-squad-onboarding-hub"
      className={cn(
        'w-full max-w-full rounded-2xl border border-border/80 bg-background/60 backdrop-blur-md p-4 sm:p-5 shadow-xs transition-all hover:border-border',
        className,
      )}
    >
      {/* Header with Delegate Paradigm Indicator */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-3 border-b border-border/50">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10 text-primary shrink-0">
            <Network className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-foreground/90">{t('title')}</h3>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-primary/10 text-primary border border-primary/20">
                <Sparkles className="w-2.5 h-2.5" />
                {t('badge')}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{t('description')}</p>
          </div>
        </div>

        {/* Quick Mention Trigger Link */}
        <button
          type="button"
          onClick={handleQuickMention}
          data-testid="squad-mention-quick-action"
          className="inline-flex items-center gap-1.5 self-start sm:self-auto px-2.5 py-1 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground bg-muted/50 hover:bg-muted border border-border/60 transition-colors cursor-pointer"
        >
          <AtSign className="w-3.5 h-3.5 text-primary" />
          <span>{t('quickInsertMention')}</span>
        </button>
      </div>

      {/* Squad Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-3.5">
        {SQUAD_PRESETS.map((preset) => {
          const Icon = preset.icon;
          const name = t(`squads.${preset.id}.name`);
          const tagline = t(`squads.${preset.id}.tagline`);
          const leader = t(`squads.${preset.id}.leader`);
          const workers = t(`squads.${preset.id}.workers`);

          return (
            <div
              key={preset.id}
              data-testid={`squad-card-${preset.id}`}
              className="group flex flex-col justify-between rounded-xl border border-border/70 bg-card/50 p-3.5 transition-all duration-200 hover:shadow-xs hover:border-primary/40 hover:bg-card"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div
                    className={cn(
                      'flex items-center justify-center w-7 h-7 rounded-lg border transition-colors',
                      preset.accentColor,
                    )}
                  >
                    <Icon className="w-3.5 h-3.5" />
                  </div>
                  <span className="text-[10px] font-medium text-muted-foreground/80 bg-muted/60 px-1.5 py-0.5 rounded">
                    {t('delegateTag')}
                  </span>
                </div>

                <div>
                  <h4 className="text-xs font-semibold text-foreground group-hover:text-primary transition-colors">
                    {name}
                  </h4>
                  <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-1">{tagline}</p>
                </div>

                {/* Team Roster Detail */}
                <div className="space-y-1 pt-1 border-t border-border/40 text-[11px]">
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <span className="font-medium text-foreground/80 shrink-0">{t('leaderLabel')}</span>
                    <span className="truncate">{leader}</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <span className="font-medium text-foreground/80 shrink-0">{t('workersLabel')}</span>
                    <span className="truncate text-[10px]">{workers}</span>
                  </div>
                </div>
              </div>

              {/* Action Button */}
              <button
                type="button"
                onClick={() => handleAssembleSquad(preset.id)}
                className="mt-3 w-full inline-flex items-center justify-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-primary/10 hover:bg-primary text-primary hover:text-primary-foreground border border-primary/20 hover:border-primary transition-all duration-150 cursor-pointer shadow-2xs"
              >
                <span>{t('assembleSquad')}</span>
                <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
              </button>
            </div>
          );
        })}
      </div>

      {/* Footer Hint */}
      <div className="mt-3 flex items-center gap-1.5 text-[11px] text-muted-foreground bg-muted/30 px-3 py-1.5 rounded-lg border border-border/40">
        <Users className="w-3.5 h-3.5 text-primary shrink-0" />
        <span className="truncate">{t('mentionTip')}</span>
      </div>
    </section>
  );
});

DigitalEmployeeSquadOnboardingCard.displayName = 'DigitalEmployeeSquadOnboardingCard';
export default DigitalEmployeeSquadOnboardingCard;
