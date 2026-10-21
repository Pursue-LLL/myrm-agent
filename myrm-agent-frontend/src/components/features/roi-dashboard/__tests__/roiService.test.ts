import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  calculateLocalRoiFallback,
  fetchRoiDashboardMetrics,
  fetchHighYieldRoutines,
} from '../roiService';

describe('roiService', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('calculateLocalRoiFallback', () => {
    it('calculates baseline metrics for today range', () => {
      const metrics = calculateLocalRoiFallback('today', 35.0);
      expect(metrics.time_range).toBe('today');
      expect(metrics.total_hours_saved).toBeGreaterThan(0);
      expect(metrics.total_monetary_saved_usd).toBeGreaterThan(0);
      expect(metrics.total_compute_cost_usd).toBeGreaterThan(0);
      expect(metrics.net_roi_multiplier).toBeGreaterThan(1.0);
      expect(metrics.categories_breakdown.length).toBe(6);
      expect(metrics.recent_digest).toBeDefined();
    });

    it('scales metrics upwards for week and all_time ranges', () => {
      const todayMetrics = calculateLocalRoiFallback('today');
      const weekMetrics = calculateLocalRoiFallback('week');
      const allTimeMetrics = calculateLocalRoiFallback('all_time');

      expect(weekMetrics.total_hours_saved).toBeGreaterThan(todayMetrics.total_hours_saved);
      expect(allTimeMetrics.total_hours_saved).toBeGreaterThan(weekMetrics.total_hours_saved);
      expect(weekMetrics.total_monetary_saved_usd).toBeGreaterThan(todayMetrics.total_monetary_saved_usd);
    });

    it('respects custom hourly rate parameter', () => {
      const rate35 = calculateLocalRoiFallback('today', 35.0);
      const rate70 = calculateLocalRoiFallback('today', 70.0);

      expect(rate70.hourly_rate_baseline_usd).toBe(70.0);
      expect(rate70.total_monetary_saved_usd).toBeGreaterThan(rate35.total_monetary_saved_usd);
    });
  });

  describe('fetchRoiDashboardMetrics', () => {
    it('falls back to local calculator on fetch error', async () => {
      vi.spyOn(global, 'fetch').mockRejectedValueOnce(new Error('Network error'));
      const res = await fetchRoiDashboardMetrics('today', 40.0);

      expect(res.time_range).toBe('today');
      expect(res.hourly_rate_baseline_usd).toBe(40.0);
      expect(res.total_hours_saved).toBeGreaterThan(0);
    });

    it('parses valid server response when fetch succeeds', async () => {
      const mockServerPayload = {
        time_range: 'today',
        total_hours_saved: 18.5,
        total_monetary_saved_usd: 647.5,
        total_compute_cost_usd: 0.85,
        net_roi_multiplier: 761.8,
        hourly_rate_baseline_usd: 35.0,
        categories_breakdown: [],
      };

      vi.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockServerPayload,
      } as unknown as Response);

      const res = await fetchRoiDashboardMetrics('today');
      expect(res.total_hours_saved).toBe(18.5);
      expect(res.net_roi_multiplier).toBe(761.8);
    });
  });

  describe('fetchHighYieldRoutines', () => {
    it('returns fallback preset routines on network error', async () => {
      vi.spyOn(global, 'fetch').mockRejectedValueOnce(new Error('Network error'));
      const routines = await fetchHighYieldRoutines();

      expect(routines.length).toBeGreaterThanOrEqual(4);
      expect(routines[0]?.routine_id).toBe('routine_market_radar');
      expect(routines[0]?.estimated_minutes_saved).toBeGreaterThan(0);
    });

    it('returns server routines when response is valid array', async () => {
      const mockRoutines = [
        {
          routine_id: 'custom_routine_1',
          title_zh: '自定义报告',
          title_en: 'Custom Report',
          description_zh: '描述',
          description_en: 'Desc',
          estimated_minutes_saved: 90,
          typical_roi_multiplier: 150.0,
          category: 'doc_summary',
          preset_prompt: 'Run test prompt',
        },
      ];

      vi.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockRoutines,
      } as unknown as Response);

      const routines = await fetchHighYieldRoutines();
      expect(routines.length).toBe(1);
      expect(routines[0]?.routine_id).toBe('custom_routine_1');
    });
  });
});
