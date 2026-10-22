import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  PipelineIntegrityDoctorCard,
  PipelineDefinitionData,
} from '../PipelineIntegrityDoctorCard';

describe('PipelineIntegrityDoctorCard', () => {
  it('renders initial compliant state and handles dismiss', () => {
    const handleDismiss = vi.fn();
    render(
      <PipelineIntegrityDoctorCard
        chatId="test-healthy-01"
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByTestId('pipeline-integrity-doctor-card')).toBeInTheDocument();
    expect(screen.getByTestId('stat-total-steps')).toHaveTextContent('4');
    expect(screen.getByTestId('stat-detected-gaps')).toHaveTextContent('0');
    expect(screen.getByTestId('stat-health-status')).toHaveTextContent('HEALTHY');
    expect(screen.getByTestId('empty-gaps')).toBeInTheDocument();

    const dismissBtn = screen.getByRole('button', { name: /Dismiss dialog/i });
    fireEvent.click(dismissBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('renders custom initial pipeline correctly', () => {
    const customPipeline: PipelineDefinitionData = {
      pipeline_id: 'custom-pipe-01',
      name: 'Custom Two-Step Pipeline',
      steps: [
        {
          step_id: 'step-a',
          stage: 'analysis',
          agent_role: 'analyst',
          requires_approval: false,
          requires_verification: false,
          produced_artifacts: [],
        },
        {
          step_id: 'step-b',
          stage: 'execution',
          agent_role: 'coder',
          requires_approval: false,
          requires_verification: true,
          produced_artifacts: [],
          metadata: {
            source_agent: 'analyst',
            target_agent: 'coder',
            transfer_reason: 'Execute based on spec',
          },
        },
      ],
      version: '1.2.0',
    };

    render(
      <PipelineIntegrityDoctorCard
        chatId="test-custom-02"
        initialPipeline={customPipeline}
      />
    );

    expect(screen.getByTestId('stat-total-steps')).toHaveTextContent('2');
    expect(screen.getByTestId('stat-detected-gaps')).toHaveTextContent('0');
    expect(screen.getByTestId('chain-link-step-a')).toBeInTheDocument();
    expect(screen.getByTestId('chain-link-step-b')).toBeInTheDocument();
  });

  it('loads gapped sample and flags metadata, approval and artifact gaps', () => {
    render(<PipelineIntegrityDoctorCard chatId="test-gapped-03" />);

    expect(screen.getByTestId('stat-detected-gaps')).toHaveTextContent('0');

    // Load sample flawed pipeline
    fireEvent.click(screen.getByTestId('btn-load-gapped'));

    expect(screen.getByTestId('stat-detected-gaps')).not.toHaveTextContent('0');
    expect(screen.getByTestId('stat-health-status')).toHaveTextContent('CRITICAL ISSUES');
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Loaded sample flawed pipeline with multiple integrity gaps.'
    );

    expect(screen.getByTestId('gap-item-RULE-001-HANDOFF-METADATA')).toBeInTheDocument();
    expect(screen.getByTestId('gap-item-RULE-002-APPROVAL-GATE')).toBeInTheDocument();
    expect(screen.getByTestId('gap-item-RULE-003-PUBLISH-ARTIFACT')).toBeInTheDocument();
  });

  it('executes manual integrity lint and reports diagnostic status', () => {
    render(<PipelineIntegrityDoctorCard chatId="test-lint-04" />);

    fireEvent.click(screen.getByTestId('btn-run-lint'));

    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Lint complete: 0 gaps detected across 4 steps.'
    );
  });

  it('auto-heals flawed pipeline, remediating all error gaps back to healthy', () => {
    render(<PipelineIntegrityDoctorCard chatId="test-heal-05" />);

    // Load gapped sample first
    fireEvent.click(screen.getByTestId('btn-load-gapped'));
    expect(screen.getByTestId('stat-health-status')).toHaveTextContent('CRITICAL ISSUES');

    // Trigger auto-heal
    fireEvent.click(screen.getByTestId('btn-auto-heal'));

    expect(screen.getByTestId('stat-health-status')).toHaveTextContent('HEALTHY');
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Auto-healed pipeline: all blocking error gaps remediated!'
    );
    // Error gap items are eliminated
    expect(screen.queryByTestId('gap-item-RULE-002-APPROVAL-GATE')).not.toBeInTheDocument();
    expect(screen.queryByTestId('gap-item-RULE-003-PUBLISH-ARTIFACT')).not.toBeInTheDocument();
  });

  it('resets pipeline back to standard compliant baseline', () => {
    render(<PipelineIntegrityDoctorCard chatId="test-reset-06" />);

    // Load gapped
    fireEvent.click(screen.getByTestId('btn-load-gapped'));
    expect(screen.getByTestId('stat-total-steps')).toHaveTextContent('3');

    // Reset
    fireEvent.click(screen.getByTestId('btn-reset'));
    expect(screen.getByTestId('stat-total-steps')).toHaveTextContent('4');
    expect(screen.getByTestId('stat-detected-gaps')).toHaveTextContent('0');
    expect(screen.getByTestId('stat-health-status')).toHaveTextContent('HEALTHY');
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Reset to standard compliant pipeline.'
    );
  });
});
