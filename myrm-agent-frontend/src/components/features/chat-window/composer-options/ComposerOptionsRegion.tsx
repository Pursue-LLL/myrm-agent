'use client';

/**
 * [INPUT]
 * - @/components/features/message-input-actions (POS: 输入区的各个选项控件)
 * - ../thinking-permission, ../agent-config-panel/ExpertSummonPopover, ../ForkButton (POS: 同属输入区的选项控件)
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 *
 * [OUTPUT]
 * - ComposerOptionsRegion: the collapsible region under the desktop composer's primary row, holding every secondary option.
 *
 * [POS]
 * The controls stay mounted while the region is closed, so their state and scripted clicks keep working; a closed
 * region is `inert`, which takes them out of the tab order and the accessibility tree. The height animates through
 * grid rows because the content height is not known in advance. Phones never show it: they reach the same options
 * through the action sheet.
 */

import type { ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';

import AgentIndicator from '@/components/features/message-input-actions/AgentIndicator';
import DeepSearchToggle from '@/components/features/message-input-actions/DeepSearchToggle';
import FocusFlushButton from '@/components/features/message-input-actions/FocusFlushButton';
import GoalModeToggle from '@/components/features/message-input-actions/GoalModeToggle';
import IncognitoModeToggle from '@/components/features/message-input-actions/IncognitoModeToggle';
import KnowledgePickerPopover from '@/components/features/message-input-actions/KnowledgePickerPopover';
import SecurityPresetSelector from '@/components/features/message-input-actions/SecurityPresetSelector';
import SessionSkillsToggle from '@/components/features/message-input-actions/SessionSkillsToggle';
import ThinkingIntensityButton from '@/components/features/message-input-actions/ThinkingIntensityButton';
import ToolsPanel from '@/components/features/message-input-actions/ToolsPanel';
import TurnCapabilityToggle from '@/components/features/message-input-actions/TurnCapabilityToggle';
import WorkflowModeToggle from '@/components/features/message-input-actions/WorkflowModeToggle';
import type { TurnCapabilitySelection } from '@/hooks/message-input/turnCapabilityOverrideCore';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';

import { ExpertSummonPopover } from '../agent-config-panel/ExpertSummonPopover';
import { ForkButton } from '../ForkButton';
import { ThinkingBudgetEffortSlider } from '../thinking-permission';

interface ComposerOptionsRegionProps {
  id: string;
  expanded: boolean;
  loading: boolean;
  turnCapabilitySelection: TurnCapabilitySelection | null;
  onTurnCapabilityChange: (selection: TurnCapabilitySelection | null) => void;
  turnCapabilityOpen: boolean;
  onTurnCapabilityOpenChange: (open: boolean) => void;
}

/** A captioned row of controls. A row whose controls all render nothing disappears with its caption. */
function OptionGroup({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[5rem_minmax(0,1fr)] items-center gap-x-3 has-[[data-option-group-body]:empty]:hidden">
      <span className="whitespace-nowrap text-[11px] font-medium tracking-wide text-muted-foreground/80">
        {caption}
      </span>
      <div data-option-group-body className="flex min-w-0 flex-wrap items-center gap-2">
        {children}
      </div>
    </div>
  );
}

export function ComposerOptionsRegion({
  id,
  expanded,
  loading,
  turnCapabilitySelection,
  onTurnCapabilityChange,
  turnCapabilityOpen,
  onTurnCapabilityOpenChange,
}: ComposerOptionsRegionProps) {
  const t = useTranslations('chat.input');
  const { actionMode, agentConfig, chatId, messageCount } = useChatStore(
    useShallow((state) => ({
      actionMode: state.actionMode,
      agentConfig: state.agentConfig,
      chatId: state.chatId,
      messageCount: state.messages.length,
    })),
  );

  return (
    <section
      id={id}
      aria-label={t('toolbar')}
      data-testid="composer-options-region"
      data-state={expanded ? 'open' : 'closed'}
      inert={!expanded}
      className={cn(
        'hidden sm:grid transition-[grid-template-rows,opacity] duration-200 ease-out motion-reduce:transition-none',
        expanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
      )}
    >
      <div className="min-h-0 overflow-hidden">
        <div className="mt-3 flex flex-col gap-2 border-t border-border/50 pb-1 pt-3">
          <OptionGroup caption={t('toolbarGroupThinking')}>
            <ThinkingBudgetEffortSlider />
            <ThinkingIntensityButton actionMode={actionMode} agentConfig={agentConfig} />
          </OptionGroup>
          <OptionGroup caption={t('toolbarGroupModes')}>
            <DeepSearchToggle />
            <WorkflowModeToggle />
            <GoalModeToggle />
            <IncognitoModeToggle />
            <SecurityPresetSelector />
            <FocusFlushButton />
          </OptionGroup>
          <OptionGroup caption={t('toolbarGroupCapabilities')}>
            <ExpertSummonPopover />
            {chatId && messageCount > 0 && !loading && <ForkButton chatId={chatId} messageIndex={messageCount - 1} />}
            <AgentIndicator />
            <SessionSkillsToggle />
            <KnowledgePickerPopover />
            <TurnCapabilityToggle
              selection={turnCapabilitySelection}
              onSelectionChange={onTurnCapabilityChange}
              disabled={loading}
              open={turnCapabilityOpen}
              onOpenChange={onTurnCapabilityOpenChange}
            />
            <ToolsPanel />
          </OptionGroup>
        </div>
      </div>
    </section>
  );
}
