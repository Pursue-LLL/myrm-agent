import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Sun } from 'lucide-react';
import type { BlueprintDef } from '@/services/cron';
import {
  humanizeSchedule,
  buildBlueprintCreatePayload,
  buildScheduleFromSlots,
  CRON_PRESETS,
  resolveBlueprintTitleKey,
  resolveBlueprintSlotLabel,
} from '../cron-blueprints';

vi.mock('@/services/cron', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/cron')>();
  return {
    ...actual,
    fillBlueprint: vi.fn(),
    listBlueprints: vi.fn(),
  };
});

import { fillBlueprint } from '@/services/cron';
import { ApiError } from '@/lib/api';

const MORNING_DEF: BlueprintDef = {
  id: 'morning_briefing',
  icon: 'Sun',
  title: { en: 'Morning Briefing' },
  description: { en: 'Daily briefing' },
  prompt_template: { en: 'Brief me' },
  slots: [
    { name: 'time', type: 'time', label: 'time', default: '08:00', options: [], optional: false },
    {
      name: 'weekdays',
      type: 'enum',
      label: 'weekdays',
      default: 'everyday',
      options: ['everyday', 'weekdays', 'weekends'],
      optional: false,
    },
  ],
  category: 'general',
  tags: [],
  sort_order: 0,
};

const WEEKLY_DEF: BlueprintDef = {
  ...MORNING_DEF,
  id: 'weekly_review',
  slots: [
    { name: 'time', type: 'time', label: 'time', default: '18:00', options: [], optional: false },
    {
      name: 'day',
      type: 'enum',
      label: 'day',
      default: '5',
      options: ['1', '2', '3', '4', '5', '6', '0'],
      optional: false,
    },
  ],
};

