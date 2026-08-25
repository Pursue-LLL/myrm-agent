/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { renderHook } from '@testing-library/react';
import WorkbenchRetentionSection from '../WorkbenchRetentionSection';
import { useWorkbenchRetentionSummary } from '../useWorkbenchRetentionSummary';
import { apiRequest } from '@/lib/api';
import { getGrowthDashboard } from '@/services/statistics';
import { listCronJobs } from '@/services/cron';
import * as deployModeModule from '@/lib/deploy-mode';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params) {
    let str = key;
    for (const [k, v] of Object.entries(params)) {
      str += `:${k}=${v}`;
    }
    return str;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

vi.mock('@/services/statistics', () => ({
  getGrowthDashboard: vi.fn(),
}));

vi.mock('@/services/cron', () => ({
  listCronJobs: vi.fn(),
}));

describe('useWorkbenchRetentionSummary & WorkbenchRetentionSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('aggregates all asset sources correctly when all APIs succeed', async () => {
    vi.mocked(apiRequest).mockImplementation(async (path: string) => {
      if (path === '/wiki/stats') {
        return {
          total_concepts: 42,
          total_articles: 12,
          total_raw_files: 8,
          wiki_path: '/workspace/.myrm/wiki',
        };
      }
      if (path === '/workspace/rules') {
        return {
          rules: [
            { path: '.cursorrules', source: 'workspace', char_count: 500, truncated: false, content: 'Rule 1' },
            { path: 'CLAUDE.md', source: 'claude', char_count: 300, truncated: false, content: 'Rule 2' },
          ],
          total_chars: 800,
          workspace_root: '/workspace/project',
        };
      }
      if (path === '/system/storage') {
        return {
          data_dir: '/workspace/.myrm/data',
          disk_total_bytes: 100 * 1024 * 1024 * 1024,
          disk_used_bytes: 20 * 1024 * 1024 * 1024,
          disk_free_bytes: 80 * 1024 * 1024 * 1024,
          subdirs: [],
        };
      }
      throw new Error(`Unexpected path: ${path}`);
    });

    vi.mocked(getGrowthDashboard).mockResolvedValue({
      snapshot: {
        total_memories: 156,
        memory_by_type: {},
        memory_week_delta: 10,
        total_skills: 24,
        total_evolutions: 5,
        skill_success_rate: 98,
        active_routings: 3,
        auto_healed_sessions: 2,
        memory_health_score: 95,
      },
      weekly_summary: {
        cron_executions: 38,
      },
    } as any);

    vi.mocked(listCronJobs).mockResolvedValue({
      items: [{ id: 'job-1', name: 'daily-backup' } as any, { id: 'job-2', name: 'hourly-sync' } as any],
      total: 2,
    } as any);

    const { result } = renderHook(() => useWorkbenchRetentionSummary());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    const summary = result.current.summary;
    expect(summary).not.toBeNull();
    expect(summary?.wikiConcepts).toBe(42);
    expect(summary?.wikiRawFiles).toBe(8);
    expect(summary?.wikiStatus).toBe('ok');
    expect(summary?.totalMemories).toBe(156);
    expect(summary?.memoryHealthScore).toBe(95);
    expect(summary?.totalSkills).toBe(24);
    expect(summary?.totalEvolutions).toBe(5);
    expect(summary?.totalRules).toBe(2);
    expect(summary?.totalRuleChars).toBe(800);
    expect(summary?.cronJobsCount).toBe(2);
    expect(summary?.cronExecutions).toBe(38);
    expect(summary?.storageUsedBytes).toBe(20 * 1024 * 1024 * 1024);
    expect(summary?.storageStatus).toBe('ok');
  });

  it('handles partial API failures with graceful degradation', async () => {
    vi.mocked(apiRequest).mockImplementation(async (path: string) => {
      if (path === '/wiki/stats') {
        throw new Error('Wiki offline');
      }
      if (path === '/workspace/rules') {
        return { rules: [], total_chars: 0, workspace_root: '' };
      }
      if (path === '/system/storage') {
        throw new Error('Storage unavailable');
      }
      throw new Error(`Unknown path: ${path}`);
    });

    vi.mocked(getGrowthDashboard).mockRejectedValue(new Error('Growth DB down'));
    vi.mocked(listCronJobs).mockResolvedValue({ items: [], total: 0 } as any);

    const { result } = renderHook(() => useWorkbenchRetentionSummary());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    const summary = result.current.summary;
    expect(summary).not.toBeNull();
    expect(summary?.wikiStatus).toBe('unavailable');
    expect(summary?.memoryStatus).toBe('unavailable');
    expect(summary?.skillsStatus).toBe('unavailable');
    expect(summary?.rulesStatus).toBe('ok');
    expect(summary?.cronStatus).toBe('ok');
    expect(summary?.storageStatus).toBe('unavailable');
  });

  it('renders WorkbenchRetentionSection with metrics and sovereignty cards', async () => {
    vi.mocked(apiRequest).mockImplementation(async (path: string) => {
      if (path === '/wiki/stats') {
        return { total_concepts: 10, total_articles: 5, total_raw_files: 2, wiki_path: '/path' };
      }
      if (path === '/workspace/rules') {
        return { rules: [], total_chars: 0, workspace_root: '' };
      }
      if (path === '/system/storage') {
        return {
          data_dir: '/data',
          disk_total_bytes: 1000,
          disk_used_bytes: 500,
          disk_free_bytes: 500,
          subdirs: [],
        };
      }
      return {};
    });

    vi.mocked(getGrowthDashboard).mockResolvedValue({
      snapshot: { total_memories: 50, total_skills: 8, total_evolutions: 2, memory_health_score: 90 },
      weekly_summary: { cron_executions: 12 },
    } as any);

    vi.mocked(listCronJobs).mockResolvedValue({ items: [{ id: '1' }], total: 1 } as any);

    render(<WorkbenchRetentionSection />);

    await waitFor(() => {
      expect(screen.getByText('title')).toBeDefined();
      expect(screen.getByText('badge')).toBeDefined();
      expect(screen.getByText('sovereignty.title')).toBeDefined();
      expect(screen.getByText('deployHonest.title')).toBeDefined();
      expect(screen.getByText('50')).toBeDefined(); // total memories
      expect(screen.getByText('8')).toBeDefined(); // total skills
    });
  });

  it('adapts storage subtitle and details across Tauri, Sandbox, and Local deployment modes', async () => {
    vi.mocked(apiRequest).mockImplementation(async () => ({}));
    vi.mocked(getGrowthDashboard).mockResolvedValue({
      snapshot: { total_memories: 0, total_skills: 0, total_evolutions: 0, memory_health_score: 100 },
      weekly_summary: { cron_executions: 0 },
    } as any);
    vi.mocked(listCronJobs).mockResolvedValue({ items: [], total: 0 } as any);

    const tauriSpy = vi.spyOn(deployModeModule, 'isTauriRuntime').mockReturnValue(true);
    const sandboxSpy = vi.spyOn(deployModeModule, 'isSandbox').mockReturnValue(false);
    const localSpy = vi.spyOn(deployModeModule, 'isLocalMode').mockReturnValue(false);

    render(<WorkbenchRetentionSection />);

    await waitFor(() => {
      expect(screen.getByText('deployHonest.tauriSubtitle')).toBeDefined();
    });

    tauriSpy.mockRestore();
    sandboxSpy.mockRestore();
    localSpy.mockRestore();
  });
});
