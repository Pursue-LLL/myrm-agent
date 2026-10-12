/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FirstEncounterReportCard } from '../command-center/FirstEncounterReportCard';
import type {
  ConfirmInsightIngestResponseDTO,
  FirstEncounterReportResponseDTO,
  OnboardingScanSummaryResponseDTO,
} from '@/services/memory/onboardingInsight';

const {
  mockScanAgentSources,
  mockGenerateFirstEncounterReport,
  mockConfirmInsightIngest,
} = vi.hoisted(() => ({
  mockScanAgentSources: vi.fn(),
  mockGenerateFirstEncounterReport: vi.fn(),
  mockConfirmInsightIngest: vi.fn(),
}));

vi.mock('@/services/memory/onboardingInsight', () => ({
  scanAgentSources: mockScanAgentSources,
  generateFirstEncounterReport: mockGenerateFirstEncounterReport,
  confirmInsightIngest: mockConfirmInsightIngest,
}));

describe('FirstEncounterReportCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockScanSummary: OnboardingScanSummaryResponseDTO = {
    total_detected: 3,
    sources: [
      { source_id: 'cursor', display_name: 'Cursor Composer & Agent', detected: true, recent_sessions_count: 14 },
      { source_id: 'claude_code', display_name: 'Claude Code CLI', detected: true, recent_sessions_count: 8 },
      { source_id: 'codex', display_name: 'Codex / GitHub Copilot', detected: false, recent_sessions_count: 0 },
      { source_id: 'hermes', display_name: 'Hermes Agent', detected: true, recent_sessions_count: 5 },
      { source_id: 'openclaw', display_name: 'OpenClaw Agent', detected: false, recent_sessions_count: 0 },
    ],
  };

  const mockReport: FirstEncounterReportResponseDTO = {
    report_id: 'rep-test-999',
    generated_at: '2026-10-08T02:00:00Z',
    total_sessions_scanned: 16,
    total_facts_extracted: 3,
    secrets_redacted_count: 5,
    token_budget_saved_estimate: 92000,
    sources_sampled: ['cursor', 'claude_code', 'hermes'],
    candidate_facts: [
      {
        fact_id: 'fact-pref-01',
        category: 'tech_stack_preference',
        summary: '前端架构强制开启 TypeScript 严格模式，严禁使用 any 类型',
        source_agent: 'cursor',
        confidence: 0.98,
        fingerprint: 'fp-tech-01',
        origin_conversation_id: 'session-cursor-alpha',
        raw_quote: 'Always use strict types and eliminate any annotations.',
      },
      {
        fact_id: 'fact-less-02',
        category: 'hard_learned_lesson',
        summary: '单文件代码行数严格控制在 400 行以内，杜绝技术债遗留',
        source_agent: 'claude_code',
        confidence: 0.95,
        fingerprint: 'fp-less-02',
        origin_conversation_id: 'session-claude-refactor',
        raw_quote: 'Refactor if file exceeds 400 lines into modular components.',
      },
      {
        fact_id: 'fact-goal-03',
        category: 'active_project_goal',
        summary: '构建轻量零配置的 SQLite 向量检索与本地优先离线自举架构',
        source_agent: 'hermes',
        confidence: 0.91,
        fingerprint: 'fp-goal-03',
        origin_conversation_id: 'session-hermes-storage',
        raw_quote: 'Local-first zero daemon storage is our strategic direction.',
      },
    ],
  };

  const mockIngestSuccess: ConfirmInsightIngestResponseDTO = {
    success: true,
    ingested_count: 3,
    deduplicated_count: 0,
    message: '成功将 3 项初见技术画像沉淀至持久化记忆库',
    ingested_fact_ids: ['fact-pref-01', 'fact-less-02', 'fact-goal-03'],
  };

  it('renders initial state and fetches agent sources radar', async () => {
    mockScanAgentSources.mockResolvedValueOnce(mockScanSummary);

    render(<FirstEncounterReportCard />);

    expect(screen.getByTestId('first-encounter-report-card')).toBeInTheDocument();
    expect(screen.getByText(/历史会话轻量采样与初见报告/)).toBeInTheDocument();
    expect(screen.getByText('Item 67 · P0')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockScanAgentSources).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText('Cursor Composer & Agent')).toBeInTheDocument();
    expect(screen.getByText('Claude Code CLI')).toBeInTheDocument();
    expect(screen.getByText('Hermes Agent')).toBeInTheDocument();
    expect(screen.getByText('发现 14 会话')).toBeInTheDocument();
  });

  it('updates sampling options parameters', async () => {
    mockScanAgentSources.mockResolvedValueOnce(mockScanSummary);

    render(<FirstEncounterReportCard />);

    const sessionsInput = screen.getByLabelText(/单源采样会话上限:/);
    fireEvent.change(sessionsInput, { target: { value: '12' } });
    expect(sessionsInput).toHaveValue(12);

    const entropyCheckbox = screen.getByLabelText(/香农熵密钥深度脱敏/);
    expect(entropyCheckbox).toBeChecked();
    fireEvent.click(entropyCheckbox);
    expect(entropyCheckbox).not.toBeChecked();
  });

  it('generates first encounter report and displays candidate facts with HUD metrics', async () => {
    mockScanAgentSources.mockResolvedValueOnce(mockScanSummary);
    mockGenerateFirstEncounterReport.mockResolvedValueOnce(mockReport);

    render(<FirstEncounterReportCard />);

    const generateBtn = screen.getByRole('button', { name: /生成初见技术画像报告/ });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(mockGenerateFirstEncounterReport).toHaveBeenCalledWith(
        expect.objectContaining({
          max_sessions_per_source: 6,
          enable_entropy_inspection: true,
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/初见报告成果与安全审计/)).toBeInTheDocument();
    });

    expect(screen.getByText('16')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('92,000')).toBeInTheDocument();

    expect(screen.getByText('前端架构强制开启 TypeScript 严格模式，严禁使用 any 类型')).toBeInTheDocument();
    expect(screen.getByText('单文件代码行数严格控制在 400 行以内，杜绝技术债遗留')).toBeInTheDocument();
    expect(screen.getByText('构建轻量零配置的 SQLite 向量检索与本地优先离线自举架构')).toBeInTheDocument();

    expect(screen.getByText('技术栈偏好')).toBeInTheDocument();
    expect(screen.getByText('架构避坑法则')).toBeInTheDocument();
    expect(screen.getByText('活跃项目目标')).toBeInTheDocument();
  });

  it('supports selecting, unselecting and toggling all candidate facts', async () => {
    mockScanAgentSources.mockResolvedValueOnce(mockScanSummary);
    mockGenerateFirstEncounterReport.mockResolvedValueOnce(mockReport);

    render(<FirstEncounterReportCard />);

    fireEvent.click(screen.getByRole('button', { name: /生成初见技术画像报告/ }));

    await waitFor(() => {
      expect(screen.getByText(/已识别画像事实 \(3\/3 已勾选\):/)).toBeInTheDocument();
    });

    // Unselect one fact
    const firstCheckbox = screen.getByLabelText('前端架构强制开启 TypeScript 严格模式，严禁使用 any 类型');
    fireEvent.click(firstCheckbox);

    await waitFor(() => {
      expect(screen.getByText(/已识别画像事实 \(2\/3 已勾选\):/)).toBeInTheDocument();
    });

    // Toggle select all (from partial to all)
    const toggleAllBtn = screen.getByRole('button', { name: '全部勾选' });
    fireEvent.click(toggleAllBtn);

    await waitFor(() => {
      expect(screen.getByText(/已识别画像事实 \(3\/3 已勾选\):/)).toBeInTheDocument();
    });

    // Toggle select all (from all to none)
    const cancelAllBtn = screen.getByRole('button', { name: '取消全选' });
    fireEvent.click(cancelAllBtn);

    await waitFor(() => {
      expect(screen.getByText(/已识别画像事实 \(0\/3 已勾选\):/)).toBeInTheDocument();
    });
  });

  it('executes one-click memory ingestion and renders confirmation audit badge', async () => {
    mockScanAgentSources.mockResolvedValueOnce(mockScanSummary);
    mockGenerateFirstEncounterReport.mockResolvedValueOnce(mockReport);
    mockConfirmInsightIngest.mockResolvedValueOnce(mockIngestSuccess);

    render(<FirstEncounterReportCard initialTargetAgentId="agent-primary" />);

    fireEvent.click(screen.getByRole('button', { name: /生成初见技术画像报告/ }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /一键确认沉淀入记忆库 \(3 项\)/ })).toBeInTheDocument();
    });

    const commitBtn = screen.getByRole('button', { name: /一键确认沉淀入记忆库 \(3 项\)/ });
    fireEvent.click(commitBtn);

    await waitFor(() => {
      expect(mockConfirmInsightIngest).toHaveBeenCalledWith(
        expect.objectContaining({
          report_id: 'rep-test-999',
          selected_fact_ids: ['fact-pref-01', 'fact-less-02', 'fact-goal-03'],
          target_agent_id: 'agent-primary',
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText('成功将 3 项初见技术画像沉淀至持久化记忆库')).toBeInTheDocument();
      expect(screen.getByText('新增 3 / 去重 0')).toBeInTheDocument();
    });
  });
});
