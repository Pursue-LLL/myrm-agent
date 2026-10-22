/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Consistent vector icons)
 * - @/components/features/chat-window/token-economics/tokenEconomicsTypes
 * - @/components/features/chat-window/token-economics/tokenEconomicsEngine
 * - @/components/features/chat-window/token-economics/useTokenEconomicsStore
 *
 * [OUTPUT]
 * - SessionTokenCapsule (POS: Lightweight token metering and cost estimation capsule badge)
 *
 * [POS]
 * Primary header/toolbar capsule for Item 193 (P1).
 * Displays real-time session tokens and currency cost projections,
 * with quick entry to the provider balance probe modal.
 */

import React, { useState } from 'react';
import {
  Coins,
  Cpu,
  Wallet,
  ChevronDown,
  Info,
} from 'lucide-react';
import { useTokenEconomicsStore } from './useTokenEconomicsStore';
import { formatTokenCount } from './tokenEconomicsEngine';

export interface SessionTokenCapsuleProps {
  readonly chatId?: string;
  readonly compact?: boolean;
  readonly className?: string;
  readonly onOpenBalanceModal?: () => void;
}

export const SessionTokenCapsule: React.FC<SessionTokenCapsuleProps> = ({
  chatId,
  compact = false,
  className = '',
  onOpenBalanceModal,
}) => {
  const activeChatId = useTokenEconomicsStore((state) => state.activeChatId);
  const sessionSnapshots = useTokenEconomicsStore((state) => state.sessionSnapshots);
  const toggleBalanceModal = useTokenEconomicsStore((state) => state.toggleBalanceModal);

  const [isTooltipOpen, setIsTooltipOpen] = useState<boolean>(false);

  const targetChatId = chatId ?? activeChatId;
  const snapshot = targetChatId ? sessionSnapshots[targetChatId] : undefined;

  const totalTokens = snapshot?.usage.totalTokens ?? 0;
  const formattedCost = snapshot?.costEstimate.formattedCost ?? '¥0.00';
  const promptTokens = snapshot?.usage.promptTokens ?? 0;
  const completionTokens = snapshot?.usage.completionTokens ?? 0;
  const modelName = snapshot?.modelId ?? '默认模型';

  const handleOpenBalance = () => {
    if (onOpenBalanceModal) {
      onOpenBalanceModal();
    } else {
      toggleBalanceModal(true);
    }
  };

  return (
    <div
      className={`relative inline-flex items-center ${className}`}
      onMouseEnter={() => {
        setIsTooltipOpen(true);
      }}
      onMouseLeave={() => {
        setIsTooltipOpen(false);
      }}
    >
      <button
        type="button"
        onClick={handleOpenBalance}
        data-testid="session-token-capsule-button"
        title="查看会话 Token 用量与 Provider 账户余额"
        aria-label="查看会话 Token 用量与 Provider 账户余额"
        className="inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-muted/40 hover:bg-accent hover:border-accent-foreground/20 px-2.5 py-1 text-xs font-medium text-foreground transition-all shadow-sm"
      >
        <div className="flex items-center gap-1 text-muted-foreground">
          <Cpu className="w-3.5 h-3.5 text-primary" />
          <span>{formatTokenCount(totalTokens)}</span>
        </div>

        {!compact ? (
          <>
            <span className="text-border">|</span>
            <div className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-mono">
              <Coins className="w-3.5 h-3.5" />
              <span>{formattedCost}</span>
            </div>
          </>
        ) : null}

        <Wallet className="w-3.5 h-3.5 text-muted-foreground/80 hover:text-foreground transition-colors ml-0.5" />
        <ChevronDown className="w-3 h-3 text-muted-foreground/60" />
      </button>

      {/* 悬浮用量明细气泡浮层 */}
      {isTooltipOpen ? (
        <div
          role="tooltip"
          data-testid="token-economics-tooltip"
          className="absolute left-0 top-full mt-2 z-40 w-56 rounded-lg border border-border bg-popover p-3 shadow-lg text-xs animate-in fade-in zoom-in-95 duration-150"
        >
          <div className="flex items-center justify-between border-b border-border/60 pb-1.5 mb-2">
            <span className="font-semibold text-foreground">会话 Token 消耗</span>
            <span className="text-[10px] text-muted-foreground truncate max-w-[90px]">
              {modelName}
            </span>
          </div>

          <div className="space-y-1.5 text-muted-foreground">
            <div className="flex justify-between items-center">
              <span>输入 Prompt:</span>
              <span className="font-mono text-foreground font-medium">
                {promptTokens.toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span>生成 Completion:</span>
              <span className="font-mono text-foreground font-medium">
                {completionTokens.toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between items-center pt-1 border-t border-border/40 font-semibold text-foreground">
              <span>预估费用:</span>
              <span className="font-mono text-emerald-600 dark:text-emerald-400">
                {formattedCost}
              </span>
            </div>
          </div>

          <div className="mt-2.5 pt-2 border-t border-border/40 flex items-center gap-1 text-[11px] text-primary hover:underline cursor-pointer">
            <Info className="w-3 h-3" />
            <span>点击查看 Provider 账户余额自省</span>
          </div>
        </div>
      ) : null}
    </div>
  );
};
