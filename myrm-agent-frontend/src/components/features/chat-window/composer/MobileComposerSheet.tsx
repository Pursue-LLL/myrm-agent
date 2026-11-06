'use client';

/**
 * [INPUT]
 * - ../mobile/MobileActionSheet::MobileActionSheet (POS: 手机底部操作表容器)
 * - ../mobile/useMobileSheetEntries::useMobileSheetEntries (POS: 操作表的入口列表)
 * - @/components/features/message-input-actions/* (POS: 操作表底部的开关与选择器)
 * - @/hooks/message-input/turnCapabilityOverrideCore::TurnCapabilitySelection (POS: 本轮能力覆写)
 *
 * [OUTPUT]
 * - MobileComposerSheet: 手机上「+」打开的操作表，入口列表加底部的模式开关与单轮能力选择。
 *
 * [POS]
 * 手机不显示桌面的选项区（ComposerOptionsRegion），那里的选项在这里以操作表呈现；关闭操作表由入口项自己触发。
 */
import { useTranslations } from 'next-intl';

import AgentIndicator from '@/components/features/message-input-actions/AgentIndicator';
import DeepSearchToggle from '@/components/features/message-input-actions/DeepSearchToggle';
import IncognitoModeToggle from '@/components/features/message-input-actions/IncognitoModeToggle';
import KnowledgePickerPopover from '@/components/features/message-input-actions/KnowledgePickerPopover';
import SecurityPresetSelector from '@/components/features/message-input-actions/SecurityPresetSelector';
import TurnCapabilityToggle from '@/components/features/message-input-actions/TurnCapabilityToggle';
import WorkflowModeToggle from '@/components/features/message-input-actions/WorkflowModeToggle';
import type { TurnCapabilitySelection } from '@/hooks/message-input/turnCapabilityOverrideCore';

import { MobileActionSheet } from '../mobile/MobileActionSheet';
import { useMobileSheetEntries } from '../mobile/useMobileSheetEntries';

interface MobileComposerSheetProps {
  open: boolean;
  onClose: () => void;
  loading: boolean;
  turnCapabilitySelection: TurnCapabilitySelection | null;
  onTurnCapabilityChange: (selection: TurnCapabilitySelection | null) => void;
}

export function MobileComposerSheet({
  open,
  onClose,
  loading,
  turnCapabilitySelection,
  onTurnCapabilityChange,
}: MobileComposerSheetProps) {
  const chatT = useTranslations('chat');
  const entries = useMobileSheetEntries({ onClose });

  return (
    <MobileActionSheet
      open={open}
      onClose={onClose}
      title={chatT('input.expandToolbar')}
      entries={entries}
      footer={
        <>
          <DeepSearchToggle />
          <WorkflowModeToggle />
          <IncognitoModeToggle />
          <SecurityPresetSelector />
          <AgentIndicator />
          <KnowledgePickerPopover />
          <TurnCapabilityToggle
            selection={turnCapabilitySelection}
            onSelectionChange={onTurnCapabilityChange}
            disabled={loading}
          />
        </>
      }
    />
  );
}
