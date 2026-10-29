'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: toolApproval 文案)
 * - useApprovalCountdown 的计时结果（POS: 剩余秒数、是否过期/紧迫、进度）
 *
 * [OUTPUT]
 * - ApprovalCountdown: 审批卡底部的「剩余时间」文字与进度条，最后 10 秒转红
 *
 * [POS]
 * 审批卡倒计时的展示层，计时本身在 hooks/approval/useApprovalCountdown。
 */

import { Clock } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Progress } from '@/components/primitives/progress';

interface ApprovalCountdownProps {
  remainingSeconds: number;
  isExpired: boolean;
  isUrgent: boolean;
  progressPercent: number;
}

export default function ApprovalCountdown({
  remainingSeconds,
  isExpired,
  isUrgent,
  progressPercent,
}: ApprovalCountdownProps) {
  const t = useTranslations('toolApproval');

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <Clock className={`h-3 w-3 ${isUrgent ? 'text-destructive animate-pulse' : ''}`} />
        <span className={isUrgent ? 'text-destructive font-medium' : ''}>
          {isExpired ? t('expired') : t('expiresIn', { seconds: remainingSeconds })}
        </span>
      </div>
      <Progress value={progressPercent} className={`h-1 ${isUrgent ? '[&>div]:bg-destructive' : ''}`} />
    </div>
  );
}
