import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  TriRolePipelinePanel,
  TriRoleSessionData,
} from '../TriRolePipelinePanel';

describe('TriRolePipelinePanel', () => {
  const sampleAcceptedSession: TriRoleSessionData = {
    session_id: 'sess-tri-test-1',
    task_description: 'Build High-Throughput Message Bus',
    stages: [
      {
        stage_id: 'stage-1',
        stage_name: 'Protocol & Schema',
        status: 'accepted',
        planner_output: 'Defined protobuf message format with idempotency key.',
        criteria: [
          {
            criterion_id: 'crit-proto',
            description: 'Protobuf spec compiles cleanly',
            assertion_rule: 'protoc --check == 0',
            is_satisfied: true,
          },
        ],
        generator_output: 'Generated message_bus.proto and python bindings.',
        produced_files: ['proto/message_bus.proto', 'bus_client.py'],
        evaluation: {
          is_accepted: true,
          score: 1.0,
          evaluator_notes: 'Schema validated against conformance suite.',
          criteria_results: { 'crit-proto': true },
          evaluated_at: '2026-10-15T12:00:00Z',
        },
        manifest: {
          manifest_id: 'manifest-bus-stage-1',
          session_id: 'sess-tri-test-1',
          stage_index: 0,
          produced_files: ['proto/message_bus.proto', 'bus_client.py'],
          passed_assertions: ['Protobuf spec compiles cleanly'],
          key_constraints: ['protoc --check == 0'],
          pending_todos: ['Implement Kafka broker adapter'],
          created_at: '2026-10-15T12:05:00Z',
        },
      },
      {
        stage_id: 'stage-2',
        stage_name: 'Broker Implementation',
        status: 'planned',
        criteria: [],
        produced_files: [],
      },
    ],
    current_stage_index: 0,
    is_completed: false,
    created_at: '2026-10-15T11:50:00Z',
    updated_at: '2026-10-15T12:05:00Z',
  };

  const sampleRejectedSession: TriRoleSessionData = {
    session_id: 'sess-tri-test-2',
    task_description: 'Implement Zero-Trust Token Validator',
    stages: [
      {
        stage_id: 'stage-sec-1',
        stage_name: 'Cryptographic Verification',
        status: 'rejected',
        planner_output: 'Validate Ed25519 signature.',
        criteria: [
          {
            criterion_id: 'crit-sig',
            description: 'Reject forged signatures',
            assertion_rule: 'verify(fake_sig) == False',
            is_satisfied: false,
          },
        ],
        generator_output: 'Fallback to unverified token decode.',
        produced_files: ['token_validator.py'],
        evaluation: {
          is_accepted: false,
          score: 0.0,
          evaluator_notes: 'Adversary test penetrated the validator.',
          criteria_results: { 'crit-sig': false },
          evaluated_at: '2026-10-15T12:10:00Z',
        },
        manifest: null,
      },
    ],
    current_stage_index: 0,
    is_completed: false,
    created_at: '2026-10-15T12:00:00Z',
    updated_at: '2026-10-15T12:10:00Z',
  };

  it('renders session header, stages, and role columns cleanly', () => {
    render(<TriRolePipelinePanel session={sampleAcceptedSession} />);

    expect(screen.getByText('Tri-Role Pipeline Separation')).toBeInTheDocument();
    expect(screen.getByText('Build High-Throughput Message Bus')).toBeInTheDocument();
    expect(screen.getByText(/Stage 1 of 2:/)).toBeInTheDocument();
    expect(screen.getByText('Protocol & Schema')).toBeInTheDocument();

    // Roles
    expect(screen.getByText('1. Planner Criteria')).toBeInTheDocument();
    expect(screen.getByText('2. Generator Deliverables')).toBeInTheDocument();
    expect(screen.getByText('3. Independent Evaluator')).toBeInTheDocument();

    // Deliverables
    expect(screen.getByText('proto/message_bus.proto')).toBeInTheDocument();
    expect(screen.getByText('bus_client.py')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getAllByText('Accepted').length).toBeGreaterThanOrEqual(1);
  });

  it('renders evaluator rejection verdict and missing manifest safely', () => {
    render(<TriRolePipelinePanel session={sampleRejectedSession} />);

    expect(screen.getAllByText('Rejected').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('0%')).toBeInTheDocument();
    expect(screen.getByText('Adversary test penetrated the validator.')).toBeInTheDocument();
    expect(screen.queryByText(/Handoff Manifest:/)).not.toBeInTheDocument();
  });

  it('triggers onAdvanceStage when Advance button clicked on accepted stage', () => {
    const handleAdvance = vi.fn();
    render(
      <TriRolePipelinePanel
        session={sampleAcceptedSession}
        onAdvanceStage={handleAdvance}
      />
    );

    const advanceBtn = screen.getByRole('button', { name: /Advance/i });
    fireEvent.click(advanceBtn);
    expect(handleAdvance).toHaveBeenCalledTimes(1);
  });

  it('triggers onExportManifest when Export Handoff button clicked', () => {
    const handleExport = vi.fn();
    render(
      <TriRolePipelinePanel
        session={sampleAcceptedSession}
        onExportManifest={handleExport}
      />
    );

    const exportBtn = screen.getByRole('button', { name: /Export Handoff/i });
    fireEvent.click(exportBtn);
    expect(handleExport).toHaveBeenCalledTimes(1);
    expect(handleExport).toHaveBeenCalledWith(
      expect.objectContaining({ manifest_id: 'manifest-bus-stage-1' })
    );
  });

  it('collapses and expands panel upon toggle click', () => {
    render(<TriRolePipelinePanel session={sampleAcceptedSession} />);

    expect(screen.getByText('1. Planner Criteria')).toBeInTheDocument();
    const toggleBtn = screen.getByRole('button', { name: /Collapse/i });
    fireEvent.click(toggleBtn);

    // Body content hidden
    expect(screen.queryByText('1. Planner Criteria')).not.toBeInTheDocument();

    const expandBtn = screen.getByRole('button', { name: /Expand/i });
    fireEvent.click(expandBtn);
    expect(screen.getByText('1. Planner Criteria')).toBeInTheDocument();
  });

  it('triggers onClose when close button clicked', () => {
    const handleClose = vi.fn();
    render(
      <TriRolePipelinePanel
        session={sampleAcceptedSession}
        onClose={handleClose}
      />
    );

    const closeBtn = screen.getByRole('button', { name: /Close panel/i });
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
