/**
 * Unit & Integration tests for RiskConfirmationCard component.
 *
 * [INPUT] RiskConfirmationCard, mock callbacks
 * [OUTPUT] Vitest test suites verifying multi-tier rendering, dry-run simulation, and actions.
 * [POS] Item 29 frontend test coverage. Strictly under 250 lines. Zero `any`.
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RiskConfirmationCard } from './RiskConfirmationCard';
import type { TieredRiskEvaluation } from './riskApprovalTypes';

describe('RiskConfirmationCard', () => {
  const readEval: TieredRiskEvaluation = {
    tier: 'READ',
    tool_name: 'read_file',
    target_entity: '/workspace/README.md',
    risk_reasons: [],
    supports_dry_run: false,
    is_dry_run: false,
    need_confirmation: false,
    confirmation_token: null,
    suggested_action: 'pass',
    param_summary: { path: '/workspace/README.md' },
  };

  const writeEval: TieredRiskEvaluation = {
    tier: 'WRITE',
    tool_name: 'update_config',
    target_entity: 'settings.json',
    risk_reasons: ['State-mutating operation'],
    supports_dry_run: true,
    is_dry_run: false,
    need_confirmation: false,
    confirmation_token: null,
    suggested_action: 'review_summary',
    param_summary: { target: 'settings.json', mode: 'strict' },
  };

  const highRiskEval: TieredRiskEvaluation = {
    tier: 'HIGH_RISK',
    tool_name: 'delete_database',
    target_entity: 'production_cluster',
    risk_reasons: ['Irreversible database dropping', 'High blast radius'],
    supports_dry_run: true,
    is_dry_run: false,
    need_confirmation: true,
    confirmation_token: 'tok_test123456789',
    suggested_action: 'NEED_CONFIRMATION',
    param_summary: { database: 'production_cluster', force: 'true' },
  };

  it('renders Level 1 READ operation with fast-pass status', () => {
    const onConfirm = vi.fn();
    const onReject = vi.fn();

    render(
      <RiskConfirmationCard
        evaluation={readEval}
        onConfirm={onConfirm}
        onReject={onReject}
      />
    );

    expect(screen.getByText('read_file')).toBeInTheDocument();
    expect(screen.getAllByText('/workspace/README.md').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/只读操作/)).toBeInTheDocument();
    expect(screen.getByText('已放行')).toBeInTheDocument();
    expect(screen.queryByText('终止打回')).not.toBeInTheDocument();
  });

  it('renders Level 2 WRITE operation and handles dry-run trigger', async () => {
    const onConfirm = vi.fn();
    const onReject = vi.fn();
    const onSimulateDryRun = vi.fn().mockResolvedValue({
      simulated: true,
      tool_name: 'update_config',
      simulated_impact: 'Simulated 1 config update without persistent mutation',
      affected_target: 'settings.json',
      predicted_changes: ['Key "mode" set to "strict"'],
    });

    render(
      <RiskConfirmationCard
        evaluation={writeEval}
        onConfirm={onConfirm}
        onReject={onReject}
        onSimulateDryRun={onSimulateDryRun}
      />
    );

    expect(screen.getByText('update_config')).toBeInTheDocument();
    expect(screen.getByText(/状态写入/)).toBeInTheDocument();
    expect(screen.getByText('继续执行')).toBeInTheDocument();

    const dryRunBtn = screen.getByText('Dry-Run 预演');
    fireEvent.click(dryRunBtn);

    expect(onSimulateDryRun).toHaveBeenCalledWith('update_config', writeEval.param_summary);
    expect(await screen.findByText(/Dry-Run 预演模拟结果/)).toBeInTheDocument();
    expect(screen.getByText(/Simulated 1 config update/)).toBeInTheDocument();
  });

  it('renders Level 3 HIGH_RISK operation with warning alerts and token', () => {
    const onConfirm = vi.fn();
    const onReject = vi.fn();

    render(
      <RiskConfirmationCard
        evaluation={highRiskEval}
        onConfirm={onConfirm}
        onReject={onReject}
      />
    );

    expect(screen.getByText('delete_database')).toBeInTheDocument();
    expect(screen.getByText(/高危操作/)).toBeInTheDocument();
    expect(screen.getByText('Irreversible database dropping')).toBeInTheDocument();
    expect(screen.getByText('High blast radius')).toBeInTheDocument();
    expect(screen.getByText('终止打回')).toBeInTheDocument();
    expect(screen.getByText('授权并执行')).toBeInTheDocument();
  });

  it('triggers onConfirm callback with token upon authorization', async () => {
    const onConfirm = vi.fn();
    const onReject = vi.fn();

    render(
      <RiskConfirmationCard
        evaluation={highRiskEval}
        onConfirm={onConfirm}
        onReject={onReject}
      />
    );

    const confirmBtn = screen.getByText('授权并执行');
    fireEvent.click(confirmBtn);

    expect(onConfirm).toHaveBeenCalledWith({
      confirmation_token: 'tok_test123456789',
      approved: true,
      modified_input: null,
      reason: 'Authorized via interactive risk gate',
    });
  });

  it('supports inline parameter editing and sends modified input', async () => {
    const onConfirm = vi.fn();
    const onReject = vi.fn();

    render(
      <RiskConfirmationCard
        evaluation={highRiskEval}
        onConfirm={onConfirm}
        onReject={onReject}
      />
    );

    const editBtn = screen.getByText('修改参数');
    fireEvent.click(editBtn);

    expect(screen.getByText(/修改执行参数/)).toBeInTheDocument();
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, {
      target: { value: JSON.stringify({ database: 'backup_cluster', force: false }) },
    });

    const modifiedConfirmBtn = screen.getByText('修改参数并执行');
    fireEvent.click(modifiedConfirmBtn);

    expect(onConfirm).toHaveBeenCalledWith({
      confirmation_token: 'tok_test123456789',
      approved: true,
      modified_input: { database: 'backup_cluster', force: false },
      reason: 'Authorized via interactive risk gate',
    });
  });

  it('handles operator rejection with custom reason input', () => {
    const onConfirm = vi.fn();
    const onReject = vi.fn();

    render(
      <RiskConfirmationCard
        evaluation={highRiskEval}
        onConfirm={onConfirm}
        onReject={onReject}
      />
    );

    const rejectBtn = screen.getByText('终止打回');
    fireEvent.click(rejectBtn);

    const input = screen.getByPlaceholderText(/输入拒绝理由/);
    fireEvent.change(input, { target: { value: 'Production write blocked by policy' } });

    const confirmRejectBtn = screen.getByText('确认打回');
    fireEvent.click(confirmRejectBtn);

    expect(onReject).toHaveBeenCalledWith('Production write blocked by policy');
  });
});
