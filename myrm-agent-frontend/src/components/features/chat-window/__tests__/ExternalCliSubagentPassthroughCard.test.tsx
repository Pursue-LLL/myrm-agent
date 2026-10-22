import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ExternalCliSubagentPassthroughCard } from '../ExternalCliSubagentPassthroughCard';

describe('ExternalCliSubagentPassthroughCard', () => {
  it('renders header, workspace confinement, and 3 CLI bundles', () => {
    const handleDismiss = vi.fn();
    render(
      <ExternalCliSubagentPassthroughCard
        chatId="chat-test-passthrough"
        workspaceRoot="/workspace/test-repo"
        onDismiss={handleDismiss}
      />,
    );

    expect(
      screen.getByRole('region', {
        name: /External CLI Subagent Passthrough and BYOS Dispatcher/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('Session: chat-test-passthrough')).toBeInTheDocument();
    expect(screen.getAllByText('/workspace/test-repo').length).toBeGreaterThan(0);

    // Verify 3 CLI bundles
    expect(screen.getByText('Claude Code Subagent')).toBeInTheDocument();
    expect(screen.getByText('Codex CLI Subagent')).toBeInTheDocument();
    expect(screen.getByText('Cursor Agent CLI')).toBeInTheDocument();

    // Verify BYOS subscription tags
    expect(screen.getAllByText('ACTIVE_PRO').length).toBeGreaterThan(0);
    expect(screen.getByText('ACTIVE_TEAM')).toBeInTheDocument();

    // Dismiss button
    const closeBtn = screen.getByLabelText('Dismiss CLI Passthrough Card');
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('switches selected bundle and updates vendor disclosure terms', () => {
    render(<ExternalCliSubagentPassthroughCard />);

    // Initially Claude Code (Anthropic PBC) is selected
    expect(screen.getByText('Anthropic PBC')).toBeInTheDocument();

    // Switch to Codex CLI
    const codexBtn = screen.getByRole('button', {
      name: /Codex CLI Subagent/i,
    });
    fireEvent.click(codexBtn);

    expect(screen.getByText('OpenAI Inc.')).toBeInTheDocument();
  });

  it('enforces privacy gate: execution button is disabled until disclosure is acknowledged', () => {
    render(<ExternalCliSubagentPassthroughCard />);

    const dispatchBtn = screen.getByRole('button', {
      name: /Dispatch to claude \(BYOS\)/i,
    });
    expect(dispatchBtn).toBeDisabled();
    expect(
      screen.getByText(/\* Acknowledge privacy disclosure above before execution/i),
    ).toBeInTheDocument();
  });

  it('acknowledges privacy disclosure and executes headless task successfully', () => {
    const handleCompleted = vi.fn();
    const handleAcknowledged = vi.fn();

    render(
      <ExternalCliSubagentPassthroughCard
        onExecutionCompleted={handleCompleted}
        onPrivacyAcknowledged={handleAcknowledged}
      />,
    );

    // Acknowledge privacy disclosure
    const checkbox = screen.getByLabelText(
      /I acknowledge vendor terms & context transfer to Anthropic PBC/i,
    );
    fireEvent.click(checkbox);
    expect(handleAcknowledged).toHaveBeenCalledWith(
      expect.stringContaining('disc-bundle-claude-code'),
    );

    // Now dispatch button is enabled
    const dispatchBtn = screen.getByRole('button', {
      name: /Dispatch to claude \(BYOS\)/i,
    });
    expect(dispatchBtn).not.toBeDisabled();

    // Click dispatch
    fireEvent.click(dispatchBtn);

    // Verify completion
    expect(handleCompleted).toHaveBeenCalledTimes(1);
    expect(
      screen.getByText(/Execution Succeeded \(Exit Code: 0\)/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Tokens Saved/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Git Diff Output:/i)).toBeInTheDocument();
    expect(screen.getByText(/SHA-256 Audit:/i)).toBeInTheDocument();
  });
});
