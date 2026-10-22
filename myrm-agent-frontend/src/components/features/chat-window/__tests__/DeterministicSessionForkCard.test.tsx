import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  DeterministicSessionForkCard,
  ChildSessionLinkData,
} from '../DeterministicSessionForkCard';

describe('DeterministicSessionForkCard', () => {
  it('renders initial empty directory state and handles dismiss', () => {
    const handleDismiss = vi.fn();
    render(
      <DeterministicSessionForkCard
        chatId="test-parent-01"
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByTestId('deterministic-session-fork-card')).toBeInTheDocument();
    expect(screen.getByTestId('stat-total-children')).toHaveTextContent('0');
    expect(screen.getByTestId('stat-total-replays')).toHaveTextContent('0');
    expect(screen.getByTestId('stat-prevented-twins')).toHaveTextContent('0');
    expect(screen.getByTestId('empty-directory')).toBeInTheDocument();

    const dismissBtn = screen.getByRole('button', { name: /Dismiss dialog/i });
    fireEvent.click(dismissBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('renders custom initial children accurately', () => {
    const customChildren: ChildSessionLinkData[] = [
      {
        child_session_id: 'child-alpha-123',
        parent_session_id: 'test-parent-02',
        tool_call_id: 'call-first-01',
        fork_scope: 'branch',
        created_at: 1000,
        reattach_count: 2,
        last_attached_at: 1020,
      },
      {
        child_session_id: 'child-beta-456',
        parent_session_id: 'test-parent-02',
        tool_call_id: 'call-second-02',
        fork_scope: 'tree',
        created_at: 1010,
        reattach_count: 0,
        last_attached_at: 1010,
      },
    ];

    render(
      <DeterministicSessionForkCard
        chatId="test-parent-02"
        initialChildren={customChildren}
      />
    );

    expect(screen.getByTestId('stat-total-children')).toHaveTextContent('2');
    expect(screen.getByTestId('stat-total-replays')).toHaveTextContent('2');
    expect(screen.getByTestId('stat-prevented-twins')).toHaveTextContent('2');
    expect(screen.getByTestId('child-item-child-alpha-123')).toBeInTheDocument();
    expect(screen.getByTestId('child-item-child-beta-456')).toBeInTheDocument();
  });

  it('handles forking new child session with branch and tree scopes', () => {
    render(<DeterministicSessionForkCard chatId="test-parent-03" />);

    expect(screen.getByTestId('stat-total-children')).toHaveTextContent('0');

    // Fork branch scope
    fireEvent.click(screen.getByTestId('btn-fork-branch'));
    expect(screen.getByTestId('stat-total-children')).toHaveTextContent('1');
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      "with scope 'branch' (idle initial state)."
    );

    // Fork tree scope
    fireEvent.click(screen.getByTestId('btn-fork-tree'));
    expect(screen.getByTestId('stat-total-children')).toHaveTextContent('2');
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      "with scope 'tree' (idle initial state)."
    );
  });

  it('handles safe replay reattach and increments replay count to prevent twins', () => {
    render(<DeterministicSessionForkCard chatId="test-parent-04" />);

    // First fork a child
    fireEvent.click(screen.getByTestId('btn-fork-branch'));
    expect(screen.getByTestId('stat-total-children')).toHaveTextContent('1');
    expect(screen.getByTestId('stat-total-replays')).toHaveTextContent('0');

    // Simulate safe replay of identical tool call
    fireEvent.click(screen.getByTestId('btn-safe-replay'));

    expect(screen.getByTestId('stat-total-children')).toHaveTextContent('1'); // Children count does not double!
    expect(screen.getByTestId('stat-total-replays')).toHaveTextContent('1');
    expect(screen.getByTestId('stat-prevented-twins')).toHaveTextContent('1');
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Safe Tool Replay: Reattached to'
    );
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Twin child session prevented!'
    );
  });

  it('handles reset action', () => {
    render(<DeterministicSessionForkCard chatId="test-parent-05" />);

    // Create child
    fireEvent.click(screen.getByTestId('btn-fork-branch'));
    expect(screen.getByTestId('stat-total-children')).toHaveTextContent('1');

    // Reset
    fireEvent.click(screen.getByTestId('btn-reset'));
    expect(screen.getByTestId('stat-total-children')).toHaveTextContent('0');
    expect(screen.getByTestId('stat-total-replays')).toHaveTextContent('0');
    expect(screen.getByTestId('empty-directory')).toBeInTheDocument();
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Deterministic session fork repository reset.'
    );
  });
});
