import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  SubagentFailurePolicyCard,
  RolePolicyItem,
  RemediationDecisionItem,
} from '../SubagentFailurePolicyCard';

describe('SubagentFailurePolicyCard', () => {
  const samplePolicy: RolePolicyItem = {
    role_key: 'coder',
    primary_action: 'restart_fresh',
    allow_failure: false,
    max_retries: 3,
    fallback_action: 'escalate_parent',
    fresh_instructions_template: 'Fix previous error {{error}}',
    redeploy_model_tier_downgrade: false,
  };

  const sampleDecision: RemediationDecisionItem = {
    event_id: 'evt_fail_101',
    task_id: 'task_worker_99',
    role_key: 'coder',
    action: 'restart_fresh',
    attempt_number: 2,
    max_retries: 3,
    rationale: 'Subagent crashed due to out of memory; restarting worker with cleaned context.',
  };

  it('renders idle state gracefully when no active failure decision is present', () => {
    render(
      <SubagentFailurePolicyCard
        chatId="chat_12345678_abcd"
        policy={samplePolicy}
      />,
    );

    expect(screen.getByText(/Subagent Mid-Task Failure Policy/i)).toBeInTheDocument();
    expect(screen.getByText(/All Subagents Running Normally/i)).toBeInTheDocument();
  });

  it('renders active failure remediation decision details and triggers actions', () => {
    const handleReset = vi.fn();
    const handleEscalate = vi.fn();

    render(
      <SubagentFailurePolicyCard
        chatId="chat_12345678_abcd"
        policy={samplePolicy}
        latestDecision={sampleDecision}
        onResetCounter={handleReset}
        onManualEscalate={handleEscalate}
      />,
    );

    expect(screen.getByText(/Task: task_worker_99/i)).toBeInTheDocument();
    expect(screen.getByText(/Restart Fresh/i)).toBeInTheDocument();
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    expect(screen.getByText(/Subagent crashed due to out of memory/i)).toBeInTheDocument();

    // Trigger Reset Counter
    const resetBtn = screen.getByRole('button', { name: /Reset Counter/i });
    fireEvent.click(resetBtn);
    expect(handleReset).toHaveBeenCalledWith('task_worker_99');

    // Trigger Manual Escalate
    const escalateBtn = screen.getByRole('button', { name: /Manual Escalate/i });
    fireEvent.click(escalateBtn);
    expect(handleEscalate).toHaveBeenCalledWith(
      'task_worker_99',
      'Manual intervention requested from UI',
    );
  });

  it('switches to declarative policy tab, edits form, and calls onSavePolicy', () => {
    const handleSave = vi.fn();

    render(
      <SubagentFailurePolicyCard
        chatId="chat_12345678_abcd"
        policy={samplePolicy}
        onSavePolicy={handleSave}
      />,
    );

    // Switch to settings tab
    const settingsTab = screen.getByRole('button', { name: /Declarative Policy/i });
    fireEvent.click(settingsTab);

    // Change role key input
    const roleInput = screen.getByLabelText(/Role Key:/i);
    fireEvent.change(roleInput, { target: { value: 'reviewer' } });

    // Change action select
    const actionSelect = screen.getByLabelText(/Primary Action:/i);
    fireEvent.change(actionSelect, { target: { value: 'redeploy_specs' } });

    // Click Save
    const saveBtn = screen.getByRole('button', { name: /Save Policy/i });
    fireEvent.click(saveBtn);

    expect(handleSave).toHaveBeenCalledWith(
      expect.objectContaining({
        role_key: 'reviewer',
        primary_action: 'redeploy_specs',
      }),
    );
  });

  it('calls onDismiss when close button is clicked', () => {
    const handleDismiss = vi.fn();

    render(
      <SubagentFailurePolicyCard
        chatId="chat_12345678_abcd"
        policy={samplePolicy}
        onDismiss={handleDismiss}
      />,
    );

    const closeBtn = screen.getByRole('button', { name: /Dismiss Policy Card/i });
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });
});
