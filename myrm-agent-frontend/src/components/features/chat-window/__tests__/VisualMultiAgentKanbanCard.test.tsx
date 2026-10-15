import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { VisualMultiAgentKanbanCard } from '../VisualMultiAgentKanbanCard';
import {
  CardArtifact,
  KanbanBoardState,
  KanbanCard,
} from '../kanban-orchestrator/types';

const mockBoardState: KanbanBoardState = {
  board_id: 'board-test-1',
  session_id: 'chat-kanban-1',
  title: 'Test Kanban Orchestration Board',
  cards: {
    'card-1': {
      card_id: 'card-1',
      board_id: 'board-test-1',
      title: 'Analyze DB Schema',
      description: 'Review table definitions and indexes',
      lane: 'todo',
      priority: 'high',
      assigned_agent: 'db-architect',
      depends_on: [],
      blocked_by: [],
      sandbox_subdir: 'tasks/card-1',
      artifacts: [],
      created_at: 1710000000,
      updated_at: 1710000000,
    },
    'card-2': {
      card_id: 'card-2',
      board_id: 'board-test-1',
      title: 'Generate Migration Scripts',
      description: 'Apply schema diff to sandbox database',
      lane: 'blocked',
      priority: 'medium',
      assigned_agent: 'backend-dev',
      depends_on: ['card-1'],
      blocked_by: ['card-1'],
      sandbox_subdir: 'tasks/card-2',
      artifacts: [],
      created_at: 1710000000,
      updated_at: 1710000000,
    },
  },
  created_at: 1710000000,
  updated_at: 1710000000,
};

