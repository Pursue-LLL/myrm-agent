import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { VisualTimelineCherryPickCard } from '../VisualTimelineCherryPickCard';

describe('VisualTimelineCherryPickCard', () => {
  it('renders visual timeline header, session id, and initial nodes list', () => {
    const handleDismiss = vi.fn();
    render(
      <VisualTimelineCherryPickCard
        sessionId="sess-test-timeline"
        onDismiss={handleDismiss}
      />
    );

    expect(
      screen.getByRole('region', {
        name: /Multi-Agent Visual Timeline & Cherry-Pick Rollback/i,
      })
    ).toBeInTheDocument();
    expect(
      screen.getByText('Multi-Agent Visual Timeline & Cherry-Pick')
    ).toBeInTheDocument();
    expect(screen.getByText('sess-test-timeline')).toBeInTheDocument();

    // Check presence of initial nodes
    expect(screen.getByText('Lead Architect')).toBeInTheDocument();
    expect(screen.getByText('Database Optimizer Bot')).toBeInTheDocument();
    expect(screen.getByText('Junior Scaffold Bot')).toBeInTheDocument();

    // Check dismiss button
    const closeBtn = screen.getByLabelText('Close');
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('filters timeline nodes by search query and operation type', () => {
    render(<VisualTimelineCherryPickCard />);

    // Filter by operation: file_create
    const opSelect = screen.getByLabelText('Filter by Operation');
    fireEvent.change(opSelect, { target: { value: 'file_create' } });
    expect(screen.getByText('Lead Architect')).toBeInTheDocument();
    expect(screen.queryByText('Database Optimizer Bot')).not.toBeInTheDocument();

    // Reset operation filter
    fireEvent.change(opSelect, { target: { value: 'all' } });

    // Search query: signature
    const searchInput = screen.getByPlaceholderText(/Search by file, actor, or diff/i);
    fireEvent.change(searchInput, { target: { value: 'signature' } });
    expect(screen.getByText('Junior Scaffold Bot')).toBeInTheDocument();
    expect(screen.queryByText('Lead Architect')).not.toBeInTheDocument();
  });

  it('toggles diff expansion to inspect before and after code changes', () => {
    render(<VisualTimelineCherryPickCard />);

    const expandButtons = screen.getAllByLabelText('Expand Diff');
    expect(expandButtons.length).toBeGreaterThan(0);

    // Click the first expand button
    fireEvent.click(expandButtons[0]);
    expect(screen.getByText(/export const GATEWAY_TIMEOUT/i)).toBeInTheDocument();

    // Collapse
    const collapseButton = screen.getByLabelText('Collapse Diff');
    fireEvent.click(collapseButton);
    expect(screen.queryByText(/export const GATEWAY_TIMEOUT/i)).not.toBeInTheDocument();
  });

  it('performs cherry-pick undo on a targeted node with two-step confirmation', async () => {
    const handleRollbackComplete = vi.fn();
    render(
      <VisualTimelineCherryPickCard onRollbackComplete={handleRollbackComplete} />
    );

    // Target the junior scaffold bot node (node-bug-03)
    const undoButtons = screen.getAllByText('Cherry-Pick Undo');
    fireEvent.click(undoButtons[2]); // 3rd node

    // Confirmation prompt appears
    expect(screen.getByText(/Revert this node only\?/i)).toBeInTheDocument();
    const confirmBtn = screen.getByText('Confirm');
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText(/Node node-bug-03 reverted safely!/i)).toBeInTheDocument();
    });

    expect(screen.getByText('ROLLED BACK')).toBeInTheDocument();
    expect(handleRollbackComplete).toHaveBeenCalledWith(
      expect.objectContaining({
        nodeId: 'node-bug-03',
        status: 'success',
        filePath: 'src/auth/token_guard.py',
      })
    );
  });
});
