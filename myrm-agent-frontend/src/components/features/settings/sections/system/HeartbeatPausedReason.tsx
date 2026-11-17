'use client';

/**
 * [INPUT] @/components/features/cron/cron-utils::pauseReasonLabelKey (POS: 定时任务的标签 key 与纯函数), @/services/cron::PauseReason (POS: 调度器自行暂停的原因类型)
 * [OUTPUT] HeartbeatPausedReason: 心跳被调度器自行暂停的原因
 * [POS] 心跳设置开关下的一行：开关关着、又不是用户关的时候，用定时任务的暂停原因词说明为什么。
 */

import { useTranslations } from 'next-intl';
import { pauseReasonLabelKey } from '@/components/features/cron/cron-utils';
import type { PauseReason } from '@/services/cron';

interface HeartbeatPausedReasonProps {
  reason: PauseReason;
}

export default function HeartbeatPausedReason({ reason }: HeartbeatPausedReasonProps) {
  const t = useTranslations('cron');
  return <p className="text-xs text-destructive-text">{t(pauseReasonLabelKey(reason))}</p>;
}
