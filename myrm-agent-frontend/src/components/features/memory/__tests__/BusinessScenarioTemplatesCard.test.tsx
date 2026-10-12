/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/businessTemplates::fetchBusinessTemplates, evaluateEscalationGate, recordTemplateValidation
 * ../command-center/BusinessScenarioTemplatesCard::BusinessScenarioTemplatesCard
 *
 * [OUTPUT]
 * Test suite verifying Business Scenario Experience Templates & Escalation Gate Card:
 * 1. Initial render of HUD metrics & Business Analysis 3-Method Template
 * 2. Evolution feedback recording on review template
 * 3. Retail exchange 5-stage interactive checklist transitions
 * 4. Human escalation gate evaluation with policy ambiguity & clean flow presets
 *
 * [POS]
 * Unit test for Item 107 (BusinessScenarioExperienceTemplatesAndEscalationChecklistSuite).
 * Strict typing applied: No `any` types allowed. File lines < 300.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BusinessScenarioTemplatesCard } from '../command-center/BusinessScenarioTemplatesCard';
import type {
  BusinessExperienceTemplateDTO,
  EscalationEvaluationResponseDTO,
  ListTemplatesResponseDTO,
  RecordValidationResponseDTO,
} from '@/services/memory/businessTemplates';
import {
  FALLBACK_BUSINESS_ANALYSIS_TEMPLATE,
  FALLBACK_RETAIL_EXCHANGE_TEMPLATE,
  FALLBACK_ESCALATION_GATE_TEMPLATE,
} from '../command-center/businessTemplateFallbacks';

const {
  mockFetchBusinessTemplates,
  mockEvaluateEscalationGate,
  mockRecordTemplateValidation,
} = vi.hoisted(() => ({
  mockFetchBusinessTemplates: vi.fn(),
  mockEvaluateEscalationGate: vi.fn(),
  mockRecordTemplateValidation: vi.fn(),
}));

vi.mock('@/services/memory/businessTemplates', () => ({
  fetchBusinessTemplates: mockFetchBusinessTemplates,
  evaluateEscalationGate: mockEvaluateEscalationGate,
  recordTemplateValidation: mockRecordTemplateValidation,
}));

