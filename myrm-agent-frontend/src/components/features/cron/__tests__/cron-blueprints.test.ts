import { describe, it, expect } from 'vitest';
import {
  CRON_BLUEPRINTS,
  humanizeSchedule,
  buildJobPayload,
  CRON_PRESETS,
} from '../cron-blueprints';

describe('cron-blueprints', () => {
  describe('CRON_BLUEPRINTS', () => {
    it('contains 5 blueprints', () => {
      expect(CRON_BLUEPRINTS).toHaveLength(5);
    });

    it('all blueprints have required fields', () => {
      for (const bp of CRON_BLUEPRINTS) {
        expect(bp.id).toBeTruthy();
        expect(bp.icon).toBeDefined();
        expect(bp.titleKey).toBeTruthy();
        expect(bp.descKey).toBeTruthy();
        expect(bp.promptKey).toBeTruthy();
        expect(bp.slots.length).toBeGreaterThan(0);
        expect(bp.buildSchedule).toBeInstanceOf(Function);
        expect(bp.buildPrompt).toBeInstanceOf(Function);
      }
    });

    it('morning_briefing has weekdays slot with correct options', () => {
      const bp = CRON_BLUEPRINTS.find((b) => b.id === 'morning_briefing')!;
      const weekdaysSlot = bp.slots.find((s) => s.name === 'weekdays');
      expect(weekdaysSlot).toBeDefined();
      expect(weekdaysSlot!.type).toBe('enum');
      expect(weekdaysSlot!.options).toEqual(['everyday', 'weekdays', 'weekends']);
      expect(weekdaysSlot!.default).toBe('everyday');
    });

    it('morning_briefing buildSchedule produces correct cron for everyday', () => {
      const bp = CRON_BLUEPRINTS.find((b) => b.id === 'morning_briefing')!;
      const schedule = bp.buildSchedule({ time: '08:00', weekdays: 'everyday' });
      expect(schedule.kind).toBe('cron');
      expect(schedule.expr).toBe('0 8 * * *');
    });

    it('morning_briefing buildSchedule produces correct cron for weekdays', () => {
      const bp = CRON_BLUEPRINTS.find((b) => b.id === 'morning_briefing')!;
      const schedule = bp.buildSchedule({ time: '09:30', weekdays: 'weekdays' });
      expect(schedule.expr).toBe('30 9 * * 1-5');
    });

    it('morning_briefing buildSchedule produces correct cron for weekends', () => {
      const bp = CRON_BLUEPRINTS.find((b) => b.id === 'morning_briefing')!;
      const schedule = bp.buildSchedule({ time: '10:00', weekdays: 'weekends' });
      expect(schedule.expr).toBe('0 10 * * 0,6');
    });

    it('weekly_review buildSchedule uses day slot correctly', () => {
      const bp = CRON_BLUEPRINTS.find((b) => b.id === 'weekly_review')!;
      const schedule = bp.buildSchedule({ time: '18:00', day: '1' });
      expect(schedule.expr).toBe('0 18 * * 1');
    });

    it('news_digest has topic text slot', () => {
      const bp = CRON_BLUEPRINTS.find((b) => b.id === 'news_digest')!;
      const topicSlot = bp.slots.find((s) => s.name === 'topic');
      expect(topicSlot).toBeDefined();
      expect(topicSlot!.type).toBe('text');
    });
  });

  describe('humanizeSchedule', () => {
    it('returns "Daily at HH:MM" for everyday cron', () => {
      expect(humanizeSchedule({ kind: 'cron', expr: '0 8 * * *' })).toBe('Daily at 08:00');
    });

    it('returns "Weekdays at HH:MM" for weekday cron', () => {
      expect(humanizeSchedule({ kind: 'cron', expr: '30 9 * * 1-5' })).toBe('Weekdays at 09:30');
    });

    it('returns "Weekends at HH:MM" for weekend cron', () => {
      expect(humanizeSchedule({ kind: 'cron', expr: '0 10 * * 0,6' })).toBe('Weekends at 10:00');
    });

    it('returns specific day names for single day cron', () => {
      const result = humanizeSchedule({ kind: 'cron', expr: '0 18 * * 5' });
      expect(result).toBe('Fri at 18:00');
    });

    it('returns formatted date for once schedule', () => {
      const result = humanizeSchedule({ kind: 'once', run_at: '2026-06-17T08:00:00Z' });
      expect(result).toContain('2026');
    });

    it('returns interval description', () => {
      const result = humanizeSchedule({ kind: 'interval', interval_ms: 3_600_000 });
      expect(result).toBe('Every 60 min');
    });

    it('returns empty string for missing expr', () => {
      expect(humanizeSchedule({ kind: 'cron' })).toBe('');
    });
  });

  describe('buildJobPayload', () => {
    const mockT = (key: string) => `translated:${key}`;
    const bp = CRON_BLUEPRINTS[0]; // morning_briefing

    it('builds correct payload without delivery', () => {
      const payload = buildJobPayload(
        bp,
        { time: '08:00', weekdays: 'everyday' },
        'Asia/Shanghai',
        mockT,
      );
      expect(payload.job_type).toBe('agent');
      expect(payload.schedule.kind).toBe('cron');
      expect(payload.schedule.expr).toBe('0 8 * * *');
      expect(payload.schedule.tz).toBe('Asia/Shanghai');
      expect(payload.session_target).toBe('isolated');
      expect(payload.delivery).toBeUndefined();
    });

    it('builds correct payload with delivery', () => {
      const payload = buildJobPayload(
        bp,
        { time: '08:00', weekdays: 'weekdays' },
        'UTC',
        mockT,
        { channel: 'telegram', target: '@mychat' },
      );
      expect(payload.delivery).toEqual({ channel: 'telegram', target: '@mychat' });
      expect(payload.schedule.expr).toBe('0 8 * * 1-5');
    });

    it('does not include delivery if channel is chat', () => {
      const payload = buildJobPayload(
        bp,
        { time: '08:00', weekdays: 'everyday' },
        'UTC',
        mockT,
        { channel: 'chat' },
      );
      expect(payload.delivery).toBeUndefined();
    });

    it('truncates name to 40 chars', () => {
      const longPromptBp = {
        ...bp,
        buildPrompt: () => 'A'.repeat(100),
      };
      const payload = buildJobPayload(
        longPromptBp,
        { time: '08:00', weekdays: 'everyday' },
        'UTC',
        mockT,
      );
      expect(payload.name.length).toBe(40);
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

  describe('edge cases', () => {
    it('timeToCronWithWeekdays handles midnight correctly', () => {
      const bp = CRON_BLUEPRINTS.find((b) => b.id === 'morning_briefing')!;
      const schedule = bp.buildSchedule({ time: '00:00', weekdays: 'everyday' });
      expect(schedule.expr).toBe('0 0 * * *');
    });

    it('timeToCronWithWeekdays handles 23:59 correctly', () => {
      const bp = CRON_BLUEPRINTS.find((b) => b.id === 'morning_briefing')!;
      const schedule = bp.buildSchedule({ time: '23:59', weekdays: 'weekends' });
      expect(schedule.expr).toBe('59 23 * * 0,6');
    });

    it('buildJobPayload with delivery target omitted', () => {
      const bp = CRON_BLUEPRINTS[0];
      const payload = buildJobPayload(
        bp,
        { time: '08:00', weekdays: 'everyday' },
        'UTC',
        (key: string) => key,
        { channel: 'discord' },
      );
      expect(payload.delivery).toEqual({ channel: 'discord' });
      expect(payload.delivery!.target).toBeUndefined();
    });

    it('buildJobPayload uses defaults when values are missing', () => {
      const bp = CRON_BLUEPRINTS.find((b) => b.id === 'morning_briefing')!;
      const payload = buildJobPayload(bp, {}, 'UTC', (key: string) => key);
      expect(payload.schedule.expr).toBe('0 8 * * *');
    });

    it('humanizeSchedule handles multi-day cron', () => {
      const result = humanizeSchedule({ kind: 'cron', expr: '0 9 * * 1,3,5' });
      expect(result).toBe('Mon, Wed, Fri at 09:00');
    });

    it('humanizeSchedule handles malformed short expr gracefully', () => {
      const result = humanizeSchedule({ kind: 'cron', expr: '0 8' });
      expect(result).toBe('0 8');
    });

    it('evening_winddown uses weekdays slot', () => {
      const bp = CRON_BLUEPRINTS.find((b) => b.id === 'evening_winddown')!;
      const schedule = bp.buildSchedule({ time: '21:00', weekdays: 'weekdays' });
      expect(schedule.expr).toBe('0 21 * * 1-5');
    });

    it('custom_reminder uses daily schedule (no weekdays slot)', () => {
      const bp = CRON_BLUEPRINTS.find((b) => b.id === 'custom_reminder')!;
      expect(bp.slots.find((s) => s.name === 'weekdays')).toBeUndefined();
      const schedule = bp.buildSchedule({ time: '09:00' });
      expect(schedule.expr).toBe('0 9 * * *');
    });

    it('all blueprints produce valid 5-part cron with defaults', () => {
      for (const bp of CRON_BLUEPRINTS) {
        const defaults = Object.fromEntries(bp.slots.map((s) => [s.name, s.default]));
        const schedule = bp.buildSchedule(defaults);
        expect(schedule.kind).toBe('cron');
        const parts = schedule.expr!.split(' ');
        expect(parts).toHaveLength(5);
      }
    });
  });
});
