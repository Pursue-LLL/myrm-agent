/**
 * Unit & Integration tests for TieredRiskGateContainer.
 *
 * [INPUT] TieredRiskGateContainer, useRiskGateStore
 * [OUTPUT] Vitest test suite verifying host container lifecycle and event binding.
 * [POS] Item 29 container tests. Strictly under 200 lines. Zero `any`.
 */

import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { TieredRiskGateContainer } from './TieredRiskGateContainer';
import { useRiskGateStore } from '@/store/useRiskGateStore';
import type { TieredRiskEvaluation } from './riskApprovalTypes';

describe('TieredRiskGateContainer', () => {
  beforeEach(() => {
    act(() => {
      useRiskGateStore.getState().clearEvaluation();
    });
  });

  const mockEval: TieredRiskEvaluation = {
    tier: 'HIGH_RISK',
    tool_name: 'drop_table',
    target_entity: 'users_v2',
    risk_reasons: ['Database schema destruction'],
    supports_dry_run: true,
    is_dry_run: false,
    need_confirmation: true,
    confirmation_token: 'tok_drop_123',
    suggested_action: 'NEED_CONFIRMATION',
    param_summary: { table: 'users_v2' },
  };

  it('renders nothing when activeEvaluation is null', () => {
    const { container } = render(<TieredRiskGateContainer />);
    expect(container.firstChild).toBeNull();
  });

  it('renders confirmation card when activeEvaluation is set in store', () => {
    act(() => {
      useRiskGateStore.getState().setActiveEvaluation(mockEval);
    });

    render(<TieredRiskGateContainer />);

    expect(screen.getByText('drop_table')).toBeInTheDocument();
    expect(screen.getAllByText('users_v2').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Database schema destruction')).toBeInTheDocument();
    expect(screen.getByText('授权并执行')).toBeInTheDocument();
  });

  it('responds to global "myrm:tiered-risk-eval" custom event', () => {
    render(<TieredRiskGateContainer />);
    expect(screen.queryByText('drop_table')).not.toBeInTheDocument();

    act(() => {
      window.dispatchEvent(
        new CustomEvent('myrm:tiered-risk-eval', {
          detail: mockEval,
        })
      );
    });

    expect(screen.getByText('drop_table')).toBeInTheDocument();
  });

  it('clears activeEvaluation on authorization confirm', async () => {
    act(() => {
      useRiskGateStore.getState().setActiveEvaluation(mockEval);
    });

    render(<TieredRiskGateContainer />);

    const confirmBtn = screen.getByText('授权并执行');
    await act(async () => {
      fireEvent.click(confirmBtn);
    });

    expect(useRiskGateStore.getState().activeEvaluation).toBeNull();
    expect(screen.queryByText('drop_table')).not.toBeInTheDocument();
  });
});
