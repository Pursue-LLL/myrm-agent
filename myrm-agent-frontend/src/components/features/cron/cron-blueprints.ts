import type { BlueprintDef, BlueprintFillResponse, CreateCronJobRequest, CronSchedule } from '@/services/cron';
import { fillBlueprint, listBlueprints } from '@/services/cron';
import type { LucideIcon } from 'lucide-react';
import { Sun, ClipboardList, Bell, Newspaper, Moon, Sparkles, Activity, Eye, CheckSquare, BookOpen, Radio } from 'lucide-react';
import { formatTime } from './cron-utils';

/** Locale-aware translation function compatible with next-intl `useTranslations`. */
export type ScheduleT = (key: string, values?: Record<string, string | number>) => string;

// ==================== Types ====================

export interface BlueprintSlot {
  name: string;
  type: 'time' | 'text' | 'enum';
  label: string;
  default: string;
  options?: string[];
  optional?: boolean;
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
  asset: 'blueprint.slotAsset',
  quote_currency: 'blueprint.slotQuoteCurrency',
  lower_bound: 'blueprint.slotLowerBound',
  upper_bound: 'blueprint.slotUpperBound',
  source: 'blueprint.slotSource',
  watchlist: 'blueprint.slotWatchlist',
  signal_rules: 'blueprint.slotSignalRules',
  portfolio_context: 'blueprint.slotPortfolioContext',
};

export function resolveBlueprintSlotLabel(slotName: string): string {
  const mapped = BLUEPRINT_SLOT_LABEL_KEYS[slotName];
  if (mapped) {return mapped;}
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
      optional: s.optional ?? false,
    })),
    title: def.title,
    description: def.description,
    buildSchedule: (v) => buildScheduleFromSlots(def, v),
  };
}

/** Preview-only schedule builder; catalog data comes from server API defs. */
export function buildScheduleFromSlots(def: BlueprintDef, values: Record<string, string>): CronSchedule {
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

/**
 * Load blueprints from the server API (cached after first load).
 * Throws on network or server errors — no fake offline catalog.
 */
export async function loadBlueprints(): Promise<CronBlueprint[]> {
  if (_cachedBlueprints) {return _cachedBlueprints;}

  if (!_loadingPromise) {
    _loadingPromise = listBlueprints()
      .then((defs) => {
        const blueprints = defs
          .sort((a, b) => a.sort_order - b.sort_order)
          .map(buildBlueprintFromDef);
        _cachedBlueprints = blueprints;
        return blueprints;
      })
      .finally(() => {
        _loadingPromise = null;
      });
  }

  return _loadingPromise;
}

/** Get cached blueprints synchronously (empty until first successful load). */
export function getCachedBlueprints(): readonly CronBlueprint[] {
  return _cachedBlueprints ?? [];
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
 * Fill a blueprint via POST /cron/blueprints/fill (server SSOT).
 */
export async function fillBlueprintFromServer(
  blueprintId: string,
  values: Record<string, string>,
  tz: string,
  locale: string,
): Promise<BlueprintFillResponse> {
  return fillBlueprint(blueprintId, values, locale, tz);
}

/**
 * Build a create-job payload from blueprint slots via server fill (SSOT).
 */
export async function buildBlueprintCreatePayload(
  blueprint: CronBlueprint,
  values: Record<string, string>,
  tz: string,
  locale: string,
  delivery?: { channel: string; target?: string },
): Promise<CreateCronJobRequest> {
  const filled = await fillBlueprintFromServer(blueprint.id, values, tz, locale);
  return {
    name: filled.name,
    job_type: filled.job_type,
    schedule: filled.schedule,
    prompt: filled.prompt,
    session_target: filled.session_target,
    ...(filled.required_capabilities.length > 0
      ? { required_capabilities: filled.required_capabilities }
      : {}),
    ...(filled.tools_allowed.length > 0 ? { tools_allowed: filled.tools_allowed } : {}),
    ...(filled.deduplicate ? { deduplicate: true } : {}),
    ...(filled.skip_if_active ? { skip_if_active: true } : {}),
    ...(typeof filled.timeout_seconds === 'number' ? { timeout_seconds: filled.timeout_seconds } : {}),
    ...(filled.monitor_config ? { monitor_config: filled.monitor_config } : {}),
    ...(filled.failure_alert ? { failure_alert: filled.failure_alert } : {}),
    ...(filled.pre_condition_script !== null && filled.pre_condition_script !== undefined
      ? { pre_condition_script: filled.pre_condition_script }
      : {}),
    ...(filled.command !== null && filled.command !== undefined ? { command: filled.command } : {}),
    ...(delivery && delivery.channel !== 'chat' ? { delivery } : {}),
  };
}

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
  '0': 'daySun',
  '1': 'dayMon',
  '2': 'dayTue',
  '3': 'dayWed',
  '4': 'dayThu',
  '5': 'dayFri',
  '6': 'daySat',
};

/**
 * Humanize a schedule for preview text, e.g. "Daily at 08:00", "Weekdays at 09:30",
 * "Mon, Wed at 09:00", "Every 60 min", or "Once at <localized time>".
 *
 * All copy resolves through the `cron` namespace (`schedule.*` keys); weekday names
 * reuse the existing `blueprint.day*` keys. Locale is threaded through so the once
 * branch renders consistently between SSR and CSR.
 */
export function humanizeSchedule(schedule: CronSchedule, t: ScheduleT, locale: string): string {
  if (schedule.kind === 'once') {
    return schedule.run_at
      ? t('schedule.onceAt', { time: formatTime(schedule.run_at, locale) })
      : t('schedule.once');
  }
  if (schedule.kind === 'interval') {
    const mins = (schedule.interval_ms ?? 0) / 60_000;
    return t('schedule.everyMinutes', { count: mins });
  }
  if (!schedule.expr) {return '';}
  const parts = schedule.expr.trim().split(/\s+/);
  // Cron expressions with anything other than the standard 5 fields (e.g. a
  // 6/7-field form with seconds or year) have positional meaning we do not
  // model — humanizing by destructuring the first five would silently drop
  // fields and mislead. Fall back to the raw expression.
  if (parts.length !== 5) {return schedule.expr;}
  const [min, hour, dom, mon, dow] = parts;
  const time = `${hour.padStart(2, '0')}:${min.padStart(2, '0')}`;
  // Only interpret the day-of-week position when the date fields are unrestricted —
  // a constrained day-of-month/month (e.g. monthly `0 9 1 * *`, yearly) is not a
  // daily/weekday/weekend cadence and must not be mislabeled as one.
  if (dom !== '*' || mon !== '*') {return schedule.expr;}
  if (dow === '*') {return t('schedule.dailyAt', { time });}
  if (dow === '1-5') {return t('schedule.weekdaysAt', { time });}
  if (dow === '0,6') {return t('schedule.weekendsAt', { time });}
  const dayKeys = dow
    .split(',')
    .map((d) => WEEKDAY_KEYS[d] ?? '');
  // If any day-of-week segment uses an expression form we cannot map (e.g. a range
  // like `1-3`), fall back to the full cron expression — partial fragments would
  // drop fields and may embed untranslated glue words.
  if (dayKeys.some((k) => !k)) {return schedule.expr;}
  const dayNames = dayKeys.map((k) => t(`blueprint.${k}`)).join(', ');
  return t('schedule.weekdayListAt', { days: dayNames, time });
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
