import type { BlueprintDef, CreateCronJobRequest, CronSchedule } from '@/services/cron';
import { fillBlueprint, listBlueprints } from '@/services/cron';
import type { LucideIcon } from 'lucide-react';
import { Sun, ClipboardList, Bell, Newspaper, Moon, Sparkles, Activity, Eye, CheckSquare, BookOpen, Radio } from 'lucide-react';

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
  title: Record<string, string>;
  description: Record<string, string>;
  buildSchedule: (values: Record<string, string>) => CronSchedule;
  buildPrompt: (values: Record<string, string>, t: (key: string, params?: Record<string, string>) => string) => string;
}

// ==================== Icon Registry ====================

const ICON_MAP: Record<string, LucideIcon> = {
  Sun,
  ClipboardList,
  Bell,
  Newspaper,
  Moon,
  Sparkles,
  Activity,
  Eye,
  CheckSquare,
  BookOpen,
  Radio,
};

function resolveIcon(iconName: string): LucideIcon {
  return ICON_MAP[iconName] || Sparkles;
}

/** Server blueprint ids use snake_case; locale keys use camelCase (e.g. custom_reminder → customReminder). */
export function blueprintSnakeToCamel(id: string): string {
  return id.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
}

const BLUEPRINT_SLOT_LABEL_KEYS: Record<string, string> = {
  time: 'blueprint.slotTime',
  day: 'blueprint.slotDay',
  weekdays: 'blueprint.slotWeekdays',
  message: 'blueprint.slotMessage',
  topic: 'blueprint.slotTopic',
  competitors: 'blueprint.slotCompetitors',
  habits: 'blueprint.slotHabits',
  brand: 'blueprint.slotBrand',
  platforms: 'blueprint.slotPlatforms',
  keywords: 'blueprint.slotKeywords',
  subject: 'blueprint.slotSubject',
};

export function resolveBlueprintSlotLabel(slotName: string): string {
  const mapped = BLUEPRINT_SLOT_LABEL_KEYS[slotName];
  if (mapped) return mapped;
  const camel = blueprintSnakeToCamel(slotName);
  return `blueprint.slot${camel.charAt(0).toUpperCase()}${camel.slice(1)}`;
}

export function resolveBlueprintTitleKey(blueprintId: string): string {
  return `blueprint.${blueprintSnakeToCamel(blueprintId)}.title`;
}

export function resolveBlueprintDescKey(blueprintId: string): string {
  return `blueprint.${blueprintSnakeToCamel(blueprintId)}.desc`;
}

export function resolveBlueprintPromptKey(blueprintId: string): string {
  return `blueprint.${blueprintSnakeToCamel(blueprintId)}.prompt`;
}

// ==================== Blueprint Loading ====================

let _cachedBlueprints: CronBlueprint[] | null = null;
let _loadingPromise: Promise<CronBlueprint[]> | null = null;

function buildBlueprintFromDef(def: BlueprintDef): CronBlueprint {
  return {
    id: def.id,
    icon: resolveIcon(def.icon),
    titleKey: resolveBlueprintTitleKey(def.id),
    descKey: resolveBlueprintDescKey(def.id),
    promptKey: resolveBlueprintPromptKey(def.id),
    slots: def.slots.map((s) => ({
      name: s.name,
      type: s.type,
      label: resolveBlueprintSlotLabel(s.name),
      default: s.default,
      options: s.options.length > 0 ? s.options : undefined,
    })),
    title: def.title,
    description: def.description,
    buildSchedule: (v) => buildScheduleFromSlots(def, v),
    buildPrompt: (v, t) => buildPromptFromDef(def, v, t),
  };
}

function buildScheduleFromSlots(def: BlueprintDef, values: Record<string, string>): CronSchedule {
  const time = values.time || '08:00';
  const weekdays = values.weekdays || 'everyday';
  const day = values.day || '5';

  const hasWeekdaysSlot = def.slots.some((s) => s.name === 'weekdays');
  const hasDaySlot = def.slots.some((s) => s.name === 'day');

  if (hasWeekdaysSlot) {
    return { kind: 'cron', expr: timeToCronWithWeekdays(time, weekdays) };
  }
  if (hasDaySlot) {
    return { kind: 'cron', expr: timeToCronWeekday(time, day) };
  }
  return { kind: 'cron', expr: timeToCron(time) };
}

