import type { CreateCronJobRequest, CronSchedule } from '@/services/cron';
import type { LucideIcon } from 'lucide-react';
import { Sun, ClipboardList, Bell, Newspaper, Moon } from 'lucide-react';

// ==================== Types ====================

export interface BlueprintSlot {
  name: string;
  type: 'time' | 'text' | 'enum';
  label: string;
  default: string;
  options?: string[];
}

export interface CronBlueprint {
  id: string;
  icon: LucideIcon;
  titleKey: string;
  descKey: string;
  promptKey: string;
  slots: BlueprintSlot[];
  buildSchedule: (values: Record<string, string>) => CronSchedule;
  buildPrompt: (values: Record<string, string>, t: (key: string, params?: Record<string, string>) => string) => string;
}

// ==================== Blueprints ====================

export const CRON_BLUEPRINTS: readonly CronBlueprint[] = [
  {
    id: 'morning_briefing',
    icon: Sun,
    titleKey: 'blueprint.morningBriefing.title',
    descKey: 'blueprint.morningBriefing.desc',
    promptKey: 'blueprint.morningBriefing.prompt',
    slots: [
      { name: 'time', type: 'time', label: 'blueprint.slotTime', default: '08:00' },
      {
        name: 'weekdays',
        type: 'enum',
        label: 'blueprint.slotWeekdays',
        default: 'everyday',
        options: ['everyday', 'weekdays', 'weekends'],
      },
    ],
    buildSchedule: (v) => ({
      kind: 'cron',
      expr: timeToCronWithWeekdays(v.time || '08:00', v.weekdays || 'everyday'),
    }),
    buildPrompt: (_v, t) => t('blueprint.morningBriefing.prompt'),
  },
  {
    id: 'weekly_review',
    icon: ClipboardList,
    titleKey: 'blueprint.weeklyReview.title',
    descKey: 'blueprint.weeklyReview.desc',
    promptKey: 'blueprint.weeklyReview.prompt',
    slots: [
      { name: 'time', type: 'time', label: 'blueprint.slotTime', default: '18:00' },
      {
        name: 'day',
        type: 'enum',
        label: 'blueprint.slotDay',
        default: '5',
        options: ['1', '2', '3', '4', '5', '6', '0'],
      },
    ],
    buildSchedule: (v) => ({
      kind: 'cron',
      expr: timeToCronWeekday(v.time || '18:00', v.day || '5'),
    }),
    buildPrompt: (_v, t) => t('blueprint.weeklyReview.prompt'),
  },
  {
    id: 'custom_reminder',
    icon: Bell,
    titleKey: 'blueprint.customReminder.title',
    descKey: 'blueprint.customReminder.desc',
    promptKey: 'blueprint.customReminder.prompt',
    slots: [
      { name: 'time', type: 'time', label: 'blueprint.slotTime', default: '09:00' },
      { name: 'message', type: 'text', label: 'blueprint.slotMessage', default: '' },
    ],
    buildSchedule: (v) => ({
      kind: 'cron',
      expr: timeToCron(v.time || '09:00'),
    }),
    buildPrompt: (v, t) => v.message || t('blueprint.customReminder.prompt'),
  },
  {
    id: 'news_digest',
    icon: Newspaper,
    titleKey: 'blueprint.newsDigest.title',
    descKey: 'blueprint.newsDigest.desc',
    promptKey: 'blueprint.newsDigest.prompt',
    slots: [
      { name: 'time', type: 'time', label: 'blueprint.slotTime', default: '07:30' },
      {
        name: 'weekdays',
        type: 'enum',
        label: 'blueprint.slotWeekdays',
        default: 'everyday',
        options: ['everyday', 'weekdays', 'weekends'],
      },
      {
        name: 'topic',
        type: 'text',
        label: 'blueprint.slotTopic',
        default: 'AI and technology',
      },
    ],
    buildSchedule: (v) => ({
      kind: 'cron',
      expr: timeToCronWithWeekdays(v.time || '07:30', v.weekdays || 'everyday'),
    }),
    buildPrompt: (v, t) => t('blueprint.newsDigest.prompt', { topic: v.topic || 'AI and technology' }),
  },
  {
    id: 'evening_winddown',
    icon: Moon,
    titleKey: 'blueprint.eveningWinddown.title',
    descKey: 'blueprint.eveningWinddown.desc',
    promptKey: 'blueprint.eveningWinddown.prompt',
    slots: [
      { name: 'time', type: 'time', label: 'blueprint.slotTime', default: '21:00' },
      {
        name: 'weekdays',
        type: 'enum',
        label: 'blueprint.slotWeekdays',
        default: 'everyday',
        options: ['everyday', 'weekdays', 'weekends'],
      },
    ],
    buildSchedule: (v) => ({
      kind: 'cron',
      expr: timeToCronWithWeekdays(v.time || '21:00', v.weekdays || 'everyday'),
    }),
    buildPrompt: (_v, t) => t('blueprint.eveningWinddown.prompt'),
  },
];

