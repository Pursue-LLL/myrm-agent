/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { HindsightReflectionCard } from '../command-center/HindsightReflectionCard';

const {
  mockGetHindsightBufferStats,
  mockListHindsightRules,
  mockQueryPreExecutionWarnings,
  mockReflectTaskFailure,
} = vi.hoisted(() => ({
  mockGetHindsightBufferStats: vi.fn(),
  mockListHindsightRules: vi.fn(),
  mockQueryPreExecutionWarnings: vi.fn(),
  mockReflectTaskFailure: vi.fn(),
}));

vi.mock('@/services/memory/hindsight', () => ({
  getHindsightBufferStats: mockGetHindsightBufferStats,
  listHindsightRules: mockListHindsightRules,
  queryPreExecutionWarnings: mockQueryPreExecutionWarnings,
  reflectTaskFailure: mockReflectTaskFailure,
}));

describe('HindsightReflectionCard', () => {
  const mockStats = {
    total_rules: 12,
    avg_confidence: 0.88,
    total_hits: 34,
  };

  const mockRules = [
    {
      rule_id: 'rule-rm-protect',
      task_pattern: 'clean temp build artifacts',
      mistake_signature: 'rm -rf root directory',
      correction_advice: 'Always verify directory path exists within workspace before deletion.',
      tags: ['cleanup', 'fs'],
      confidence: 0.95,
      hit_count: 5,
      created_at: 1728300000,
    },
  ];

  const mockWarningsResult = {
    task_goal: 'Clean temp build artifacts in workspace',
    total_warnings: 1,
    warnings: [
      {
        rule_id: 'rule-rm-protect',
        task_pattern: 'clean temp build artifacts',
        warning_text: 'Detected destructive deletion pattern matching historical crash.',
        recommended_action: 'Ensure relative path constraints and probe file existence before invoking removal.',
        confidence: 0.95,
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetHindsightBufferStats.mockResolvedValue(mockStats);
    mockListHindsightRules.mockResolvedValue(mockRules);
  });

  it('renders telemetry HUD and initial rules on mount', async () => {
    render(<HindsightReflectionCard />);

    await waitFor(() => {
      expect(mockGetHindsightBufferStats).toHaveBeenCalledTimes(1);
      expect(mockListHindsightRules).toHaveBeenCalledTimes(1);
    });

    expect(
      screen.getByText(/事后经验反思与失败任务回放缓冲池/i),
    ).toBeInTheDocument();
    expect(screen.getByText('反事实推理 HER')).toBeInTheDocument();
    expect(screen.getByText('前置避坑拦截')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('88%')).toBeInTheDocument();
    expect(screen.getByText('34')).toBeInTheDocument();
  });

  it('queries pre-execution warnings for a task goal and displays warning card', async () => {
    mockQueryPreExecutionWarnings.mockResolvedValueOnce(mockWarningsResult);

    render(<HindsightReflectionCard />);

    await waitFor(() => {
      expect(mockGetHindsightBufferStats).toHaveBeenCalledTimes(1);
    });

    const queryBtn = screen.getByRole('button', { name: /匹配前置避坑预警/i });
    fireEvent.click(queryBtn);

    await waitFor(() => {
      expect(mockQueryPreExecutionWarnings).toHaveBeenCalledWith({
        task_goal: 'Clean temp build artifacts in workspace',
        top_k: 3,
      });
      expect(
        screen.getByText(/前置预警探测完成：匹配到 1 条历史避坑指南/),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(/Detected destructive deletion pattern matching historical crash/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Ensure relative path constraints and probe file existence/),
    ).toBeInTheDocument();
    expect(screen.getByText(/置信度: 95%/)).toBeInTheDocument();
  });

  it('simulates failure reflection extraction and refreshes buffer data', async () => {
    mockReflectTaskFailure.mockResolvedValueOnce({
      status: 'success',
      message: 'Hindsight reflection extracted and registered',
      rule: {
        rule_id: 'rule-port-8080',
        task_pattern: 'Launch production mock service',
        mistake_signature: 'Port 8080 already in use',
        correction_advice: 'Probe active network ports before binding socket listener.',
        tags: ['network', 'port'],
        confidence: 0.9,
        hit_count: 1,
        created_at: 1728300000,
      },
    });

    render(<HindsightReflectionCard />);

    await waitFor(() => {
      expect(mockGetHindsightBufferStats).toHaveBeenCalledTimes(1);
    });

    const goalInput = screen.getByPlaceholderText(/例如: npm run start/i);
    const errorInput = screen.getByPlaceholderText(/例如: Port 8080 is already in use/i);

    fireEvent.change(goalInput, { target: { value: 'npm run start' } });
    fireEvent.change(errorInput, { target: { value: 'Port 8080 is already allocated' } });

    const submitBtn = screen.getByRole('button', { name: /提炼反事实避坑规则并沉淀/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockReflectTaskFailure).toHaveBeenCalledTimes(1);
      expect(
        screen.getByText(/反事实避坑规则 \[rule-port-8080\] 提炼成功并沉淀入库/),
      ).toBeInTheDocument();
      expect(mockGetHindsightBufferStats).toHaveBeenCalledTimes(2);
      expect(mockListHindsightRules).toHaveBeenCalledTimes(2);
    });
  });
});
