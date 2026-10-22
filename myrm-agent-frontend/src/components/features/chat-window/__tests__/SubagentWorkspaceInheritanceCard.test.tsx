import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SubagentWorkspaceInheritanceCard } from '../SubagentWorkspaceInheritanceCard';

describe('SubagentWorkspaceInheritanceCard', () => {
  it('renders initial workspace inheritance rules and budget allocation bar', () => {
    const handleDismiss = vi.fn();
    render(
      <SubagentWorkspaceInheritanceCard
        chatId="test-chat-01"
        workspaceRoot="/test/workspace"
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByTestId('workspace-inheritance-card')).toBeInTheDocument();
    expect(screen.getByText(/Root:/)).toBeInTheDocument();
    expect(screen.getByText('/test/workspace')).toBeInTheDocument();
    expect(screen.getByTestId('budget-bar')).toBeInTheDocument();
    expect(screen.getByTestId('rules-list')).toBeInTheDocument();

    // Verify default rules
    expect(screen.getByText('Code Quality & Lint Guardrails')).toBeInTheDocument();
    expect(screen.getByText('Subagent Collaboration & Memory Protocol')).toBeInTheDocument();
    expect(screen.getByText('Project Architecture Conventions')).toBeInTheDocument();

    // Dismiss button
    const closeBtn = screen.getByTestId('close-btn');
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('triggers rescan and updates rules list', () => {
    render(<SubagentWorkspaceInheritanceCard chatId="test-chat-02" />);

    const rescanBtn = screen.getByTestId('rescan-btn');
    fireEvent.click(rescanBtn);
    expect(screen.getByTestId('rules-list')).toBeInTheDocument();
    expect(screen.getByText('Code Quality & Lint Guardrails')).toBeInTheDocument();
  });

  it('allows changing role and budget slider', () => {
    render(<SubagentWorkspaceInheritanceCard chatId="test-chat-03" />);

    const roleSelect = screen.getByTestId('role-select');
    fireEvent.change(roleSelect, { target: { value: 'reviewer' } });
    expect(roleSelect).toHaveValue('reviewer');

    const slider = screen.getByLabelText(/Max Budget:/i);
    fireEvent.change(slider, { target: { value: '1500' } });
    expect(screen.getByText('1500 t')).toBeInTheDocument();
  });

  it('enriches child prompt, switches to preview tab, and triggers onEnrichSuccess callback', () => {
    const handleEnrichSuccess = vi.fn();
    render(
      <SubagentWorkspaceInheritanceCard
        chatId="test-chat-04"
        onEnrichSuccess={handleEnrichSuccess}
      />
    );

    const enrichBtn = screen.getByTestId('enrich-btn');
    fireEvent.click(enrichBtn);

    expect(screen.getByTestId('prompt-preview')).toBeInTheDocument();
    expect(screen.getByText(/Injected:/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue(/=== WORKSPACE INHERITED CONTEXT/i)).toBeInTheDocument();
    expect(handleEnrichSuccess).toHaveBeenCalledTimes(1);
  });

  it('navigates to audit trail tab and displays historical records', () => {
    render(<SubagentWorkspaceInheritanceCard chatId="test-chat-05" />);

    // Click on Audit Trail tab
    const auditTabBtn = screen.getByRole('button', { name: /Audit Trail/i });
    fireEvent.click(auditTabBtn);

    expect(screen.getByTestId('audit-history')).toBeInTheDocument();
    expect(screen.getByText(/\[WORKER\]/i)).toBeInTheDocument();
    expect(screen.getByText(/3 rules/i)).toBeInTheDocument();
  });

  it('triggers compacting when rule tokens exceed small budget', () => {
    render(<SubagentWorkspaceInheritanceCard chatId="test-chat-06" />);

    // Set a very small budget that is lower than default rule tokens (275)
    const slider = screen.getByLabelText(/Max Budget:/i);
    fireEvent.change(slider, { target: { value: '100' } });

    const enrichBtn = screen.getByTestId('enrich-btn');
    fireEvent.click(enrichBtn);

    expect(screen.getByTestId('prompt-preview')).toBeInTheDocument();
    expect(screen.getByText('Compacted')).toBeInTheDocument();
  });
});
