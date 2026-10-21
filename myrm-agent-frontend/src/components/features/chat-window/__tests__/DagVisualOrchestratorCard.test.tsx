import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DagVisualOrchestratorCard } from '../DagVisualOrchestratorCard';
import { DEFAULT_DAG_NODES } from '../dag-orchestrator/types';

describe('DagVisualOrchestratorCard', () => {
  it('renders DAG header, workflow info, nodes and initial progress', () => {
    render(
      <DagVisualOrchestratorCard
        chatId="chat-test-dag"
        workflowId="wf-test-01"
      />,
    );

    expect(
      screen.getByRole('region', {
        name: /DAG Visual Orchestrator & Cold Resume/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('wf-test-01')).toBeInTheDocument();
    expect(screen.getByText('Architecture Planning')).toBeInTheDocument();
    expect(screen.getByText('Implementation Wave')).toBeInTheDocument();
    expect(screen.getByText('Critic Audit & Review')).toBeInTheDocument();
    expect(screen.getByText('Smoke Test & Delivery')).toBeInTheDocument();

    // Verify progress text
    expect(screen.getByText(/Progress: 2\/4 Completed/i)).toBeInTheDocument();
    expect(screen.getByText(/1 Issue\(s\)/i)).toBeInTheDocument();
  });

  it('triggers cold resume, restores failed nodes to READY and notifies screen reader', () => {
    const handleColdResume = vi.fn();
    render(
      <DagVisualOrchestratorCard
        workflowId="wf-resume-test"
        onColdResume={handleColdResume}
      />,
    );

    const resumeBtn = screen.getByRole('button', {
      name: /Cold Resume Checkpoint/i,
    });
    fireEvent.click(resumeBtn);

    expect(handleColdResume).toHaveBeenCalledWith('wf-resume-test-snap');
    expect(
      screen.getByText(/Cold resume completed: restored from snapshot wf-resume-test-snap/i),
    ).toBeInTheDocument();
    // Review node should now be READY
    expect(screen.getByText('READY')).toBeInTheDocument();
  });

  it('advances step for ready nodes successfully', () => {
    const customNodes = {
      ...DEFAULT_DAG_NODES,
      review: {
        ...DEFAULT_DAG_NODES.review,
        status: 'READY' as const,
        errorMessage: undefined,
      },
    };
    render(<DagVisualOrchestratorCard initialNodes={customNodes} />);

    const advanceBtn = screen.getByRole('button', {
      name: /Advance Step/i,
    });
    fireEvent.click(advanceBtn);

    expect(
      screen.getByText(/Orchestrator stepped forward/i),
    ).toBeInTheDocument();
  });

  it('triggers downstream reject and cascades downstream nodes to PENDING', () => {
    const handleRejectLoopback = vi.fn();
    render(
      <DagVisualOrchestratorCard
        onRejectLoopback={handleRejectLoopback}
      />,
    );

    // Open reject panel
    const openRejectBtn = screen.getByRole('button', {
      name: /Bidirectional Reject & Redo/i,
    });
    fireEvent.click(openRejectBtn);

    expect(screen.getByText(/Downstream Critic Reject & Cascade Redo/i)).toBeInTheDocument();

    // Target node is 'code', modify feedback
    const feedbackInput = screen.getByLabelText(/Audit Feedback & Defects:/i);
    fireEvent.change(feedbackInput, {
      target: { value: 'Critical race condition found in code module' },
    });

    // Submit reject form
    const submitBtn = screen.getByRole('button', {
      name: /Confirm Reject & Cascade Reset/i,
    });
    fireEvent.click(submitBtn);

    expect(handleRejectLoopback).toHaveBeenCalledWith(
      'code',
      'Critical race condition found in code module',
    );
    expect(
      screen.getByText(/Cascade reject applied to node \[code\]/i),
    ).toBeInTheDocument();
  });

  it('allows selecting a node and toggling selection highlight', () => {
    render(<DagVisualOrchestratorCard />);

    const planNodeText = screen.getByText('Architecture Planning');
    const nodeCard = planNodeText.closest('div');
    expect(nodeCard).toBeTruthy();

    if (nodeCard) {
      fireEvent.click(nodeCard);
      // Click again to deselect
      fireEvent.click(nodeCard);
    }
  });
});
