import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { VisualKanbanWorkflowDispatcherCard } from '../VisualKanbanWorkflowDispatcherCard';

describe('VisualKanbanWorkflowDispatcherCard', () => {
  it('renders header with metrics, 5 swimlanes, and demo cards', () => {
    const handleDismiss = vi.fn();
    render(
      <VisualKanbanWorkflowDispatcherCard
        chatId="chat-test-kanban"
        onDismiss={handleDismiss}
      />,
    );

    expect(
      screen.getByRole('region', {
        name: /Visual Kanban Multi-Agent Workflow Dispatcher and Card Handoff/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('Session: chat-test-kanban')).toBeInTheDocument();
    expect(screen.getByText(/Visual Kanban Dispatcher/i)).toBeInTheDocument();

    // Verify 5 swimlanes
    expect(screen.getByText('Backlog')).toBeInTheDocument();
    expect(screen.getByText('Researching')).toBeInTheDocument();
    expect(screen.getByText('Developing')).toBeInTheDocument();
    expect(screen.getByText('Reviewing')).toBeInTheDocument();
    expect(screen.getByText('Done')).toBeInTheDocument();

    // Verify default agents
    expect(screen.getByText('product_manager')).toBeInTheDocument();
    expect(screen.getByText('research_specialist')).toBeInTheDocument();
    expect(screen.getByText('dev_coder')).toBeInTheDocument();
    expect(screen.getByText('reviewer_critic')).toBeInTheDocument();
    expect(screen.getByText('qa_release_bot')).toBeInTheDocument();

    // Verify initial cards
    expect(
      screen.getByText('Analyze Vector Index Latency Bottleneck'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Implement Rust SIMD Vector Normalization'),
    ).toBeInTheDocument();

    // Dismiss button
    const closeBtn = screen.getByLabelText('Dismiss Kanban Board');
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('triggers card handoff to advance to next swimlane and reassign agent', () => {
    const handleHandoff = vi.fn();
    render(
      <VisualKanbanWorkflowDispatcherCard onCardHandoff={handleHandoff} />,
    );

    // Find card-101 (in Researching lane) handoff button
    const handoffBtns = screen.getAllByRole('button', { name: /Handoff →/i });
    expect(handoffBtns.length).toBeGreaterThan(0);

    // Click handoff on card-101
    fireEvent.click(handoffBtns[0]);
    expect(handleHandoff).toHaveBeenCalledWith(
      'card-101',
      'developing',
      'dev_coder',
    );
  });

  it('toggles block and unblock state on a card', () => {
    const handleToggleBlock = vi.fn();
    render(
      <VisualKanbanWorkflowDispatcherCard onCardToggleBlock={handleToggleBlock} />,
    );

    // Card 101 is initially unblocked -> button is "Block"
    const blockBtns = screen.getAllByRole('button', { name: 'Block' });
    fireEvent.click(blockBtns[0]);
    expect(handleToggleBlock).toHaveBeenCalledWith(
      'card-101',
      true,
      expect.stringContaining('Blocked by dependency'),
    );

    // Card 101 was just blocked, Card 102 was initially blocked -> both have "Unblock"
    const unblockBtns = screen.getAllByRole('button', { name: 'Unblock' });
    expect(unblockBtns.length).toBe(2);
    fireEvent.click(unblockBtns[1]);
    expect(handleToggleBlock).toHaveBeenCalledWith(
      'card-102',
      false,
      undefined,
    );
  });

  it('creates a new card and dispatches it to Backlog lane', () => {
    const handleCreated = vi.fn();
    render(
      <VisualKanbanWorkflowDispatcherCard onCardCreated={handleCreated} />,
    );

    // Open add card form
    const addBtn = screen.getByRole('button', { name: /\+ New Card/i });
    fireEvent.click(addBtn);

    const titleInput = screen.getByLabelText('Task Title');
    const descInput = screen.getByLabelText('Description');
    const tagsInput = screen.getByLabelText('Tags (comma separated)');

    fireEvent.change(titleInput, {
      target: { value: 'Distributed Cache Invalidation Protocol' },
    });
    fireEvent.change(descInput, {
      target: { value: 'Implement Raft-backed Lease synchronization.' },
    });
    fireEvent.change(tagsInput, {
      target: { value: 'cache, raft, high-perf' },
    });

    const submitBtn = screen.getByRole('button', {
      name: /Dispatch to Backlog/i,
    });
    fireEvent.click(submitBtn);

    expect(handleCreated).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Distributed Cache Invalidation Protocol',
        swimlane: 'backlog',
        assignedAgentId: 'product_manager',
      }),
    );
    expect(
      screen.getByText('Distributed Cache Invalidation Protocol'),
    ).toBeInTheDocument();
  });

  it('expands and collapses handoff history log', () => {
    render(<VisualKanbanWorkflowDispatcherCard />);

    // Click "Log" button on first card
    const logBtns = screen.getAllByRole('button', { name: 'Log' });
    fireEvent.click(logBtns[0]);

    expect(screen.getByText(/Handoff History/i)).toBeInTheDocument();

    // Click "Hide" button to close
    const hideBtn = screen.getByRole('button', { name: 'Hide' });
    fireEvent.click(hideBtn);

    expect(screen.queryByText(/Handoff History/i)).not.toBeInTheDocument();
  });
});