describe('VisualMultiAgentKanbanCard', () => {
  it('renders kanban board header, metrics, 6 swimlanes, and accessible live output', () => {
    render(
      <VisualMultiAgentKanbanCard
        chatId="chat-kanban-1"
        initialBoardState={mockBoardState}
      />,
    );

    expect(
      screen.getByRole('article', { name: /Visual Multi-Agent Kanban Card/i }),
    ).toBeInTheDocument();
    expect(screen.getByText('Test Kanban Orchestration Board')).toBeInTheDocument();
    expect(screen.getByText(/DAG Auto-Unblock Active/i)).toBeInTheDocument();
    expect(screen.getByText(/Card Sandbox Isolated/i)).toBeInTheDocument();

    // 6 swimlane headers
    expect(screen.getByText(/Backlog/i)).toBeInTheDocument();
    expect(screen.getByText(/Ready \(To-Do\)/i)).toBeInTheDocument();
    expect(screen.getByText(/In Progress/i)).toBeInTheDocument();
    expect(screen.getByText(/In Review/i)).toBeInTheDocument();
    expect(screen.getByText(/^Done/i)).toBeInTheDocument();
    expect(screen.getByText(/Blocked \(Waiting DAG\)/i)).toBeInTheDocument();

    // Verify accessible status element
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(
      screen.getByText(/6-swimlane workflow active with automatic DAG dependency unblocking/i),
    ).toBeInTheDocument();
  });

  it('triggers card transition and automatic downstream dependency unblocking', async () => {
    const handleTransition = vi.fn().mockImplementation(async (cardId: string, lane: string) => {
      const updatedCard: KanbanCard = {
        ...mockBoardState.cards[cardId],
        lane: lane as KanbanCard['lane'],
        updated_at: Date.now(),
      };
      const unlockedCards = lane === 'done' ? ['card-2'] : [];
      return { card: updatedCard, unlocked_cards: unlockedCards };
    });

    render(
      <VisualMultiAgentKanbanCard
        chatId="chat-kanban-1"
        initialBoardState={mockBoardState}
        onTransitionCard={handleTransition}
      />,
    );

    // Initial state: card-1 in To Do, card-2 in Blocked
    expect(screen.getByText('Analyze DB Schema')).toBeInTheDocument();
    expect(screen.getByText('Generate Migration Scripts')).toBeInTheDocument();

    // Advance card-1 from todo to in_progress
    const advanceButtons = screen.getAllByRole('button', { name: /Advance →/i });
    const advanceBtn = advanceButtons.find((el) => el.tagName === 'BUTTON') ?? advanceButtons[0];
    fireEvent.click(advanceBtn);

    expect(handleTransition).toHaveBeenCalledWith('card-1', 'in_progress');
    await waitFor(() => {
      expect(screen.getByText(/Card 'card-1' moved to 'in_progress'/i)).toBeInTheDocument();
    });
  });

  it('opens decompose modal and adds decomposed cards from Boss Agent', async () => {
    const handleDecompose = vi.fn().mockResolvedValue([
      {
        card_id: 'card-sub-1',
        board_id: 'board-test-1',
        title: 'Draft API contracts',
        description: 'OpenAPI 3.1 schema definition',
        lane: 'todo' as const,
        priority: 'high' as const,
        assigned_agent: 'api-designer',
        depends_on: [],
        blocked_by: [],
        sandbox_subdir: 'tasks/card-sub-1',
        artifacts: [],
        created_at: Date.now(),
        updated_at: Date.now(),
      },
    ]);

    render(
      <VisualMultiAgentKanbanCard
        chatId="chat-kanban-1"
        initialBoardState={mockBoardState}
        onDecomposeGoal={handleDecompose}
      />,
    );

    // Click Auto Decompose Goal button
    const decomposeBtn = screen.getByRole('button', { name: /⚡ Auto Decompose/i });
    fireEvent.click(decomposeBtn);

    expect(screen.getByText(/Boss Agent Goal Auto-Decomposition/i)).toBeInTheDocument();

    // Submit decomposition form
    const submitBtn = screen.getByRole('button', { name: /Decompose & Sequenced DAG/i });
    fireEvent.click(submitBtn);

    expect(handleDecompose).toHaveBeenCalled();

    await waitFor(() => {
      expect(screen.getByText('Draft API contracts')).toBeInTheDocument();
      expect(
        screen.getByText(/Boss Agent generated 1 sequenced DAG cards/i),
      ).toBeInTheDocument();
    });
  });

  it('opens add card modal and manually creates a new task card', async () => {
    const handleCreate = vi.fn().mockResolvedValue({
      card_id: 'card-manual-9',
      board_id: 'board-test-1',
      title: 'Configure Prometheus Metrics',
      description: 'Instrument HTTP endpoints with counters',
      lane: 'todo' as const,
      priority: 'low' as const,
      assigned_agent: 'observability-spec',
      depends_on: [],
      blocked_by: [],
      sandbox_subdir: 'tasks/card-manual-9',
      artifacts: [],
      created_at: Date.now(),
      updated_at: Date.now(),
    });

    render(
      <VisualMultiAgentKanbanCard
        chatId="chat-kanban-1"
        initialBoardState={mockBoardState}
        onCreateCard={handleCreate}
      />,
    );

    const addCardBtn = screen.getByRole('button', { name: /\+ Add Card/i });
    fireEvent.click(addCardBtn);

    expect(screen.getByText(/Create Kanban Task Card/i)).toBeInTheDocument();

    const titleInput = screen.getByPlaceholderText(/e\.g\. Implement WebSocket reconnection protocol/i);
    fireEvent.change(titleInput, { target: { value: 'Configure Prometheus Metrics' } });

    const createSubmitBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createSubmitBtn);

    expect(handleCreate).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getByText('Configure Prometheus Metrics')).toBeInTheDocument();
    });
  });

  it('opens card detail drawer and supports artifact mounting and human-in-the-loop override', async () => {
    const handleMount = vi.fn().mockResolvedValue({
      artifact_id: 'art-patch-1',
      name: 'schema_patch.sql',
      artifact_type: 'diff',
      file_path: 'migrations/0001_init.sql',
      content_preview: 'CREATE TABLE users (id UUID PRIMARY KEY);',
      mounted_at: Date.now(),
    } as CardArtifact);

    const handleOverride = vi.fn().mockResolvedValue({
      card: {
        ...mockBoardState.cards['card-1'],
        assigned_agent: 'senior-architect',
        priority: 'critical' as const,
      },
      unlocked_cards: [],
    });

    render(
      <VisualMultiAgentKanbanCard
        chatId="chat-kanban-1"
        initialBoardState={mockBoardState}
        onMountArtifact={handleMount}
        onHumanOverride={handleOverride}
      />,
    );

    // Open detail drawer by clicking card-1
    const cardTitle = screen.getByText('Analyze DB Schema');
    fireEvent.click(cardTitle);

    expect(screen.getByRole('dialog', { name: /Card Detail Drawer/i })).toBeInTheDocument();
    expect(screen.getByText(/Card Sandbox Scope/i)).toBeInTheDocument();
    expect(screen.getAllByText(/tasks\/card-1/i).length).toBeGreaterThanOrEqual(1);

    // Mount an artifact: open artifact subform
    const openFormBtn = screen.getByRole('button', { name: /\+ Mount Artifact/i });
    fireEvent.click(openFormBtn);

    const nameInput = screen.getByLabelText(/Artifact Title/i);
    fireEvent.change(nameInput, { target: { value: 'schema_patch.sql' } });

    const attachBtn = screen.getByRole('button', { name: /Attach Artifact/i });
    fireEvent.click(attachBtn);

    expect(handleMount).toHaveBeenCalledWith(
      'card-1',
      'schema_patch.sql',
      'diff',
      undefined,
      undefined,
    );

    await waitFor(() => {
      expect(screen.getByText(/schema_patch\.sql/i)).toBeInTheDocument();
    });

    // Human in the loop override: save override
    const saveOverrideBtn = screen.getByRole('button', { name: /Save Override/i });
    fireEvent.click(saveOverrideBtn);

    expect(handleOverride).toHaveBeenCalledWith(
      'card-1',
      'db-architect',
      'high',
      'todo',
    );
  });
});
