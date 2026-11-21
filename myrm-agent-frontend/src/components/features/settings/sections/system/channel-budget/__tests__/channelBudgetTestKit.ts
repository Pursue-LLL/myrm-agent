/**
 * [INPUT]
 * - @/services/budget (POS: Channel budget API types)
 * - ../useChannelAudit::AUDIT_DAYS (POS: Audit window the toggle label names)
 *
 * [OUTPUT]
 * - CHANNEL_KEY / OTHER_CHANNEL_KEY: two channels a panel test can show side by side
 * - channelStatus / policyOf / auditEntry: the three shapes the panel reads, with the limit of 2 USD a test starts from
 * - stableT: the stand-in for the translator (keys with their values appended, so tests can see what a message was
 *   filled with); one module-level reference, as `verify:stable-mocks` requires
 * - AUDIT_TOGGLE / trashName: what the stand-in translator makes of the audit toggle's text and of a channel's trash button name
 * - nextTick: lets every promise already queued settle
 *
 * [POS]
 * Shared fixtures of the channel budget panel tests. The `vi.mock` calls stay in each test file, where vitest hoists them.
 */
import type { ChannelAuditEntry, ChannelBudgetPolicy, ChannelBudgetStatus } from '@/services/budget';
import { AUDIT_DAYS } from '../useChannelAudit';

export const CHANNEL_KEY = 'telegram:group:g-1';
export const OTHER_CHANNEL_KEY = 'telegram:group:g-2';

export const stableT = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}|${Object.values(values).join(',')}` : key;

/** The text of the audit toggle of a channel. */
export const AUDIT_TOGGLE = `auditDetails|${AUDIT_DAYS}`;

/** The accessible name of the trash button of the channel called `name`. */
export const trashName = (name: string) => `deleteNamed|${name}`;

/** A channel whose group has a chat on record, unless `known` says it has none yet. */
export const channelStatus = (
  todayCostUsd: number,
  channelKey = CHANNEL_KEY,
  label = '',
  known = true,
): ChannelBudgetStatus => ({
  channel_key: channelKey,
  label,
  enabled: true,
  daily_limit_usd: 2,
  today_cost_usd: todayCostUsd,
  remaining_usd: Math.max(2 - todayCostUsd, 0),
  usage_pct: (todayCostUsd / 2) * 100,
  status: 'ok',
  known,
});

export const policyOf = (dailyLimitUsd: number, channelKey = CHANNEL_KEY, label = ''): ChannelBudgetPolicy => ({
  channel_key: channelKey,
  daily_limit_usd: dailyLimitUsd,
  warning_threshold: 0.8,
  enabled: true,
  label,
});

export const auditEntry = (senderId: string, totalCostUsd: number): ChannelAuditEntry => ({
  sender_id: senderId,
  message_count: 3,
  total_cost_usd: totalCostUsd,
});

/** Lets every promise already queued settle, so a test can look at the screen after a save has fully finished. */
export const nextTick = () => new Promise<void>((resolve) => setTimeout(resolve, 0));
