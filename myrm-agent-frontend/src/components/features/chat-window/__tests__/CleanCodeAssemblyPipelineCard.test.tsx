import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { CleanCodeAssemblyPipelineCard } from '../CleanCodeAssemblyPipelineCard';

describe('CleanCodeAssemblyPipelineCard', () => {
  it('renders clean code assembly pipeline header, task id, and 5 stages', () => {
    const handleDismiss = vi.fn();
    render(
      <CleanCodeAssemblyPipelineCard
        taskId="clean-task-101"
        sessionId="sess-test-clean"
        onDismiss={handleDismiss}
      />
    );

    expect(
      screen.getByRole('region', {
        name: /Clean-Code Assembly Pipeline/i,
      })
    ).toBeInTheDocument();
    expect(screen.getByText('Clean-Code Assembly Pipeline')).toBeInTheDocument();
    expect(screen.getByText('clean-task-101')).toBeInTheDocument();

    // Verify 5 stages are present
    expect(screen.getByText('Specifier')).toBeInTheDocument();
    expect(screen.getByText('Coder')).toBeInTheDocument();
    expect(screen.getByText('Cleaner')).toBeInTheDocument();
    expect(screen.getByText('Hardener')).toBeInTheDocument();
    expect(screen.getByText('QA Signoff')).toBeInTheDocument();

    // Verify dismiss button
    const closeBtn = screen.getByLabelText('Close Clean-Code pipeline card');
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('allows switching selected stage to inspect deliverables', () => {
    render(<CleanCodeAssemblyPipelineCard />);

    // Click on Specifier stage
    const specifierBtn = screen.getByText('Specifier').closest('button');
    expect(specifierBtn).not.toBeNull();
    if (specifierBtn) {
      fireEvent.click(specifierBtn);
    }

    // Specifier deliverable artifact should be visible
    expect(screen.getByText('Formal Interface Contracts')).toBeInTheDocument();

    // Click on Hardener stage
    const hardenerBtn = screen.getByText('Hardener').closest('button');
    expect(hardenerBtn).not.toBeNull();
    if (hardenerBtn) {
      fireEvent.click(hardenerBtn);
    }

    // Should indicate no artifact yet
    expect(
      screen.getByText(/No deliverable artifact produced for this stage yet/i)
    ).toBeInTheDocument();
  });

  it('advances stage upon clicking Advance Stage', async () => {
    const handleAdvance = vi.fn();
    render(<CleanCodeAssemblyPipelineCard onAdvanceComplete={handleAdvance} />);

    const advanceBtn = screen.getByRole('button', { name: /Advance Stage/i });
    fireEvent.click(advanceBtn);

    await waitFor(
      () => {
        expect(
          screen.getByText(/Successfully advanced to 3. Cleaner/i)
        ).toBeInTheDocument();
      },
      { timeout: 1500 }
    );
    expect(handleAdvance).toHaveBeenCalledTimes(1);
  });

  it('handles architecture violation trigger and DIP remediation', () => {
    render(<CleanCodeAssemblyPipelineCard />);

    // Trigger simulated violation
    const simBtn = screen.getByRole('button', { name: /Simulate Violation/i });
    fireEvent.click(simBtn);

    // Verify violation banner appears
    expect(screen.getByText(/Architecture Boundary Violations/i)).toBeInTheDocument();
    expect(screen.getAllByText(/src\.domain\.payment/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Gate Blocked/i)).toBeInTheDocument();

    // Verify Advance Stage button is disabled
    const advanceBtn = screen.getByRole('button', { name: /Advance Stage/i });
    expect(advanceBtn).toBeDisabled();

    // Apply DIP Fix
    const fixBtn = screen.getByRole('button', { name: /Apply DIP Fix/i });
    fireEvent.click(fixBtn);

    // Gate should be unblocked
    expect(screen.queryByText(/Architecture Boundary Violations/i)).not.toBeInTheDocument();
    expect(advanceBtn).not.toBeDisabled();
  });
});
