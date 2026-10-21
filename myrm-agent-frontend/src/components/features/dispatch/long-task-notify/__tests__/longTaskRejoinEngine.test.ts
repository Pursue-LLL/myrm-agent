import { describe, it, expect } from 'vitest';
import {
  formatTaskDuration,
  calculateEstimatedCompletionTime,
  computeRejoinDelta,
  simulatePushNotificationPayload,
} from '../longTaskRejoinEngine';
import { LongTaskDispatchTicket } from '../longTaskNotifyTypes';

describe('longTaskRejoinEngine pure algorithms', () => {
  describe('formatTaskDuration', () => {
    it('formats duration across seconds, minutes, and compound combinations', () => {
      expect(formatTaskDuration(0)).toBe('0秒');
      expect(formatTaskDuration(-5)).toBe('0秒');
      expect(formatTaskDuration(45)).toBe('45秒');
      expect(formatTaskDuration(180)).toBe('3分钟');
      expect(formatTaskDuration(150)).toBe('2分30秒');
    });
  });

  describe('calculateEstimatedCompletionTime', () => {
    it('calculates completion timestamp, formatted time, and remaining seconds', () => {
      const startedAt = 1700000000000;
      const durationSec = 120; // 2 mins
      const currentNow = startedAt + 30000; // 30s elapsed

      const info = calculateEstimatedCompletionTime(
        startedAt,
        durationSec,
        currentNow
      );

      expect(info.etaTimestamp).toBe(startedAt + 120000);
      expect(info.remainingSec).toBe(90);
      expect(info.etaFormatted).toMatch(/^\d{2}:\d{2}$/);
    });

    it('clamps remaining seconds to zero when expired', () => {
      const startedAt = 1000000;
      const durationSec = 60;
      const expiredNow = 2000000;

      const info = calculateEstimatedCompletionTime(
        startedAt,
        durationSec,
        expiredNow
      );

      expect(info.remainingSec).toBe(0);
    });
  });

  describe('computeRejoinDelta', () => {
    it('computes missed event counts accurately against last sync timestamp', () => {
      const lastSync = 1000;
      const events = [
        { timestamp: 900 },
        { timestamp: 1000 },
        { timestamp: 1050 },
        { timestamp: 1100 },
      ];

      const delta = computeRejoinDelta(lastSync, events);
      expect(delta.missedCount).toBe(2);
      expect(delta.needsCatchup).toBe(true);
    });

    it('returns 0 missed events when list is empty or already in sync', () => {
      expect(computeRejoinDelta(2000, [])).toEqual({
        missedCount: 0,
        needsCatchup: false,
      });

      const events = [{ timestamp: 1500 }, { timestamp: 1800 }];
      expect(computeRejoinDelta(2000, events)).toEqual({
        missedCount: 0,
        needsCatchup: false,
      });
    });
  });

  describe('simulatePushNotificationPayload', () => {
    it('generates rich Web Push payload containing checklist count and deep link', () => {
      const mockTicket: LongTaskDispatchTicket = {
        taskId: 'task-test-77',
        title: '全量竞品调研',
        prompt: '测试提示词',
        estimatedDurationSec: 180,
        executionEnv: 'cloud-server',
        notifyChannels: ['web-push'],
        startedAt: 1000,
        status: 'completed',
        progressPercent: 100,
        currentStep: '已完成',
        sourcedChecklist: [
          {
            id: '1',
            title: '竞品A',
            sourceUrl: 'https://a.com',
            sourceTitle: 'A',
            verified: true,
            snippet: '',
            timestamp: 1000,
          },
        ],
        pushSent: true,
      };

      const payload = simulatePushNotificationPayload(mockTicket);
      expect(payload.title).toBe('长任务已完成: 全量竞品调研');
      expect(payload.body).toContain('1 条核验产物');
      expect(payload.deepLink).toBe('myrm://session/rejoin?task=task-test-77');
      expect(payload.tag).toBe('task-notify-task-test-77');
    });
  });
});