describe('BusinessScenarioTemplatesCard', () => {
  const sampleTemplatesList: BusinessExperienceTemplateDTO[] = [
    FALLBACK_BUSINESS_ANALYSIS_TEMPLATE,
    FALLBACK_RETAIL_EXCHANGE_TEMPLATE,
    FALLBACK_ESCALATION_GATE_TEMPLATE,
  ];

  const mockListResponse: ListTemplatesResponseDTO = {
    status: 'ok',
    total_count: 3,
    templates: sampleTemplatesList,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchBusinessTemplates.mockResolvedValue(mockListResponse);
  });

  it('renders card header, HUD bar, and business analysis review methods by default', async () => {
    render(<BusinessScenarioTemplatesCard />);

    // Header and title
    expect(
      screen.getByText('业务场景经验模板与转人工门禁工作台'),
    ).toBeInTheDocument();
    expect(screen.getByText('P0 Item 107')).toBeInTheDocument();

    // 4 HUD metrics
    await waitFor(() => {
      expect(screen.getByText('3 Active Schemas')).toBeInTheDocument();
    });
    expect(screen.getByText('3 Reusable Rules')).toBeInTheDocument();
    expect(screen.getByText('5-Stage Protocol')).toBeInTheDocument();

    // Default Tab: Business Analysis Review methods
    expect(screen.getByText('复杂表格公式计算值回查')).toBeInTheDocument();
    expect(screen.getByText('多源冲突数据口径显式核对')).toBeInTheDocument();
    expect(screen.getByText('交付前规范模板验收检查')).toBeInTheDocument();
  });

  it('submits validation feedback on business analysis review template', async () => {
    const mockValResponse: RecordValidationResponseDTO = {
      status: 'ok',
      record_id: 'val_test_99',
      template_id: 'BA-REV-01',
      is_validated: true,
      validated_count: 13,
      rejected_count: 0,
      timestamp: '2026-10-08T06:00:00Z',
    };
    mockRecordTemplateValidation.mockResolvedValueOnce(mockValResponse);

    render(<BusinessScenarioTemplatesCard />);

    await waitFor(() => {
      expect(screen.getByText(/验证通过 \(12\)/i)).toBeInTheDocument();
    });

    const approveBtn = screen.getByRole('button', { name: /验证通过 \(12\)/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(mockRecordTemplateValidation).toHaveBeenCalledWith({
        template_id: 'BA-REV-01',
        is_validated: true,
        note: expect.stringContaining('Operator confirmed'),
      });
      expect(screen.getByText(/验证成功已记录/i)).toBeInTheDocument();
    });
  });

  it('switches to retail exchange tab and toggles checklist steps', async () => {
    render(<BusinessScenarioTemplatesCard />);

    const retailTabBtn = screen.getByRole('button', {
      name: /^换货先问必查全链路$/i,
    });
    fireEvent.click(retailTabBtn);

    // 5 Stages rendered
    expect(
      screen.getByText(/阶段 1: 先问: 身份、订单号与换货诉求/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/阶段 2: 必查: 物流履约状态、售后政策与目标库存/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/阶段 3: 显式确认: 换货明细与寄回协议/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/阶段 4: 办理: 原子创建换货单与物流标签/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/阶段 5: 告知后续: 退货指引与新包裹时效/i),
    ).toBeInTheDocument();

    // Reset all steps
    const resetBtn = screen.getByRole('button', { name: /^重置步骤$/i });
    fireEvent.click(resetBtn);
    expect(screen.getByText(/进度: 0 \/ 5/i)).toBeInTheDocument();

    // One-click complete all
    const completeAllBtn = screen.getByRole('button', {
      name: /^一键全部勾选$/i,
    });
    fireEvent.click(completeAllBtn);
    expect(screen.getByText(/进度: 5 \/ 5/i)).toBeInTheDocument();
    expect(
      screen.getByText(/全链路规程满足，允许办理换货/i),
    ).toBeInTheDocument();
  });

  it('switches to escalation gate tab and simulates custom product escalation', async () => {
    const mockEscalationDecision: EscalationEvaluationResponseDTO = {
      action: 'escalate_to_human',
      reason: 'policy_ambiguity',
      message: '订单涉及特殊定制品类或退换货政策存在歧义条款，已阻断自主办理并触发人工客服审核。',
      required_context: { order_id: 'ORD-2026-X09', policy_issue: 'custom_order' },
      suggested_skill_or_tool: 'route_to_human_specialist',
    };
    mockEvaluateEscalationGate.mockResolvedValueOnce(mockEscalationDecision);

    render(<BusinessScenarioTemplatesCard />);

    const escalationTabBtn = screen.getByRole('button', {
      name: /^例外转人工决策门禁$/i,
    });
    fireEvent.click(escalationTabBtn);

    // Presets bar
    expect(screen.getByText(/快速仿真预设:/i)).toBeInTheDocument();

    // Click custom order preset
    const customPresetBtn = screen.getByRole('button', {
      name: /^定制\/政策模糊$/i,
    });
    fireEvent.click(customPresetBtn);

    // Click evaluate
    const evalBtn = screen.getByRole('button', { name: /^评估门禁$/i });
    fireEvent.click(evalBtn);

    await waitFor(() => {
      expect(mockEvaluateEscalationGate).toHaveBeenCalledWith(
        expect.objectContaining({
          is_custom_order: true,
          policy_clear: false,
        }),
      );
      expect(screen.getByText('ESCALATE_TO_HUMAN')).toBeInTheDocument();
      expect(screen.getByText('route_to_human_specialist')).toBeInTheDocument();
    });
  });

  it('evaluates clean automated flow successfully', async () => {
    const mockAutomatedDecision: EscalationEvaluationResponseDTO = {
      action: 'proceed_automated',
      reason: 'none',
      message: '所有先问与必查前置条件已验证通过，且用户已显式确认明细，允许自主执行办理。',
      required_context: { order_id: 'ORD-2026-X09' },
      suggested_skill_or_tool: 'commit_retail_exchange',
    };
    mockEvaluateEscalationGate.mockResolvedValueOnce(mockAutomatedDecision);

    render(<BusinessScenarioTemplatesCard />);

    const escalationTabBtn = screen.getByRole('button', {
      name: /^例外转人工决策门禁$/i,
    });
    fireEvent.click(escalationTabBtn);

    // Click clean flow preset
    const cleanPresetBtn = screen.getByRole('button', {
      name: /^标准合规流\(放行\)$/i,
    });
    fireEvent.click(cleanPresetBtn);

    const evalBtn = screen.getByRole('button', { name: /^评估门禁$/i });
    fireEvent.click(evalBtn);

    await waitFor(() => {
      expect(mockEvaluateEscalationGate).toHaveBeenCalledWith(
        expect.objectContaining({
          is_custom_order: false,
          policy_clear: true,
          inventory_available: true,
          user_confirmed: true,
        }),
      );
      expect(screen.getByText('PROCEED_AUTOMATED')).toBeInTheDocument();
      expect(screen.getByText('commit_retail_exchange')).toBeInTheDocument();
    });
  });
});
