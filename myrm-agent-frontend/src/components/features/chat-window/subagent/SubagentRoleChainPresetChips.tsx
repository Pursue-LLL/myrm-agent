'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: chat.roleChainPresets 多语言字典)
 * - @/store/useChatStore (POS: 聊天输入状态总线，用于注入角色链协议)
 * - sonner::toast (POS: 角色链装配成功反馈)
 * - lucide-react::{GitFork, Search, ShieldCheck, Feather, Sparkles, Layers} (POS: 视觉指示图标)
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind 类名合并)
 *
 * [OUTPUT]
 * - SubagentRoleChainPresetChips: 子智能体角色链预设芯片组（支持「实现➔审查➔修复」与特定专职链一键激活）
 *
 * [POS]
 * 多智能体编排与观测台控制层。提供 GUI-first 的角色协作链路预设芯片，
 * 消除长指令提示词心智负担，统一编排规范并落实 Review-Loop 轮次安全熔断。
 */

import React, { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { GitFork, Search, ShieldCheck, Feather, Sparkles, Layers } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';

export type RoleChainId = 'implement_review_fix' | 'clarify_scout_worker' | 'watchdog_guard' | 'editorial_publish';

interface RoleChainDefinition {
  id: RoleChainId;
  icon: React.ComponentType<{ className?: string }>;
  accentColor: string;
  badge?: string;
}

const ROLE_CHAINS: RoleChainDefinition[] = [
  {
    id: 'implement_review_fix',
    icon: GitFork,
    accentColor: 'text-blue-500 bg-blue-500/10 border-blue-500/20 hover:border-blue-500/40 hover:bg-blue-500/15',
    badge: 'Loop max 3',
  },
  {
    id: 'clarify_scout_worker',
    icon: Search,
    accentColor: 'text-purple-500 bg-purple-500/10 border-purple-500/20 hover:border-purple-500/40 hover:bg-purple-500/15',
  },
  {
    id: 'watchdog_guard',
    icon: ShieldCheck,
    accentColor: 'text-amber-500 bg-amber-500/10 border-amber-500/20 hover:border-amber-500/40 hover:bg-amber-500/15',
    badge: 'Art 55 Guard',
  },
  {
    id: 'editorial_publish',
    icon: Feather,
    accentColor: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20 hover:border-emerald-500/40 hover:bg-emerald-500/15',
    badge: 'Fact-Check',
  },
];

export interface SubagentRoleChainPresetChipsProps {
  className?: string;
  onSelectChain?: (chainId: RoleChainId) => void;
  compact?: boolean;
}

export const SubagentRoleChainPresetChips = memo(function SubagentRoleChainPresetChips({
  className,
  onSelectChain,
  compact = false,
}: SubagentRoleChainPresetChipsProps) {
  const t = useTranslations('chat.roleChainPresets');
  const setInputMessage = useChatStore((s) => s.setInputMessage);

  const handleApplyChain = useCallback(
    (chainId: RoleChainId) => {
      const name = t(`chains.${chainId}.name`);
      const chainPrompt = t(`chains.${chainId}.prompt`);

      const current = useChatStore.getState().inputMessage || '';
      const combined = current.trim() ? `${chainPrompt}\n${current}` : chainPrompt;

      setInputMessage(combined);
      toast.success(t('chainAssembled', { name }));

      if (onSelectChain) {
        onSelectChain(chainId);
      }

      // Focus composer
      const textarea = document.querySelector('textarea') as HTMLTextAreaElement | null;
      if (textarea) {
        textarea.focus();
        const len = combined.length;
        textarea.setSelectionRange(len, len);
      }
    },
    [onSelectChain, setInputMessage, t],
  );

  return (
    <div
      data-testid="subagent-role-chain-preset-chips"
      className={cn('flex flex-col gap-2 w-full', className)}
    >
      {!compact && (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-medium">
          <Layers className="w-3.5 h-3.5 text-primary" />
          <span>{t('title')}</span>
          <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded-full text-[10px] font-medium bg-primary/10 text-primary border border-primary/20">
            <Sparkles className="w-2.5 h-2.5" />
            {t('badge')}
          </span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {ROLE_CHAINS.map((chain) => {
          const Icon = chain.icon;
          const name = t(`chains.${chain.id}.name`);
          const desc = t(`chains.${chain.id}.desc`);

          return (
            <button
              key={chain.id}
              type="button"
              data-testid={`role-chain-chip-${chain.id}`}
              onClick={() => handleApplyChain(chain.id)}
              title={desc}
              className={cn(
                'group inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium',
                'border bg-background/80 shadow-2xs hover:shadow-xs transition-all duration-150 cursor-pointer',
                chain.accentColor,
              )}
            >
              <Icon className="w-3.5 h-3.5 shrink-0 group-hover:scale-110 transition-transform" />
              <span className="truncate max-w-[180px] sm:max-w-none text-foreground/90 group-hover:text-foreground">
                {name}
              </span>
              {chain.badge && (
                <span className="text-[9px] px-1.5 py-0.2 rounded-full bg-muted/80 text-muted-foreground font-semibold uppercase tracking-wider shrink-0">
                  {chain.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
});

SubagentRoleChainPresetChips.displayName = 'SubagentRoleChainPresetChips';
export default SubagentRoleChainPresetChips;
