import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { VerticalPresetsAndSandboxCard } from '../VerticalPresetsAndSandboxCard';

describe('VerticalPresetsAndSandboxCard', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders header, session id, presets list, and initial active role details', () => {
    const handleDismiss = vi.fn();
    render(
      <VerticalPresetsAndSandboxCard
        sessionId="sess-test-presets"
        onDismiss={handleDismiss}
      />
    );

    expect(
      screen.getByRole('region', {
        name: /Five Vertical Role Persona Presets & Sub-Bot Sandbox Tester/i,
      })
    ).toBeInTheDocument();
    expect(screen.getByText('Vertical Role Presets & Sub-Bot Sandbox')).toBeInTheDocument();
    expect(screen.getByText('Session: sess-test-presets')).toBeInTheDocument();

    // Verify initial role buttons rendered
    expect(screen.getByRole('button', { name: /Life Admin Specialist/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Office Manager Bot/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Knowledge Clipper & Distiller/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Chief of Staff Orchestrator/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /B2B Sales Development Rep/i })).toBeInTheDocument();

    // Verify active preset details
    expect(screen.getByText(/Role Config: Life Admin Specialist/i)).toBeInTheDocument();
    expect(screen.getByText(/google_calendar/i)).toBeInTheDocument();

    // Test dismiss
    const closeBtn = screen.getByLabelText('Close vertical presets card');
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('filters presets by category selector and selects a preset to view details', () => {
    render(<VerticalPresetsAndSandboxCard />);

    const select = screen.getByLabelText('Filter by Category:');
    fireEvent.change(select, { target: { value: 'clipper' } });

    expect(screen.getByRole('button', { name: /Knowledge Clipper & Distiller/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Office Manager Bot/i })).not.toBeInTheDocument();

    // Select clipper preset
    fireEvent.click(screen.getByRole('button', { name: /Knowledge Clipper & Distiller/i }));
    expect(screen.getByText(/Role Config: Knowledge Clipper & Distiller/i)).toBeInTheDocument();
    expect(screen.getByText(/tavily_search/i)).toBeInTheDocument();
  });

  it('runs sub-bot isolated sandbox test and captures telemetry', () => {
    const handleTestRun = vi.fn();
    render(<VerticalPresetsAndSandboxCard onRunSandboxTest={handleTestRun} />);

    const promptInput = screen.getByLabelText('Test Prompt:');
    fireEvent.change(promptInput, { target: { value: 'Audit employee travel expenses' } });

    const runBtn = screen.getByRole('button', { name: 'Run Sandbox Test' });
    fireEvent.click(runBtn);

    expect(screen.getByRole('button', { name: 'Running Test...' })).toBeDisabled();

    // Advance timers for setTimeout in handleRunSandbox
    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(screen.getByText(/TEST PASSED/i)).toBeInTheDocument();
    expect(screen.getByText(/Sandbox Telemetry/i)).toBeInTheDocument();
    expect(handleTestRun).toHaveBeenCalledTimes(1);
  });

  it('simulates agent communication loop and displays deadlock alert', () => {
    render(<VerticalPresetsAndSandboxCard />);

    expect(screen.getByText(/Chain Normal/i)).toBeInTheDocument();

    const loopBtn = screen.getByRole('button', { name: 'Simulate Agent Loop' });
    fireEvent.click(loopBtn);

    expect(screen.getByText(/Loop \/ Deadlock Detected/i)).toBeInTheDocument();
  });
});
