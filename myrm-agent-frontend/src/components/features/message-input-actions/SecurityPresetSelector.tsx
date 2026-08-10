/**
 * [INPUT]
 * @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * @/services/config::getConfigSyncManager (POS: 配置同步管理器)
 *
 * [OUTPUT]
 * SecurityPresetSelector: 会话级安全预设三档下拉选择器。
 *
 * [POS]
 * 输入框工具栏安全预设选择器。Agent 模式下提供 HITL/Auto-Approve Edits/Read-Only 三档，
 * 与 YOLO 模式互斥。选择后通过 security_preset 字段随消息发送至 server。
 */
'use client';

import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import useChatStore from '@/store/useChatStore';
import { disarmYoloForPreset } from '@/store/chat/securityPreset';
import type { SecurityPreset } from '@/store/chat/types/chatState';

const PRESETS = ['hitl', 'accept_edits', 'explore'] as const;

const ShieldIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={cn('shrink-0', className)}
  >
    <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
  </svg>
);

const PRESET_COLORS: Record<SecurityPreset, { active: string; icon: string }> = {
  hitl: {
    active:
      'bg-emerald-500/10 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30 dark:border-emerald-500/25',
    icon: 'text-emerald-600 dark:text-emerald-400',
  },
  accept_edits: {
    active:
      'bg-amber-500/10 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/30 dark:border-amber-500/25',
    icon: 'text-amber-600 dark:text-amber-400',
  },
  explore: {
    active:
      'bg-sky-500/10 dark:bg-sky-500/15 text-sky-700 dark:text-sky-400 border border-sky-500/30 dark:border-sky-500/25',
    icon: 'text-sky-600 dark:text-sky-400',
  },
};

const INACTIVE_STYLE =
  'bg-black/[0.04] dark:bg-white/[0.06] text-black/40 dark:text-white/40 border border-transparent hover:text-black dark:hover:text-white hover:bg-black/[0.08] dark:hover:bg-white/[0.1]';

const SecurityPresetSelector = () => {
  const t = useTranslations('securityPreset');
  const preset = useChatStore((s) => s.securityPreset);
  const setPreset = useChatStore((s) => s.setSecurityPreset);
  const actionMode = useChatStore((s) => s.actionMode);

  if (actionMode !== 'agent') return null;

  const isDefault = preset === 'hitl';
  const colors = PRESET_COLORS[preset];

  const handleSelect = (next: SecurityPreset) => {
    if (next === preset) return;

    disarmYoloForPreset(next);

    setPreset(next);
  };

  return (
    <DropdownMenu>
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label={t('label')}
                className={cn(
                  'relative flex shrink-0 items-center gap-1.5 h-7 px-2.5 rounded-full text-xs font-medium whitespace-nowrap transition-all duration-300 cursor-pointer select-none',
                  isDefault ? INACTIVE_STYLE : colors.active,
                )}
              >
                <ShieldIcon
                  className={cn('transition-colors duration-300', isDefault ? 'text-current' : colors.icon)}
                />
                <span className="hidden xl:inline">{t(`presets.${preset}.label`)}</span>
              </button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-64 p-3">
            <p className="font-semibold text-sm mb-1">{t('label')}</p>
            <p className="text-xs text-muted-foreground leading-relaxed">{t(`presets.${preset}.desc`)}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <DropdownMenuContent align="start" className="w-72">
        {PRESETS.map((p) => (
          <DropdownMenuItem
            key={p}
            onClick={() => handleSelect(p)}
            className={cn('flex flex-col items-start gap-0.5 py-2', preset === p && 'bg-accent')}
          >
            <span className="text-sm font-medium">{t(`presets.${p}.label`)}</span>
            <span className="text-xs text-muted-foreground leading-snug">{t(`presets.${p}.desc`)}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default SecurityPresetSelector;