function buildPromptFromDef(
  def: BlueprintDef,
  values: Record<string, string>,
  t: (key: string, params?: Record<string, string>) => string,
): string {
  const locale = typeof window !== 'undefined'
    ? (document.documentElement.lang || 'en').split('-')[0]
    : 'en';
  const template = def.prompt_template[locale] || def.prompt_template.en || '';

  let result = template;
  for (const [key, val] of Object.entries(values)) {
    if (val) result = result.replace(`{${key}}`, val);
  }

  if (result.includes('{message}') && !values.message) {
    const fallback = t(resolveBlueprintPromptKey(def.id));
    return fallback || result.replace('{message}', '');
  }

  return result;
}

/**
 * Load blueprints from the server API (cached after first load).
 * Falls back to hardcoded defaults on network failure.
 */
export async function loadBlueprints(): Promise<CronBlueprint[]> {
  if (_cachedBlueprints) return _cachedBlueprints;

  if (!_loadingPromise) {
    _loadingPromise = listBlueprints()
      .then((defs) => {
        const blueprints = defs
          .sort((a, b) => a.sort_order - b.sort_order)
          .map(buildBlueprintFromDef);
        _cachedBlueprints = blueprints;
        return blueprints;
      })
      .catch(() => {
        _cachedBlueprints = FALLBACK_BLUEPRINTS;
        return FALLBACK_BLUEPRINTS;
      })
      .finally(() => {
        _loadingPromise = null;
      });
  }

  return _loadingPromise;
}

/**
 * Get cached blueprints synchronously (returns fallback if not yet loaded).
 */
export function getCachedBlueprints(): readonly CronBlueprint[] {
  return _cachedBlueprints || FALLBACK_BLUEPRINTS;
}

/**
 * Invalidate blueprint cache (e.g. after locale change).
 */
export function invalidateBlueprintCache(): void {
  _cachedBlueprints = null;
  _loadingPromise = null;
}

// ==================== Server-Powered Fill ====================

/**
 * Fill a blueprint via the server API for guaranteed consistency.
 * Falls back to local computation if the API is unavailable.
 */
export async function fillBlueprintFromServer(
  blueprintId: string,
  values: Record<string, string>,
  tz: string,
  locale?: string,
): Promise<{ schedule: CronSchedule; prompt: string; name: string }> {
  try {
    return await fillBlueprint(blueprintId, values, locale, tz);
  } catch {
    const bp = getCachedBlueprints().find((b) => b.id === blueprintId);
    if (!bp) throw new Error(`Blueprint ${blueprintId} not found`);
    const schedule = bp.buildSchedule(values);
    schedule.tz = tz;
    const prompt = bp.buildPrompt(values, (k) => k);
    return { schedule, prompt, name: prompt.slice(0, 40) };
  }
}

// ==================== Fallback Blueprints (offline resilience) ====================

