'use client';

/**
 * [INPUT]
 * - @/components/billing/{WorkUnitBalanceBar,SessionSpendSurface} (POS: 余额与本会话花费)
 * - @/components/features/message-box/ContextUsageIndicator (POS: 上下文用量)
 * - @/components/features/message-input-actions/{ReadinessBadge,EnvironmentShield} (POS: 就绪度与运行环境防护)
 * - ../{LivenessIndicator,BudgetBadge,RealTimeCostAndCacheHud} (POS: Agent 状态灯、预算与实时成本)
 *
 * [OUTPUT]
 * - ComposerStatusIndicators: 输入区右侧发送按钮前的状态指示簇。
 *
 * [POS]
 * 只读的状态指示，没有输入。手机上整簇限宽并可横向滚动，环境防护、预算与实时成本三项只在桌面显示。
 */
import SessionSpendSurface from '@/components/billing/SessionSpendSurface';
import WorkUnitBalanceBar from '@/components/billing/WorkUnitBalanceBar';
import ContextUsageIndicator from '@/components/features/message-box/ContextUsageIndicator';
import EnvironmentShield from '@/components/features/message-input-actions/EnvironmentShield';
import ReadinessBadge from '@/components/features/message-input-actions/ReadinessBadge';

import BudgetBadge from '../BudgetBadge';
import LivenessIndicator from '../LivenessIndicator';
import { RealTimeCostAndCacheHud } from '../RealTimeCostAndCacheHud';

export function ComposerStatusIndicators() {
  return (
    <div className="flex items-center gap-1 overflow-x-auto max-w-[45vw] sm:max-w-none">
      <WorkUnitBalanceBar compact className="shrink-0" />
      <SessionSpendSurface className="shrink-0" />
      <ContextUsageIndicator />
      <ReadinessBadge />
      <LivenessIndicator />
      <div className="hidden sm:flex items-center gap-1">
        <EnvironmentShield />
        <BudgetBadge />
        <RealTimeCostAndCacheHud />
      </div>
    </div>
  );
}
