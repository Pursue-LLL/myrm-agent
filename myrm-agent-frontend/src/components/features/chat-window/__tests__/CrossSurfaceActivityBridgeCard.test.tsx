import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  CrossSurfaceActivityBridgeCard,
  CrossSurfaceProjectionSnapshotData,
} from '../CrossSurfaceActivityBridgeCard';

describe('CrossSurfaceActivityBridgeCard', () => {
  it('renders card with initial zero state and handles dismiss', () => {
    const handleDismiss = vi.fn();
    render(
      <CrossSurfaceActivityBridgeCard
        chatId="test-chat-01"
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByRole('dialog', { name: /Cross-Surface Agent Activity Bridge/i })).toBeInTheDocument();
    expect(screen.getByTestId('total-ingressed-count')).toHaveTextContent('0');
    expect(screen.getByTestId('active-presences-count')).toHaveTextContent('0');

    const dismissBtn = screen.getByRole('button', { name: /Dismiss dialog/i });
    fireEvent.click(dismissBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('renders custom snapshot with presence and activity waterfall accurately', () => {
    const customSnapshot: CrossSurfaceProjectionSnapshotData = {
      chat_id: 'test-chat-02',
      total_ingressed_activities: 12,
      active_presences: [
        {
          session_key: 'tauri-session-test',
          source_surface: 'tauri_desktop',
          agent_id: 'desktop-agent-1',
          status: 'active',
          last_active_at: '2026-08-22T10:00:00Z',
          recent_activities_count: 5,
        },
        {
          session_key: 'cli-session-test',
          source_surface: 'cli_tool',
          agent_id: 'cli-worker-1',
          status: 'idle',
          last_active_at: '2026-08-22T09:50:00Z',
          recent_activities_count: 7,
        },
      ],
      bounded_recent_activities: [
        {
          activity_id: 'act-sample-1',
          session_key: 'tauri-session-test',
          source_surface: 'tauri_desktop',
          agent_id: 'desktop-agent-1',
          activity_kind: 'tool_call',
          preview_text: 'Reading config/env.json',
          timestamp: '2026-08-22T10:00:00Z',
        },
      ],
      last_ingressed_at: '2026-08-22T10:00:00Z',
    };

    render(
      <CrossSurfaceActivityBridgeCard
        chatId="test-chat-02"
        initialSnapshot={customSnapshot}
      />
    );

    expect(screen.getByTestId('total-ingressed-count')).toHaveTextContent('12');
    expect(screen.getByTestId('active-presences-count')).toHaveTextContent('2');
    expect(screen.getByText('tauri-session-test')).toBeInTheDocument();
    expect(screen.getByText('cli-session-test')).toBeInTheDocument();
    expect(screen.getByText('Reading config/env.json')).toBeInTheDocument();
  });

  it('ingresses Tauri event and updates presence and waterfall', async () => {
    render(<CrossSurfaceActivityBridgeCard chatId="test-chat-03" />);

    const tauriBtn = screen.getByRole('button', { name: /Ingress Tauri/i });
    fireEvent.click(tauriBtn);

    await waitFor(() => {
      expect(screen.getByTestId('total-ingressed-count')).toHaveTextContent('1');
      expect(screen.getByTestId('active-presences-count')).toHaveTextContent('1');
      expect(screen.getByText(/Tauri indexed local rust\/workspace tree/i)).toBeInTheDocument();
    });
  });

  it('ingresses CLI event and renders thinking_pulse activity', async () => {
    render(<CrossSurfaceActivityBridgeCard chatId="test-chat-04" />);

    const cliBtn = screen.getByRole('button', { name: /Ingress CLI/i });
    fireEvent.click(cliBtn);

    await waitFor(() => {
      expect(screen.getByTestId('total-ingressed-count')).toHaveTextContent('1');
      expect(screen.getByText(/Running git status and analyzing unstaged diffs/i)).toBeInTheDocument();
    });
  });

  it('resets bridge ledger when reset button is clicked', async () => {
    const customSnapshot: CrossSurfaceProjectionSnapshotData = {
      chat_id: 'test-chat-05',
      total_ingressed_activities: 8,
      active_presences: [
        {
          session_key: 'cron-session-test',
          source_surface: 'cron_job',
          agent_id: 'cron-agent-1',
          status: 'completed',
          last_active_at: '2026-08-22T10:00:00Z',
          recent_activities_count: 8,
        },
      ],
      bounded_recent_activities: [],
      last_ingressed_at: '2026-08-22T10:00:00Z',
    };

    render(
      <CrossSurfaceActivityBridgeCard
        chatId="test-chat-05"
        initialSnapshot={customSnapshot}
      />
    );

    expect(screen.getByTestId('total-ingressed-count')).toHaveTextContent('8');

    const resetBtn = screen.getByRole('button', { name: /Reset bridge/i });
    fireEvent.click(resetBtn);

    await waitFor(() => {
      expect(screen.getByTestId('total-ingressed-count')).toHaveTextContent('0');
      expect(screen.getByTestId('active-presences-count')).toHaveTextContent('0');
      expect(screen.getByText(/Activity bridge ledger reset/i)).toBeInTheDocument();
    });
  });
});
