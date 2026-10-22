import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DeliveryEvidenceDossierModal } from '../DeliveryEvidenceDossierModal';
import { HarnessEfficacyDeck } from '../HarnessEfficacyDeck';
import type {
  AssetFrictionMetric,
  DeliveryEvidenceDossier,
} from '../deliveryDossierTypes';

describe('HarnessEfficacyDeck & DeliveryEvidenceDossierModal', () => {
  const mockAssets: AssetFrictionMetric[] = [
    {
      skill_id: 'k8s_deploy',
      model_name: 'claude-3-5-sonnet',
      execution_mode: 'MULTI_TURN_AGENT',
      sample_count: 5,
      true_efficacy_rate_pct: 100.0,
      friction_index: 0.12,
      total_wasted_tokens: 250,
      rework_count: 0,
      retry_count: 1,
      health_tag: 'CORE_EFFICIENT',
      governance_advice: '🌟 核心高效资产：采纳率高且极低返工损耗。',
    },
    {
      skill_id: 'k8s_deploy',
      model_name: 'deepseek-chat',
      execution_mode: 'MULTI_TURN_AGENT',
      sample_count: 4,
      true_efficacy_rate_pct: 25.0,
      friction_index: 0.85,
      total_wasted_tokens: 8500,
      rework_count: 3,
      retry_count: 6,
      health_tag: 'FRICTION_ASSASSIN',
      governance_advice: '⚠️ 摩擦刺客资产：频繁死循环，建议重构。',
    },
    {
      skill_id: 'unit_test_gen',
      model_name: 'gpt-4o',
      execution_mode: 'SINGLE_SHOT',
      sample_count: 1,
      true_efficacy_rate_pct: 0.0,
      friction_index: 0.0,
      total_wasted_tokens: 0,
      rework_count: 0,
      retry_count: 0,
      health_tag: 'SAMPLE_INSUFFICIENT',
      governance_advice: '当前样本量不足，暂不作定论。',
    },
  ];

  const mockDossier: DeliveryEvidenceDossier = {
    dossier_id: 'dos_abc12345678',
    task_id: 'task-auth-01',
    execution_mode: 'MULTI_TURN_AGENT',
    spec: {
      task_goal: '实现双因素认证网关',
      acceptance_criteria: ['TOTP 动态验真', '单测 100% 绿灯'],
      non_goals: ['不支持 SMS 验证码'],
    },
    persona: {
      agent_id: 'agent-dev-01',
      model_name: 'claude-3-5-sonnet',
      prompt_hash: 'ph_sec9988',
      mounted_skills: ['bash', 'code_editor'],
    },
    tool_traces: [
      {
        tool_name: 'bash',
        arguments_summary: 'pytest tests/test_totp.py',
        duration_ms: 280.0,
        exit_code: 0,
      },
    ],
    verification: {
      test_suite_exit_code: 0,
      passed_tests_count: 8,
      failed_tests_count: 0,
      artifact_path: 'app/core/auth/totp.py',
      artifact_sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
      verified_at: '2026-10-12T16:00:00Z',
    },
    acceptance: 'ACCEPTED',
    total_tokens_consumed: 14_500,
    wasted_friction_tokens: 150,
    rework_count: 0,
    dossier_checksum_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    created_at: '2026-10-12T16:00:00Z',
  };

  it('renders efficacy deck KPI summary and stratified asset rows', () => {
    const handleInspect = vi.fn();
    render(<HarnessEfficacyDeck assets={mockAssets} onInspectSkill={handleInspect} />);

    expect(screen.getByText('跨智能体资产健康与效能大盘 (Better Harness 视角)')).toBeInTheDocument();
    expect(screen.getByTestId('core-count')).toHaveTextContent('1 个技能');
    expect(screen.getByTestId('assassin-count')).toHaveTextContent('1 个技能');
    expect(screen.getByTestId('total-wasted-tokens')).toHaveTextContent('8,750 Tokens');

    // 检查 sonnet 核心高效行
    const sonnetRow = screen.getByTestId('asset-row-k8s_deploy-claude-3-5-sonnet');
    expect(sonnetRow).toBeInTheDocument();
    expect(sonnetRow).toHaveTextContent('100%');
    expect(sonnetRow).toHaveTextContent('🌟 核心高效资产');

    // 检查 deepseek 刺客行
    const deepseekRow = screen.getByTestId('asset-row-k8s_deploy-deepseek-chat');
    expect(deepseekRow).toBeInTheDocument();
    expect(deepseekRow).toHaveTextContent('25%');
    expect(deepseekRow).toHaveTextContent('⚠️ 摩擦刺客资产');

    // 点击行触发回调
    fireEvent.click(sonnetRow);
    expect(handleInspect).toHaveBeenCalledWith('k8s_deploy', 'claude-3-5-sonnet');
  });

  it('filters assets by model stratification accurately', () => {
    render(<HarnessEfficacyDeck assets={mockAssets} />);

    const modelSelect = screen.getByTestId('model-filter-select');
    fireEvent.change(modelSelect, { target: { value: 'claude-3-5-sonnet' } });

    // 只应显示 sonnet
    expect(screen.getByTestId('asset-row-k8s_deploy-claude-3-5-sonnet')).toBeInTheDocument();
    expect(screen.queryByTestId('asset-row-k8s_deploy-deepseek-chat')).not.toBeInTheDocument();
    expect(screen.getByTestId('core-count')).toHaveTextContent('1 个技能');
    expect(screen.getByTestId('assassin-count')).toHaveTextContent('0 个技能');
  });

  it('filters assets by execution mode', () => {
    render(<HarnessEfficacyDeck assets={mockAssets} />);

    const modeSelect = screen.getByTestId('mode-filter-select');
    fireEvent.change(modeSelect, { target: { value: 'SINGLE_SHOT' } });

    // 只应显示 unit_test_gen
    expect(screen.getByTestId('asset-row-unit_test_gen-gpt-4o')).toBeInTheDocument();
    expect(screen.queryByTestId('asset-row-k8s_deploy-claude-3-5-sonnet')).not.toBeInTheDocument();
  });

  it('renders empty fallback message when no assets match filters', () => {
    render(<HarnessEfficacyDeck assets={[]} />);
    expect(screen.getByText('暂无匹配的资产度量记录')).toBeInTheDocument();
  });

  it('renders DeliveryEvidenceDossierModal and exports .dossier.json', () => {
    const handleClose = vi.fn();
    const createObjectURLMock = vi.fn(() => 'blob:mock-url');
    const revokeObjectURLMock = vi.fn();
    globalThis.URL.createObjectURL = createObjectURLMock;
    globalThis.URL.revokeObjectURL = revokeObjectURLMock;

    render(
      <DeliveryEvidenceDossierModal
        isOpen={true}
        onClose={handleClose}
        dossier={mockDossier}
      />
    );

    expect(screen.getByText('全链路任务交付证据卷宗')).toBeInTheDocument();
    expect(screen.getByTestId('acceptance-badge')).toHaveTextContent('✓ 直接采纳');
    expect(screen.getByTestId('dossier-id')).toHaveTextContent('dos_abc12345678');
    expect(screen.getByTestId('spec-goal')).toHaveTextContent('目标: 实现双因素认证网关');
    expect(screen.getByTestId('exit-code-badge')).toHaveTextContent('Exit Code: 0');
    expect(screen.getByTestId('traces-list')).toHaveTextContent('pytest tests/test_totp.py');

    // 点击导出
    fireEvent.click(screen.getByTestId('export-dossier-json-btn'));
    expect(createObjectURLMock).toHaveBeenCalled();

    // 点击关闭
    fireEvent.click(screen.getByTestId('modal-close-action-btn'));
    expect(handleClose).toHaveBeenCalled();
  });
});
