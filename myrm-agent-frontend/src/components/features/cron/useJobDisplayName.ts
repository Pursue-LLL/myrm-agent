'use client';

/**
 * [INPUT] ./cron-utils::HEARTBEAT_JOB_NAME (POS: 心跳任务的保留存储名), next-intl `heartbeat.title` (POS: 心跳的用户可读名称)
 * [OUTPUT] useJobDisplayName: 任务存储名 → 用户认识的名称
 * [POS] 展示任务名的统一出口：系统任务的存储名是保留名、并非用户所起，展示时换成它的标题；其余任务原样显示。
 */

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { HEARTBEAT_JOB_NAME } from './cron-utils';

export function useJobDisplayName(): (name: string) => string {
  const tHeartbeat = useTranslations('heartbeat');
  return useCallback((name: string) => (name === HEARTBEAT_JOB_NAME ? tHeartbeat('title') : name), [tHeartbeat]);
}
