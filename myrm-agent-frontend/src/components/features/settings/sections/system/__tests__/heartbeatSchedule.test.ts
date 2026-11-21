/**
 * [INPUT]
 * ../heartbeatSchedule::{buildCronExpr, parseCronExpr, getSystemTimezone, DAY_PRESETS} (POS: 心跳设置的调度选项与 cron 互转)
 * [OUTPUT]
 * Vitest: 星期预设写进 cron 的星期字段并能原样读回；解析不出时回到每天 09:00；取不到浏览器时区时用 UTC。
 * [POS]
 * 心跳设置里「选了什么就存什么」的回归保护：预设与 cron 表达式互转出错会让保存下来的巡检时刻与界面显示不一致。
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildCronExpr, DAY_PRESETS, getSystemTimezone, parseCronExpr } from '../heartbeatSchedule';

describe('heartbeatSchedule', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('writes each day preset into the cron weekday field', () => {
    expect(buildCronExpr('9', '0', 'everyday')).toBe('0 9 * * *');
    expect(buildCronExpr('21', '30', 'weekdays')).toBe('30 21 * * 1-5');
    expect(buildCronExpr('8', '15', 'weekends')).toBe('15 8 * * 0,6');
  });

  it('reads back what it wrote, for every preset', () => {
    for (const dayPreset of DAY_PRESETS) {
      expect(parseCronExpr(buildCronExpr('7', '45', dayPreset))).toEqual({ hour: '7', minute: '45', dayPreset });
    }
  });

  it('reads a weekend written either way round', () => {
    expect(parseCronExpr('0 9 * * 6,0').dayPreset).toBe('weekends');
  });

  it('falls back to every day at 09:00 when the expression has fewer than five fields', () => {
    expect(parseCronExpr('0 9')).toEqual({ hour: '9', minute: '0', dayPreset: 'everyday' });
  });

  it('uses the browser time zone, and UTC when the browser cannot name one', () => {
    expect(getSystemTimezone()).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);

    vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(() => {
      throw new Error('unsupported');
    });
    expect(getSystemTimezone()).toBe('UTC');
  });
});
