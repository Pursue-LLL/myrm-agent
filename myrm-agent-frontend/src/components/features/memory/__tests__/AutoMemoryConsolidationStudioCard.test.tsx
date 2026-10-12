/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory::getAutoConsolidationConfig, updateAutoConsolidationConfig, evaluateAutoConsolidationGating, consolidateSessionAutoMemory
 * ../command-center/AutoMemoryConsolidationStudioCard::AutoMemoryConsolidationStudioCard
 *
 * [OUTPUT]
 * Test suite verifying Idle & Budget Gated Auto-Memory Consolidation Studio Card (Item 123 P1):
 * 1. Default render of header, badges, and 4-dimension HUD telemetry bar
 * 2. Tab switching between monitor view and config tuner view
 * 3. Gating admission evaluation interaction
 * 4. Consolidation execution and 6D artifact update
 * 5. Configuration update and reset to default
 *
 * [POS]
 * Unit test for Item 123.
 * Strict typing: No `any` types. File lines < 250.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AutoMemoryConsolidationStudioCard } from '../command-center/AutoMemoryConsolidationStudioCard';
import {
  FALLBACK_AUTO_CONSOLIDATION_CONFIG,
  FALLBACK_GATING_REPORT_ADMITTED,
  FALLBACK_SIX_DIMENSIONAL_ARTIFACT,
} from '../command-center/autoMemoryConsolidationFallbacks';

const {
  mockGetAutoConsolidationConfig,
  mockUpdateAutoConsolidationConfig,
  mockEvaluateAutoConsolidationGating,
  mockConsolidateSessionAutoMemory,
} = vi.hoisted(() => ({
  mockGetAutoConsolidationConfig: vi.fn(),
  mockUpdateAutoConsolidationConfig: vi.fn(),
  mockEvaluateAutoConsolidationGating: vi.fn(),
  mockConsolidateSessionAutoMemory: vi.fn(),
}));

vi.mock('@/services/memory', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    getAutoConsolidationConfig: mockGetAutoConsolidationConfig,
    updateAutoConsolidationConfig: mockUpdateAutoConsolidationConfig,
    evaluateAutoConsolidationGating: mockEvaluateAutoConsolidationGating,
    consolidateSessionAutoMemory: mockConsolidateSessionAutoMemory,
  };
});

describe('AutoMemoryConsolidationStudioCard (Item 123 P1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetAutoConsolidationConfig.mockResolvedValue(FALLBACK_AUTO_CONSOLIDATION_CONFIG);
    mockUpdateAutoConsolidationConfig.mockResolvedValue(FALLBACK_AUTO_CONSOLIDATION_CONFIG);
    mockEvaluateAutoConsolidationGating.mockResolvedValue({
      report: FALLBACK_GATING_REPORT_ADMITTED,
    });
    mockConsolidateSessionAutoMemory.mockResolvedValue({
      report: FALLBACK_GATING_REPORT_ADMITTED,
      artifact: FALLBACK_SIX_DIMENSIONAL_ARTIFACT,
      persisted: true,
    });
  });

  it('renders default header, badges, and 4-dimension HUD telemetry bar', async () => {
    render(<AutoMemoryConsolidationStudioCard />);

    expect(
      screen.getByText('闲置自适应与双门禁会话记忆沉淀引擎'),
    ).toBeInTheDocument();
    expect(screen.getByText('Item 123 · P1')).toBeInTheDocument();
    expect(
      screen.getByText(/对标 CodeX 双门禁：对话太短不记，额度告急不记/),
    ).toBeInTheDocument();

    // 验证 HUD 4 维指标
    expect(screen.getByText('门禁综合准入')).toBeInTheDocument();
    expect(screen.getByText('会话闲置感知')).toBeInTheDocument();
    expect(screen.getByText('轮数与信息增益')).toBeInTheDocument();
    expect(screen.getByText('预算保护看门狗')).toBeInTheDocument();
  });

  it('switches between monitor and config tabs', async () => {
    render(<AutoMemoryConsolidationStudioCard />);

    // 默认在监控看板
    expect(screen.getByText('全景看板与沉淀')).toBeInTheDocument();
    expect(screen.getByText('六维结构化记忆切片 (art-6d-7f8e3b2a1c0d)')).toBeInTheDocument();

    // 切换至配置面板
    const configTabBtn = screen.getByRole('button', { name: '切换至双门禁规则调优面板' });
    fireEvent.click(configTabBtn);

    expect(
      screen.getByText('双门禁准入与闲置自适应阈值配置'),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText('会话闲置触发时长 (秒)'),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText('最小对话轮数门禁 (Turns)'),
    ).toBeInTheDocument();

    // 切回全景看板
    const monitorTabBtn = screen.getByRole('button', { name: '切换至门禁监视与切片视图' });
    fireEvent.click(monitorTabBtn);
    expect(screen.getByText('六维结构化记忆切片 (art-6d-7f8e3b2a1c0d)')).toBeInTheDocument();
  });

  it('triggers gating evaluation and updates audit verdict', async () => {
    render(<AutoMemoryConsolidationStudioCard />);

    const evalBtn = screen.getByRole('button', { name: '评估会话门禁准入' });
    fireEvent.click(evalBtn);

    await waitFor(() => {
      expect(mockEvaluateAutoConsolidationGating).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByText('门禁评估完成')).toBeInTheDocument();
  });

  it('triggers consolidation and updates 6D artifact viewer', async () => {
    render(<AutoMemoryConsolidationStudioCard />);

    const consolidateBtn = screen.getByRole('button', { name: '执行会话记忆沉淀' });
    fireEvent.click(consolidateBtn);

    await waitFor(() => {
      expect(mockConsolidateSessionAutoMemory).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByText('六维记忆切片归档成功！')).toBeInTheDocument();
    expect(
      screen.getByText('① 工作目录上下文 (Working Directory)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('② 核心技术主题词 (Key Topics)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('③ 用户个性偏好与规范 (User Preferences)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('④ 可复用工程经验 (Reusable Knowledge)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('⑤ 踩坑教训与自愈反思 (Failure Lessons)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('⑥ 工具调用特征与行为习惯 (Tool Habits)'),
    ).toBeInTheDocument();
  });

  it('handles config form update and reset to defaults', async () => {
    render(<AutoMemoryConsolidationStudioCard />);

    // 切换至配置页
    fireEvent.click(screen.getByRole('button', { name: '切换至双门禁规则调优面板' }));

    const idleInput = screen.getByLabelText('会话闲置触发时长 (秒)');
    fireEvent.change(idleInput, { target: { value: '600' } });

    const submitBtn = screen.getByRole('button', { name: '保存自动记忆门禁配置' });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockUpdateAutoConsolidationConfig).toHaveBeenCalledTimes(1);
    });

    // 恢复默认
    const resetBtn = screen.getByRole('button', { name: '恢复默认门禁配置' });
    fireEvent.click(resetBtn);
    expect(idleInput).toHaveValue(900);
  });
});
