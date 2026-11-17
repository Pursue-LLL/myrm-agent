/**
 * [INPUT] 无外部依赖（纯函数与常量）
 * [OUTPUT] INTERVAL_OPTIONS / HOUR_OPTIONS / MINUTE_OPTIONS: 间隔与时刻下拉选项; DAY_PRESETS / DayPreset: 星期预设; parseCronExpr / buildCronExpr: 预设与 cron 表达式互转; getSystemTimezone: 浏览器时区
 * [POS] 心跳设置的调度选项与 cron 互转（纯逻辑，无 React）：每天、工作日、周末三个预设对应 cron 的星期字段；表达式解析不出时回到每天 09:00，浏览器取不到时区时用 UTC。
 */

export const INTERVAL_OPTIONS = [
  { value: '900000', labelKey: '15min' },
  { value: '1800000', labelKey: '30min' },
  { value: '3600000', labelKey: '1h' },
  { value: '7200000', labelKey: '2h' },
  { value: '14400000', labelKey: '4h' },
] as const;

export const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => ({
  value: String(i),
  label: String(i).padStart(2, '0'),
}));

export const MINUTE_OPTIONS = [
  { value: '0', label: '00' },
  { value: '15', label: '15' },
  { value: '30', label: '30' },
  { value: '45', label: '45' },
];

export type DayPreset = 'everyday' | 'weekdays' | 'weekends';

export const DAY_PRESETS: DayPreset[] = ['everyday', 'weekdays', 'weekends'];

function dayPresetToCronDow(preset: DayPreset): string {
  switch (preset) {
    case 'everyday':
      return '*';
    case 'weekdays':
      return '1-5';
    case 'weekends':
      return '0,6';
  }
}

function cronDowToPreset(dow: string): DayPreset {
  if (dow === '1-5') {
    return 'weekdays';
  }
  if (dow === '0,6' || dow === '6,0') {
    return 'weekends';
  }
  return 'everyday';
}

export function parseCronExpr(expr: string): { hour: string; minute: string; dayPreset: DayPreset } {
  const parts = expr.split(/\s+/);
  if (parts.length < 5) {
    return { hour: '9', minute: '0', dayPreset: 'everyday' };
  }
  return {
    minute: parts[0] ?? '0',
    hour: parts[1] ?? '9',
    dayPreset: cronDowToPreset(parts[4] ?? '*'),
  };
}

export function buildCronExpr(hour: string, minute: string, dayPreset: DayPreset): string {
  return `${minute} ${hour} * * ${dayPresetToCronDow(dayPreset)}`;
}

export function getSystemTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return 'UTC';
  }
}
