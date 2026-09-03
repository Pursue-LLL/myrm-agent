'use client';

/**
 * [INPUT]
 * - ../message-input-actions/TurnCapabilityToggle::TurnCapabilityToggle (POS: 单轮能力收窄 popover)
 *
 * [OUTPUT]
 * - TurnCapabilityOverrideBar: 输入框上方的单轮能力覆写可见条。
 *
 * [POS]
 * 消息输入区的单轮能力覆写状态可视化层。覆写激活时显示生效范围摘要，支持一键恢复默认
 * 与点摘要唤起 TurnCapabilityToggle 修改。跟随覆写生命周期：无覆写即不渲染。
 */

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { X } from 'lucide-react';
import type { TurnCapabilitySelection } from '@/hooks/message-input/turnCapabilityOverrideCore';
import TurnCapabilityToggle from '../message-input-actions/TurnCapabilityToggle';

interface TurnCapabilityOverrideBarProps {
  selection: TurnCapabilitySelection | null;
  onSelectionChange: (selection: TurnCapabilitySelection | null) => void;
  disabled?: boolean;
}

function formatOverrideSummary(t: ReturnType<typeof useTranslations>, selection: TurnCapabilitySelection): string {
  const parts: string[] = [];
  if (selection.skillIds !== null) {
    parts.push(t('overrideSkillsShort', { skills: selection.skillIds.length }));
  }
  if (selection.mcpNames !== null) {
    parts.push(t('overrideMcpShort', { mcps: selection.mcpNames.length }));
  }
  return parts.join(' · ');
}

export default function TurnCapabilityOverrideBar({
  selection,
  onSelectionChange,
  disabled = false,
}: TurnCapabilityOverrideBarProps) {
  const t = useTranslations('chat.turnCapabilities');
  const [isEditorOpen, setIsEditorOpen] = useState(false);

  if (selection === null) {
    return null;
  }

  const summary = formatOverrideSummary(t, selection);

  return (
    <div
      data-testid="turn-capability-override-bar"
      className="mb-2 flex flex-wrap items-center gap-2 rounded-lg border border-primary/25 bg-primary/[0.06] px-3 py-2"
    >
      <button
        type="button"
        onClick={() => setIsEditorOpen((prev) => !prev)}
        className="inline-flex h-6 max-w-full items-center gap-1.5 rounded-md border border-primary/20 bg-primary/10 px-2 text-xs font-medium leading-none text-primary"
        title={summary}
        aria-label={t('popoverTitle')}
      >
        <span className="truncate">{summary}</span>
      </button>
      <span className="text-[11px] text-muted-foreground">{t('nextTurnOnly')}</span>
      <button
        type="button"
        onClick={() => onSelectionChange(null)}
        className="ml-auto inline-flex h-6 shrink-0 items-center gap-1 rounded-md border border-border/60 px-2 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        aria-label={t('overrideRemove')}
      >
        <X size={12} />
        {t('clearOverride')}
      </button>
      <TurnCapabilityToggle
        selection={selection}
        onSelectionChange={onSelectionChange}
        disabled={disabled}
        open={isEditorOpen}
        onOpenChange={setIsEditorOpen}
        hideTrigger
      />
    </div>
  );
}
