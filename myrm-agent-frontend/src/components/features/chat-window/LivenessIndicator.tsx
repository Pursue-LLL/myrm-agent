'use client';

/**
 * [INPUT]
 * - @/hooks/useLivenessState::useLivenessState (POS: 全局 Agent liveness SSOT 五态轮询)
 *
 * [OUTPUT]
 * - LivenessIndicator: 6px 圆点状态灯，idle 时隐藏，非 idle 时显示颜色 + i18n tooltip。
 *
 * [POS]
 * 聊天输入区 Agent 状态指示灯。消费 useLivenessState 五态，
 * 以最小视觉占用反馈 Agent 运行状态。
 */
import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { useLivenessState, type LivenessState } from '@/hooks/useLivenessState';

const DOT_COLOR: Record<LivenessState, string> = {
  idle: 'bg-emerald-500',
  busy: 'bg-amber-500',
  degraded: 'bg-red-400',
  draining: 'bg-orange-400',
  offline: 'bg-red-600',
};

const LivenessIndicator = memo(() => {
  const t = useTranslations('chat.liveness');
  const { state } = useLivenessState();

  if (state === 'idle') return null;

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${DOT_COLOR[state]} ${state === 'busy' ? 'animate-pulse' : ''}`}
            aria-label={t(state)}
          />
        </TooltipTrigger>
        <TooltipContent side="top" className="text-xs">
          {t(state)}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
});

LivenessIndicator.displayName = 'LivenessIndicator';
export default LivenessIndicator;
