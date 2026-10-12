/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/experienceObservability::fetchObservabilityDashboard, fetchTraceEvidence, recordEffectOutcome, updatePluginConfig
 * ../command-center/ExperienceObservabilityStudioCard::ExperienceObservabilityStudioCard
 *
 * [OUTPUT]
 * Test suite verifying Zero-Refactor Host Plugin & Experience Observability Studio Card:
 * 1. Initial render of HUD metrics and experience inventory list
 * 2. Originating session trace evidence lookup and key quotes display
 * 3. Task execution effect outcome reporting (success & dispute)
 * 4. Zero-refactor host plugin channel switching and lifecycle simulation
 *
 * [POS]
 * Unit test for Item 108 (ZeroRefactorHostLifecyclePluginAndExperienceObservabilitySuite).
 * Strict typing applied: No `any` types allowed. File lines < 300.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ExperienceObservabilityStudioCard } from '../command-center/ExperienceObservabilityStudioCard';
import type {
  ExperienceObservabilityMetricDTO,
  HostPluginConfigDTO,
  ObservabilityDashboardResponseDTO,
  SessionTraceEvidenceDTO,
} from '@/services/memory/experienceObservability';
import {
  FALLBACK_HOST_PLUGIN_CONFIG,
  FALLBACK_OBSERVABILITY_METRICS,
  FALLBACK_SESSION_TRACES,
} from '../command-center/experienceObservabilityFallbacks';

const {
  mockFetchObservabilityDashboard,
  mockFetchTraceEvidence,
  mockRecordEffectOutcome,
  mockUpdatePluginConfig,
} = vi.hoisted(() => ({
  mockFetchObservabilityDashboard: vi.fn(),
  mockFetchTraceEvidence: vi.fn(),
  mockRecordEffectOutcome: vi.fn(),
  mockUpdatePluginConfig: vi.fn(),
}));

vi.mock('@/services/memory/experienceObservability', () => ({
  fetchObservabilityDashboard: mockFetchObservabilityDashboard,
  fetchTraceEvidence: mockFetchTraceEvidence,
  recordEffectOutcome: mockRecordEffectOutcome,
  updatePluginConfig: mockUpdatePluginConfig,
}));

describe('ExperienceObservabilityStudioCard', () => {
  const sampleDashboard: ObservabilityDashboardResponseDTO = {
    status: 'ok',
    total_experiences_tracked: 5,
    overall_success_rate: 0.95,
    total_recalls: 401,
    total_injections: 270,
    plugin_config: FALLBACK_HOST_PLUGIN_CONFIG,
    metrics: FALLBACK_OBSERVABILITY_METRICS,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchObservabilityDashboard.mockResolvedValue(sampleDashboard);
    mockFetchTraceEvidence.mockResolvedValue(
      FALLBACK_SESSION_TRACES.sess_release_incident_09,
    );
  });

  it('renders card header, HUD bar, and experience inventory by default', async () => {
    render(<ExperienceObservabilityStudioCard />);

    // Header & Title
    expect(
      screen.getByText('零改造宿主插件与经验可观测看板工作台'),
    ).toBeInTheDocument();
    expect(screen.getByText('P1 Item 108')).toBeInTheDocument();

    // 4 HUD metrics
    await waitFor(() => {
      expect(screen.getByText('5 Procedures')).toBeInTheDocument();
    });
    expect(screen.getByText('270 Prompt Hooks')).toBeInTheDocument();
    expect(screen.getByText('95% Effective')).toBeInTheDocument();

    // Inventory items
    expect(screen.getByText('SafeGitBranchPushGuard')).toBeInTheDocument();
    expect(
      screen.getByText('ConcurrentDbIndexMigrationGuard'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('经营分析与PPT复盘三方法经验模板'),
    ).toBeInTheDocument();
  });

  it('retrieves and displays source session trace evidence for selected entry', async () => {
    const mockCustomTrace: SessionTraceEvidenceDTO = {
      session_id: 'sess_custom_99',
      title: '高并发数据库连接池熔断复盘',
      trajectory_summary: '连接耗尽导致服务不可用，提炼出预检规约。',
      key_evidence_snippets: ['[Turn 3] 连接池耗尽告警触发熔断'],
      agent_role: 'DatabaseArchitect',
      timestamp: '2026-10-08T06:00:00Z',
    };
    mockFetchTraceEvidence.mockResolvedValueOnce(mockCustomTrace);

    render(<ExperienceObservabilityStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByText('ConcurrentDbIndexMigrationGuard'),
      ).toBeInTheDocument();
    });

    const dbMetricBtn = screen.getByRole('button', {
      name: /ConcurrentDbIndexMigrationGuard/i,
    });
    fireEvent.click(dbMetricBtn);

    await waitFor(() => {
      expect(mockFetchTraceEvidence).toHaveBeenCalledWith(
        'sess_postgres_lock_timeout_42',
      );
      expect(
        screen.getByText('高并发数据库连接池熔断复盘'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('[Turn 3] 连接池耗尽告警触发熔断'),
      ).toBeInTheDocument();
    });
  });

  it('records effect feedback (task success) and updates metrics', async () => {
    const mockUpdatedMetric: ExperienceObservabilityMetricDTO = {
      ...FALLBACK_OBSERVABILITY_METRICS[0],
      success_count: 86,
      success_rate: 0.967,
    };
    mockRecordEffectOutcome.mockResolvedValueOnce(mockUpdatedMetric);

    render(<ExperienceObservabilityStudioCard />);

    await waitFor(() => {
      expect(screen.getByText(/标记任务成功 \(85\)/i)).toBeInTheDocument();
    });

    const successBtn = screen.getByRole('button', {
      name: /标记任务成功 \(85\)/i,
    });
    fireEvent.click(successBtn);

    await waitFor(() => {
      expect(mockRecordEffectOutcome).toHaveBeenCalledWith(
        'proc_git_push_safe',
        true,
        false,
      );
      expect(screen.getByText(/已记录任务成功归因/i)).toBeInTheDocument();
    });
  });

  it('switches to plugin console tab, updates configuration, and simulates lifecycle event', async () => {
    const mockUpdatedConfig: HostPluginConfigDTO = {
      ...FALLBACK_HOST_PLUGIN_CONFIG,
      active_channel: 'mcp',
      monitored_host: 'cursor',
    };
    mockUpdatePluginConfig.mockResolvedValueOnce(mockUpdatedConfig);

    render(<ExperienceObservabilityStudioCard />);

    const pluginTabBtn = screen.getByRole('button', {
      name: /^零改造宿主生命周期插件$/i,
    });
    fireEvent.click(pluginTabBtn);

    // Three-way integration channels
    expect(
      screen.getByText('官方零改造插件 (Plugin)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Direct FC 标准服务 (MCP)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('经验规约技能 (Skill)'),
    ).toBeInTheDocument();

    // Simulate session start lifecycle event
    const simStartBtn = screen.getByRole('button', {
      name: /^模拟 Session Start 预热$/i,
    });
    fireEvent.click(simStartBtn);

    expect(screen.getByText(/\[Session Start\] 宿主/i)).toBeInTheDocument();

    // Click Save Config
    const saveBtn = screen.getByRole('button', { name: /^保存配置$/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockUpdatePluginConfig).toHaveBeenCalled();
      expect(
        screen.getByText(/宿主插件运行时配置已成功刷盘生效/i),
      ).toBeInTheDocument();
    });
  });
});
