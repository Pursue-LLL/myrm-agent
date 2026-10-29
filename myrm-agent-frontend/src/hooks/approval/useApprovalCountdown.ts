/**
 * [INPUT]
 * - expiresAt: 审批到期的 Unix 秒时间戳
 * - timeoutSeconds: 审批的总时长（秒），用来换算进度
 *
 * [OUTPUT]
 * - useApprovalCountdown: 每秒刷新的剩余秒数，以及是否已过期、是否进入最后 10 秒、进度百分比
 *
 * [POS]
 * 审批卡倒计时的状态来源；只负责计时，不决定过期后做什么。
 */

import { useEffect, useState } from 'react';

const URGENT_SECONDS = 10;

export function useApprovalCountdown(expiresAt: number, timeoutSeconds: number) {
  const [remainingSeconds, setRemainingSeconds] = useState(0);

  useEffect(() => {
    const update = () => {
      setRemainingSeconds(Math.max(0, Math.floor((expiresAt * 1000 - Date.now()) / 1000)));
    };
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [expiresAt]);

  return {
    remainingSeconds,
    isExpired: remainingSeconds <= 0,
    isUrgent: remainingSeconds > 0 && remainingSeconds <= URGENT_SECONDS,
    progressPercent: Math.max(0, (remainingSeconds / timeoutSeconds) * 100),
  };
}
