import { describe, it, expect } from 'vitest';
import {
  calculateWorkerEta,
  formatDuration,
  calculateAggregatedProgress,
  resolveReanchorPlacement,
  generateAdoptionSnippet,
} from '../fullDuplexBridgeEngine';
import { BackgroundWorkerTask, ReanchoredResultCard } from '../fullDuplexBridgeTypes';

describe('fullDuplexBridgeEngine', () => {
  describe('calculateWorkerEta', () => {
    it('returns remaining fallback time when progress is 0', () => {
      expect(calculateWorkerEta(0, 30, 120)).toBe(90);
      expect(calculateWorkerEta(0, 150, 120)).toBe(0);
    });

    it('returns 0 when progress is 100 or greater', () => {
      expect(calculateWorkerEta(100, 60)).toBe(0);
      expect(calculateWorkerEta(105, 60)).toBe(0);
    });

    it('returns guarded time when progress is below 5%', () => {
      expect(calculateWorkerEta(2, 10, 100)).toBe(90);
      expect(calculateWorkerEta(3, 98, 100)).toBe(5);
    });

    it('accurately estimates remaining seconds via linear projection', () => {
      // 50% 进度耗时 50 秒，总预估 100 秒，剩余 50 秒
      expect(calculateWorkerEta(50, 50)).toBe(50);
      // 25% 进度耗时 30 秒，总预估 120 秒，剩余 90 秒
      expect(calculateWorkerEta(25, 30)).toBe(90);
    });
  });

  describe('formatDuration', () => {
    it('formats seconds under 1 minute', () => {
      expect(formatDuration(0)).toBe('0s');
      expect(formatDuration(45)).toBe('45s');
    });

    it('formats minutes and seconds', () => {
      expect(formatDuration(60)).toBe('1m');
      expect(formatDuration(84)).toBe('1m 24s');
    });

    it('formats hours and minutes', () => {
      expect(formatDuration(3600)).toBe('1h 0m');
      expect(formatDuration(3720)).toBe('1h 2m');
    });
  });

  describe('calculateAggregatedProgress', () => {
    it('handles empty worker list gracefully', () => {
      const res = calculateAggregatedProgress([]);
      expect(res.totalCount).toBe(0);
      expect(res.runningCount).toBe(0);
      expect(res.averageProgress).toBe(0);
      expect(res.hasActive).toBe(false);
    });

    it('correctly aggregates counts and calculates average progress', () => {
      const mockWorkers: BackgroundWorkerTask[] = [
        {
          id: 'w1',
          title: '爬虫分析',
          category: '调研',
          status: 'running',
          progress: 40,
          currentStepLabel: '抓取中',
          steps: [],
          elapsedSec: 40,
          estimatedTotalSec: 100,
          spawnedAt: Date.now(),
        },
        {
          id: 'w2',
          title: '视频抽帧',
          category: '渲染',
          status: 'completed',
          progress: 100,
          currentStepLabel: '完成',
          steps: [],
          elapsedSec: 60,
          estimatedTotalSec: 60,
          spawnedAt: Date.now(),
        },
      ];

      const res = calculateAggregatedProgress(mockWorkers);
      expect(res.totalCount).toBe(2);
      expect(res.runningCount).toBe(1);
      expect(res.completedCount).toBe(1);
      expect(res.averageProgress).toBe(70);
      expect(res.hasActive).toBe(true);
      expect(res.topActiveTitle).toBe('爬虫分析');
    });
  });

  describe('resolveReanchorPlacement', () => {
    it('defaults to bottom append when no anchor is provided or message list is empty', () => {
      expect(resolveReanchorPlacement([])).toEqual({
        placementIndex: 0,
        strategy: 'bottom_append',
        anchorFound: false,
      });

      expect(resolveReanchorPlacement(['m1', 'm2'])).toEqual({
        placementIndex: 2,
        strategy: 'bottom_append',
        anchorFound: false,
      });
    });

    it('places result after anchor when target message anchor is found', () => {
      const res = resolveReanchorPlacement(['m1', 'm2', 'm3'], 'm2');
      expect(res).toEqual({
        placementIndex: 2,
        strategy: 'after_anchor',
        anchorFound: true,
      });
    });

    it('falls back to bottom append when target anchor is not in list', () => {
      const res = resolveReanchorPlacement(['m1', 'm2'], 'm999');
      expect(res).toEqual({
        placementIndex: 2,
        strategy: 'bottom_append',
        anchorFound: false,
      });
    });
  });

  describe('generateAdoptionSnippet', () => {
    it('constructs contextual prompt snippet from card payload', () => {
      const mockCard: ReanchoredResultCard = {
        id: 'c1',
        workerId: 'w1',
        title: '全网竞品调研报告',
        category: '调研',
        elapsedSec: 90,
        isAdopted: false,
        createdAt: Date.now(),
        artifact: {
          id: 'a1',
          title: 'report.pdf',
          type: 'report',
          summary: '已提炼 12 项关键结论',
        },
      };

      const snippet = generateAdoptionSnippet(mockCard);
      expect(snippet).toContain('《全网竞品调研报告》');
      expect(snippet).toContain('已提炼 12 项关键结论');
    });
  });
});
