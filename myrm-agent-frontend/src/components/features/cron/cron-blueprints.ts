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
): Promise<{ schedule: CronSchedule; prompt: string; name: string }> {
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
    job_type: 'agent',
    schedule: filled.schedule,
    prompt: filled.prompt,
    session_target: 'isolated',
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
