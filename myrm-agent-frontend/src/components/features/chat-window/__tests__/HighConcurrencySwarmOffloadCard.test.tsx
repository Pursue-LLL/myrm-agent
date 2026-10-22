import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { HighConcurrencySwarmOffloadCard } from '../HighConcurrencySwarmOffloadCard';

describe('HighConcurrencySwarmOffloadCard', () => {
  it('renders swarm cockpit header, watermark metrics and default 12 workers grid', () => {
    const handleDismiss = vi.fn();
    render(
      <HighConcurrencySwarmOffloadCard
        batchId="batch-test-swarm-99"
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByRole('region', { name: /High-Concurrency Subagent Swarm Cockpit/i })).toBeInTheDocument();
    expect(screen.getByText('High-Concurrency Subagent Swarm (10–15 Workers)')).toBeInTheDocument();
    expect(screen.getByText('Item 60 Active')).toBeInTheDocument();
    expect(screen.getByText(/Batch: batch-test-swarm-99/i)).toBeInTheDocument();

    // Check host physical watermark decks
    expect(screen.getByText('Host CPU Load')).toBeInTheDocument();
    expect(screen.getByText('42%')).toBeInTheDocument();
    expect(screen.getByText('Host Memory Load')).toBeInTheDocument();
    expect(screen.getByText('55%')).toBeInTheDocument();
    expect(screen.getByText('Local Worker Load')).toBeInTheDocument();
    expect(screen.getByText('SAFE CAPACITY')).toBeInTheDocument();

    // Check 12 workers grid presence
    expect(screen.getByText(/Active Concurrent Worker Swarm Grid \(12\)/i)).toBeInTheDocument();
    expect(screen.getByText('JWT Auth Unit Tests')).toBeInTheDocument();
    expect(screen.getByText('Cargo Release Build')).toBeInTheDocument();
    expect(screen.getByText('Heavy PDF Multi-Page OCR')).toBeInTheDocument();

    // Test dismiss callback
    const closeBtn = screen.getByLabelText('Close Swarm Cockpit');
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('switches offload policies between adaptive, force local, and force cloud', () => {
    render(<HighConcurrencySwarmOffloadCard />);

    // Switch to Force Cloud
    const forceCloudBtn = screen.getByText('Force Cloud');
    fireEvent.click(forceCloudBtn);
    expect(screen.getByText('0 Local')).toBeInTheDocument();
    expect(screen.getByText('12 Cloud')).toBeInTheDocument();

    // Switch to Force Local
    const forceLocalBtn = screen.getByText('Force Local');
    fireEvent.click(forceLocalBtn);
    expect(screen.getByText('12 Local')).toBeInTheDocument();
    expect(screen.getByText('0 Cloud')).toBeInTheDocument();

    // Switch back to Adaptive
    const adaptiveBtn = screen.getByText('Adaptive Offload');
    fireEvent.click(adaptiveBtn);
    expect(screen.getByText('4 Local')).toBeInTheDocument();
    expect(screen.getByText('8 Cloud')).toBeInTheDocument();
  });

  it('simulates 12-worker swarm dispatch and fires onBatchDispatched callback', () => {
    const handleBatchDispatched = vi.fn();
    render(
      <HighConcurrencySwarmOffloadCard
        batchId="batch-dispatch-eval-01"
        onBatchDispatched={handleBatchDispatched}
      />
    );

    const dispatchBtn = screen.getByText('Dispatch 12-Worker Swarm');
    fireEvent.click(dispatchBtn);

    expect(handleBatchDispatched).toHaveBeenCalledTimes(1);
    const summary = handleBatchDispatched.mock.calls[0][0];
    expect(summary.batchId).toBe('batch-dispatch-eval-01');
    expect(summary.totalTasks).toBe(12);
    expect(summary.completedCount).toBe(12);
    expect(summary.failedCount).toBe(0);
    expect(summary.localCount).toBe(4);
    expect(summary.cloudCount).toBe(8);
  });
});
