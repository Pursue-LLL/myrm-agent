/**
 * [INPUT]
 * - next-intl::useTranslations (POS: Internationalization hook; only its translator type is used)
 *
 * [OUTPUT]
 * - formatDueWindow: how far the earliest due time of a follow-up is from now, in the user's language
 *
 * [POS]
 * Gives each follow-up card its "due in 3 hours" / "overdue 2 days" caption. The distance is rounded to whole hours
 * first, so anything under half an hour reads as "under 1 hour", and from 24 hours on the caption switches to days.
 */

import type { useTranslations } from 'next-intl';

type FollowUpsTranslator = ReturnType<typeof useTranslations<'followUps'>>;

const HOUR_MS = 60 * 60 * 1000;
const HOURS_PER_DAY = 24;

export function formatDueWindow(earliestMs: number, nowMs: number, t: FollowUpsTranslator): string {
  const diffMs = earliestMs - nowMs;
  const hours = Math.abs(Math.round(diffMs / HOUR_MS));

  if (diffMs < 0) {
    if (hours < 1) {
      return t('dueWindow.overdueUnderOneHour');
    }
    return hours < HOURS_PER_DAY
      ? t('dueWindow.overdueHours', { count: hours })
      : t('dueWindow.overdueDays', { count: Math.round(hours / HOURS_PER_DAY) });
  }
  if (hours < 1) {
    return t('dueWindow.underOneHour');
  }
  return hours < HOURS_PER_DAY
    ? t('dueWindow.inHours', { count: hours })
    : t('dueWindow.inDays', { count: Math.round(hours / HOURS_PER_DAY) });
}