// ==================== Helpers ====================

function timeToCron(time: string): string {
  const [h, m] = time.split(':').map(Number);
  return `${m} ${h} * * *`;
}

function timeToCronWeekday(time: string, day: string): string {
  const [h, m] = time.split(':').map(Number);
  return `${m} ${h} * * ${day}`;
}

function timeToCronWithWeekdays(time: string, weekdays: string): string {
  const [h, m] = time.split(':').map(Number);
  const dow = weekdays === 'weekdays' ? '1-5' : weekdays === 'weekends' ? '0,6' : '*';
  return `${m} ${h} * * ${dow}`;
}

const WEEKDAY_KEYS: Record<string, string> = {
  '0': 'Sun',
  '1': 'Mon',
  '2': 'Tue',
  '3': 'Wed',
  '4': 'Thu',
  '5': 'Fri',
  '6': 'Sat',
};

export function humanizeSchedule(schedule: CronSchedule): string {
  if (schedule.kind === 'once') {
    return schedule.run_at ? new Date(schedule.run_at).toLocaleString() : 'Once';
  }
  if (schedule.kind === 'interval') {
    const mins = (schedule.interval_ms ?? 0) / 60_000;
    return `Every ${mins} min`;
  }
  if (!schedule.expr) return '';
  const parts = schedule.expr.trim().split(/\s+/);
  if (parts.length < 5) return schedule.expr;
  const [min, hour, , , dow] = parts;
  const time = `${hour.padStart(2, '0')}:${min.padStart(2, '0')}`;
  if (dow === '*') return `Daily at ${time}`;
  if (dow === '1-5') return `Weekdays at ${time}`;
  if (dow === '0,6') return `Weekends at ${time}`;
  const dayNames = dow
    .split(',')
    .map((d) => WEEKDAY_KEYS[d] ?? d)
    .join(', ');
  return `${dayNames} at ${time}`;
}

export function buildJobPayload(
  blueprint: CronBlueprint,
  values: Record<string, string>,
  tz: string,
  t: (key: string, params?: Record<string, string>) => string,
  delivery?: { channel: string; target?: string },
): CreateCronJobRequest {
  const schedule = blueprint.buildSchedule(values);
  schedule.tz = tz;
  const prompt = blueprint.buildPrompt(values, t);
  return {
    name: prompt.slice(0, 40),
    job_type: 'agent',
    schedule,
    prompt,
    session_target: 'isolated',
    ...(delivery && delivery.channel !== 'chat' ? { delivery } : {}),
  };
}

// ==================== Cron Presets ====================

export interface CronPreset {
  id: string;
  labelKey: string;
  expr: string;
}

export const CRON_PRESETS: readonly CronPreset[] = [
  { id: 'every_hour', labelKey: 'preset.everyHour', expr: '0 * * * *' },
  { id: 'daily_8am', labelKey: 'preset.daily8am', expr: '0 8 * * *' },
  { id: 'daily_9am', labelKey: 'preset.daily9am', expr: '0 9 * * *' },
  { id: 'weekdays_9am', labelKey: 'preset.weekdays9am', expr: '0 9 * * 1-5' },
  { id: 'weekly_monday', labelKey: 'preset.weeklyMonday', expr: '0 9 * * 1' },
  { id: 'monthly_first', labelKey: 'preset.monthlyFirst', expr: '0 9 1 * *' },
];
