/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FourLayerPromotionAuditCard } from '../command-center/FourLayerPromotionAuditCard';

const {
  mockListActiveCapabilityMethods,
  mockVerifyRulesCompliance,
  mockRollbackConsolidationBatch,
} = vi.hoisted(() => ({
  mockListActiveCapabilityMethods: vi.fn(),
  mockVerifyRulesCompliance: vi.fn(),
  mockRollbackConsolidationBatch: vi.fn(),
}));

vi.mock('@/services/memory/fourLayerPromotion', () => ({
  listActiveCapabilityMethods: mockListActiveCapabilityMethods,
  verifyRulesCompliance: mockVerifyRulesCompliance,
  rollbackConsolidationBatch: mockRollbackConsolidationBatch,
}));

describe('FourLayerPromotionAuditCard', () => {
  const mockMethods = [
    {
      method_id: 'method-bj-route-1',
      title: '大跨区核心景点独占日规则',
      applies_when: '多跨区大景点行程规划',
      method_steps: ['核心景点独占一天', '杜绝同日塞入两处以上远距离大项'],
      validation_criteria: '单日行程交通耗时不超过2小时',
      failure_signals: ['tool returned error', 'navigation timeout'],
      supported_event_ids: ['evt-bj-fail-1', 'evt-xa-fail-2'],
      promotion_channel: 'tool_failure_evidence',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockListActiveCapabilityMethods.mockResolvedValue(mockMethods);
    mockVerifyRulesCompliance.mockResolvedValue({
      items: [
        {
          rule_id: 'method-bj-route-1',
          statement: '核心景点独占一天',
          compliant: true,
          rationale: 'Complies with consolidated rule',
        },
      ],
      all_compliant: true,
    });
    mockRollbackConsolidationBatch.mockResolvedValue({
      batch_id: 'batch-test-101',
      success: true,
      reverted_method_ids: ['method-bj-route-1'],
    });
  });

  it('renders four-layer hierarchy overview and active capability methods', async () => {
    render(<FourLayerPromotionAuditCard />);

    await waitFor(() => {
      expect(
        screen.getByText('四层记忆晋升与防静默污染审计 (Four-Layer Promotion Audit)'),
      ).toBeDefined();
    });

    expect(screen.getByText('1. Working')).toBeDefined();
    expect(screen.getByText('2. Raw Episodic')).toBeDefined();
    expect(screen.getByText('3. Consolidated')).toBeDefined();
    expect(screen.getByText('4. Method Card')).toBeDefined();
    expect(screen.getByText('大跨区核心景点独占日规则')).toBeDefined();
    expect(screen.getByText('工具失败断言 (FAILURE)')).toBeDefined();
    expect(screen.getByText(/evt-bj-fail-1, evt-xa-fail-2/)).toBeDefined();
  });

  it('verifies rules compliance contract correctly', async () => {
    render(<FourLayerPromotionAuditCard />);

    await waitFor(() => {
      expect(screen.getByText('大跨区核心景点独占日规则')).toBeDefined();
    });

    const input = screen.getByPlaceholderText(/输入待核验回复/i);
    fireEvent.change(input, { target: { value: '故宫安排一整天游览' } });

    const verifyBtn = screen.getByRole('button', { name: /核验契约/i });
    fireEvent.click(verifyBtn);

    await waitFor(() => {
      expect(mockVerifyRulesCompliance).toHaveBeenCalledWith({
        response_text: '故宫安排一整天游览',
      });
      expect(screen.getByText('契约遵守通过: 核心景点独占一天')).toBeDefined();
    });
  });

  it('triggers atomic batch rollback on untrusted exposure', async () => {
    render(<FourLayerPromotionAuditCard />);

    await waitFor(() => {
      expect(screen.getByText('大跨区核心景点独占日规则')).toBeDefined();
    });

    const batchInput = screen.getByPlaceholderText(/批次号/i);
    fireEvent.change(batchInput, { target: { value: 'batch-test-101' } });

    const rollbackBtn = screen.getByRole('button', { name: /原子回滚/i });
    await waitFor(() => {
      expect(rollbackBtn.hasAttribute('disabled')).toBe(false);
    });
    fireEvent.click(rollbackBtn);

    await waitFor(() => {
      expect(mockRollbackConsolidationBatch).toHaveBeenCalledWith({
        batch_id: 'batch-test-101',
      });
      expect(screen.getByText(/原子回滚成功，撤销 1 个方法卡/)).toBeDefined();
    });
  });
});