describe('cron-blueprints', () => {
  describe('buildScheduleFromSlots', () => {
    it('morning_briefing everyday', () => {
      const schedule = buildScheduleFromSlots(MORNING_DEF, { time: '08:00', weekdays: 'everyday' });
      expect(schedule.expr).toBe('0 8 * * *');
    });

    it('morning_briefing weekdays', () => {
      const schedule = buildScheduleFromSlots(MORNING_DEF, { time: '09:30', weekdays: 'weekdays' });
      expect(schedule.expr).toBe('30 9 * * 1-5');
    });

    it('morning_briefing weekends', () => {
      const schedule = buildScheduleFromSlots(MORNING_DEF, { time: '10:00', weekdays: 'weekends' });
      expect(schedule.expr).toBe('0 10 * * 0,6');
    });

    it('weekly_review uses day slot', () => {
      const schedule = buildScheduleFromSlots(WEEKLY_DEF, { time: '18:00', day: '1' });
      expect(schedule.expr).toBe('0 18 * * 1');
    });

    it('handles midnight and 23:59', () => {
      expect(buildScheduleFromSlots(MORNING_DEF, { time: '00:00', weekdays: 'everyday' }).expr).toBe(
        '0 0 * * *',
      );
      expect(buildScheduleFromSlots(MORNING_DEF, { time: '23:59', weekdays: 'weekends' }).expr).toBe(
        '59 23 * * 0,6',
      );
    });
  });

  describe('humanizeSchedule', () => {
    const locale = 'en-US';
    const t = vi.fn(
      (key: string, values?: Record<string, string | number>): string => {
        const map: Record<string, string | number> = values ?? {};
        switch (key) {
          case 'schedule.once': return 'Once';
          case 'schedule.onceAt': return `Once at ${map.time}`;
          case 'schedule.everyMinutes': return `Every ${map.count} min`;
          case 'schedule.dailyAt': return `Daily at ${map.time}`;
          case 'schedule.weekdaysAt': return `Weekdays at ${map.time}`;
          case 'schedule.weekendsAt': return `Weekends at ${map.time}`;
          case 'schedule.weekdayListAt': return `${map.days} at ${map.time}`;
          case 'blueprint.daySun': return 'Sunday';
          case 'blueprint.dayMon': return 'Monday';
          case 'blueprint.dayTue': return 'Tuesday';
          case 'blueprint.dayWed': return 'Wednesday';
          case 'blueprint.dayThu': return 'Thursday';
          case 'blueprint.dayFri': return 'Friday';
          case 'blueprint.daySat': return 'Saturday';
          default: return key;
        }
      },
    );

    it('returns "Daily at HH:MM" for everyday cron', () => {
      expect(humanizeSchedule({ kind: 'cron', expr: '0 8 * * *' }, t, locale)).toBe('Daily at 08:00');
      expect(t).toHaveBeenCalledWith('schedule.dailyAt', { time: '08:00' });
    });

    it('returns "Weekdays at HH:MM" for weekday cron', () => {
      expect(humanizeSchedule({ kind: 'cron', expr: '30 9 * * 1-5' }, t, locale)).toBe('Weekdays at 09:30');
      expect(t).toHaveBeenCalledWith('schedule.weekdaysAt', { time: '09:30' });
    });

    it('returns "Weekends at HH:MM" for weekend cron', () => {
      expect(humanizeSchedule({ kind: 'cron', expr: '0 10 * * 0,6' }, t, locale)).toBe('Weekends at 10:00');
      expect(t).toHaveBeenCalledWith('schedule.weekendsAt', { time: '10:00' });
    });

    it('reuses blueprint.day* weekday keys for single day cron', () => {
      const result = humanizeSchedule({ kind: 'cron', expr: '0 18 * * 5' }, t, locale);
      expect(result).toBe('Friday at 18:00');
      expect(t).toHaveBeenCalledWith('blueprint.dayFri');
      expect(t).toHaveBeenCalledWith('schedule.weekdayListAt', { days: 'Friday', time: '18:00' });
    });

    it('reuses blueprint.day* weekday keys for multi-day cron', () => {
      const result = humanizeSchedule({ kind: 'cron', expr: '0 9 * * 1,3,5' }, t, locale);
      expect(result).toBe('Monday, Wednesday, Friday at 09:00');
      expect(t).toHaveBeenCalledWith('schedule.weekdayListAt', { days: 'Monday, Wednesday, Friday', time: '09:00' });
    });

    it('uses locale-aware formatTime for once schedule', () => {
      const result = humanizeSchedule({ kind: 'once', run_at: '2026-06-17T08:00:00Z' }, t, locale);
      expect(result).toContain('Once at ');
    });

    it('returns interval description', () => {
      expect(humanizeSchedule({ kind: 'interval', interval_ms: 3_600_000 }, t, locale)).toBe('Every 60 min');
      expect(t).toHaveBeenCalledWith('schedule.everyMinutes', { count: 60 });
    });

    it('returns empty string for missing expr', () => {
      expect(humanizeSchedule({ kind: 'cron' }, t, locale)).toBe('');
    });

    it('handles malformed short expr gracefully', () => {
      expect(humanizeSchedule({ kind: 'cron', expr: '0 8' }, t, locale)).toBe('0 8');
    });
  });

  describe('CRON_PRESETS', () => {
    it('contains 6 presets', () => {
      expect(CRON_PRESETS).toHaveLength(6);
    });

    it('all presets have valid cron expressions', () => {
      for (const preset of CRON_PRESETS) {
        expect(preset.id).toBeTruthy();
        expect(preset.labelKey).toBeTruthy();
        const parts = preset.expr.split(' ');
        expect(parts).toHaveLength(5);
      }
    });
  });

  describe('i18n key helpers', () => {
    it('maps server snake_case blueprint ids to camelCase i18n keys', () => {
      expect(resolveBlueprintTitleKey('custom_reminder')).toBe('blueprint.customReminder.title');
      expect(resolveBlueprintTitleKey('morning_briefing')).toBe('blueprint.morningBriefing.title');
    });

    it('maps blueprint slot names to cron.blueprint.slot* locale keys', () => {
      expect(resolveBlueprintSlotLabel('time')).toBe('blueprint.slotTime');
      expect(resolveBlueprintSlotLabel('message')).toBe('blueprint.slotMessage');
    });
  });

  describe('buildBlueprintCreatePayload', () => {
    const mockBlueprint = {
      id: 'morning_briefing',
      icon: Sun,
      titleKey: 'blueprint.morningBriefing.title',
      descKey: 'blueprint.morningBriefing.desc',
      promptKey: 'blueprint.morningBriefing.prompt',
      slots: [],
      title: { en: 'Morning Briefing' },
      description: { en: 'Daily briefing' },
      buildSchedule: () => ({ kind: 'cron' as const, expr: '0 8 * * *' }),
    };

    beforeEach(() => {
      vi.mocked(fillBlueprint).mockReset();
    });

    it('uses server fill API', async () => {
      vi.mocked(fillBlueprint).mockResolvedValue({
        schedule: { kind: 'cron', expr: '0 8 * * *', tz: 'Asia/Shanghai' },
        prompt: 'Server prompt',
        name: 'Morning Briefing',
        required_capabilities: ['web_search_tool', 'net_fetch'],
        tools_allowed: ['web_search'],
        job_type: 'agent',
        session_target: 'main',
        deduplicate: false,
        skip_if_active: false,
      });

      const payload = await buildBlueprintCreatePayload(
        mockBlueprint,
        { time: '08:00', weekdays: 'everyday' },
        'Asia/Shanghai',
        'ja',
      );

      expect(fillBlueprint).toHaveBeenCalledWith(
        'morning_briefing',
        { time: '08:00', weekdays: 'everyday' },
        'ja',
        'Asia/Shanghai',
      );
      expect(payload.prompt).toBe('Server prompt');
      expect(payload.name).toBe('Morning Briefing');
      expect(payload.schedule.expr).toBe('0 8 * * *');
      expect(payload.required_capabilities).toEqual(['web_search_tool', 'net_fetch']);
      expect(payload.tools_allowed).toEqual(['web_search']);
    });

    it('propagates server errors without local fallback', async () => {
      vi.mocked(fillBlueprint).mockRejectedValue(new Error('network'));

      await expect(
        buildBlueprintCreatePayload(
          mockBlueprint,
          { time: '08:00', weekdays: 'everyday' },
          'UTC',
          'en',
        ),
      ).rejects.toThrow('network');
    });

    it('rethrows client errors from fill API', async () => {
      vi.mocked(fillBlueprint).mockRejectedValue(new ApiError('bad slot', 422));

      await expect(
        buildBlueprintCreatePayload(
          mockBlueprint,
          { time: '08:00', weekdays: 'everyday' },
          'UTC',
          'en',
        ),
      ).rejects.toBeInstanceOf(ApiError);
    });
  });
});