const FALLBACK_BLUEPRINTS: CronBlueprint[] = [
  {
    id: 'morning_briefing',
    icon: Sun,
    titleKey: 'blueprint.morningBriefing.title',
    descKey: 'blueprint.morningBriefing.desc',
    promptKey: 'blueprint.morningBriefing.prompt',
    title: { en: 'Morning Briefing', zh: '每日早报' },
    description: { en: 'Get a daily briefing on topics you care about', zh: '每天获取你关心的话题简报' },
    slots: [
      { name: 'time', type: 'time', label: resolveBlueprintSlotLabel('time'), default: '08:00' },
      { name: 'weekdays', type: 'enum', label: resolveBlueprintSlotLabel('weekdays'), default: 'everyday', options: ['everyday', 'weekdays', 'weekends'] },
    ],
    buildSchedule: (v) => ({ kind: 'cron', expr: timeToCronWithWeekdays(v.time || '08:00', v.weekdays || 'everyday') }),
    buildPrompt: (_v, t) => t('blueprint.morningBriefing.prompt'),
  },
  {
    id: 'weekly_review',
    icon: ClipboardList,
    titleKey: 'blueprint.weeklyReview.title',
    descKey: 'blueprint.weeklyReview.desc',
    promptKey: 'blueprint.weeklyReview.prompt',
    title: { en: 'Weekly Review', zh: '每周回顾' },
    description: { en: 'Summarize weekly progress and plan ahead', zh: '总结每周进展并规划下周' },
    slots: [
      { name: 'time', type: 'time', label: resolveBlueprintSlotLabel('time'), default: '18:00' },
      { name: 'day', type: 'enum', label: resolveBlueprintSlotLabel('day'), default: '5', options: ['1', '2', '3', '4', '5', '6', '0'] },
    ],
    buildSchedule: (v) => ({ kind: 'cron', expr: timeToCronWeekday(v.time || '18:00', v.day || '5') }),
    buildPrompt: (_v, t) => t('blueprint.weeklyReview.prompt'),
  },
  {
    id: 'custom_reminder',
    icon: Bell,
    titleKey: 'blueprint.customReminder.title',
    descKey: 'blueprint.customReminder.desc',
    promptKey: 'blueprint.customReminder.prompt',
    title: { en: 'Custom Reminder', zh: '自定义提醒' },
    description: { en: 'Set a recurring reminder with your own message', zh: '设置一个自定义消息的定期提醒' },
    slots: [
      { name: 'time', type: 'time', label: resolveBlueprintSlotLabel('time'), default: '09:00' },
      { name: 'message', type: 'text', label: resolveBlueprintSlotLabel('message'), default: '' },
    ],
    buildSchedule: (v) => ({ kind: 'cron', expr: timeToCron(v.time || '09:00') }),
    buildPrompt: (v, t) => v.message || t('blueprint.customReminder.prompt'),
  },
  {
    id: 'news_digest',
    icon: Newspaper,
    titleKey: 'blueprint.newsDigest.title',
    descKey: 'blueprint.newsDigest.desc',
    promptKey: 'blueprint.newsDigest.prompt',
    title: { en: 'News Digest', zh: '新闻摘要' },
    description: { en: 'Get a curated digest on your chosen topics', zh: '获取你选择的话题的精选摘要' },
    slots: [
      { name: 'time', type: 'time', label: resolveBlueprintSlotLabel('time'), default: '07:30' },
      { name: 'weekdays', type: 'enum', label: resolveBlueprintSlotLabel('weekdays'), default: 'everyday', options: ['everyday', 'weekdays', 'weekends'] },
      { name: 'topic', type: 'text', label: resolveBlueprintSlotLabel('topic'), default: 'AI and technology' },
    ],
    buildSchedule: (v) => ({ kind: 'cron', expr: timeToCronWithWeekdays(v.time || '07:30', v.weekdays || 'everyday') }),
    buildPrompt: (v, t) => t('blueprint.newsDigest.prompt', { topic: v.topic || 'AI and technology' }),
  },
  {
    id: 'evening_winddown',
    icon: Moon,
    titleKey: 'blueprint.eveningWinddown.title',
    descKey: 'blueprint.eveningWinddown.desc',
    promptKey: 'blueprint.eveningWinddown.prompt',
    title: { en: 'Evening Wind-down', zh: '晚间放松' },
    description: { en: 'End your day with a calming summary', zh: '以平静的总结结束一天' },
    slots: [
      { name: 'time', type: 'time', label: resolveBlueprintSlotLabel('time'), default: '21:00' },
      { name: 'weekdays', type: 'enum', label: resolveBlueprintSlotLabel('weekdays'), default: 'everyday', options: ['everyday', 'weekdays', 'weekends'] },
    ],
    buildSchedule: (v) => ({ kind: 'cron', expr: timeToCronWithWeekdays(v.time || '21:00', v.weekdays || 'everyday') }),
    buildPrompt: (_v, t) => t('blueprint.eveningWinddown.prompt'),
  },
];

// ==================== CRON_BLUEPRINTS (backward-compat sync export) ====================

export const CRON_BLUEPRINTS: readonly CronBlueprint[] = FALLBACK_BLUEPRINTS;

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
