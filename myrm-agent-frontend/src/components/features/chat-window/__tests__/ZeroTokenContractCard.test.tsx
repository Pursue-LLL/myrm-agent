import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  ZeroTokenContractCard,
  ZeroTokenAuditSnapshot,
} from '../ZeroTokenContractCard';

describe('ZeroTokenContractCard', () => {
  it('renders card with zero tokens spent guarantee and handles dismiss', () => {
    const handleDismiss = vi.fn();
    render(
      <ZeroTokenContractCard
        chatId="test-chat-01"
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByRole('dialog', { name: /Zero-Token Visualization Contract/i })).toBeInTheDocument();
    expect(screen.getByText(/UI Tokens Spent/i)).toBeInTheDocument();
    expect(screen.getByTestId('ui-tokens-spent')).toHaveTextContent('0');
    expect(screen.getByText(/Zero LLM tokens used for rendering/i)).toBeInTheDocument();

    const dismissBtn = screen.getByRole('button', { name: /Dismiss/i });
    fireEvent.click(dismissBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('renders initial custom snapshot accurately', () => {
    const customSnapshot: ZeroTokenAuditSnapshot = {
      chat_id: 'test-chat-02',
      total_events_mirrored: 42,
      total_tokens_spent: 0,
      saved_tokens_estimated: 6300,
      violations_intercepted: 2,
      is_compliant: false,
      recent_violations: [
        {
          caller_surface: 'fleet_canvas',
          prompt_chars: 50,
          is_violation: true,
          intercepted_reason: 'Blocked by Doctor',
          timestamp: '2026-08-22T10:00:00Z',
        },
      ],
      last_mirrored_at: '2026-08-22T09:59:00Z',
    };

    render(
      <ZeroTokenContractCard
        chatId="test-chat-02"
        initialSnapshot={customSnapshot}
      />
    );

    expect(screen.getByTestId('mirrored-events-count')).toHaveTextContent('42');
    expect(screen.getByTestId('tokens-saved-estimated')).toHaveTextContent('~6,300');
    expect(screen.getByTestId('doctor-violations-count')).toHaveTextContent('2');
    expect(screen.getByText(/Breach Caught/i)).toBeInTheDocument();
    expect(screen.getByText(/Doctor Intercepted Violations/i)).toBeInTheDocument();
    expect(screen.getByText(/Blocked by Doctor/i)).toBeInTheDocument();
  });

  it('increments mirrored events when Mirror Event button is clicked', async () => {
    render(<ZeroTokenContractCard chatId="test-chat-03" />);

    const mirrorBtn = screen.getByRole('button', { name: /Mirror Event/i });
    fireEvent.click(mirrorBtn);

    await waitFor(() => {
      expect(screen.getByTestId('mirrored-events-count')).toHaveTextContent('1');
      expect(screen.getByTestId('tokens-saved-estimated')).toHaveTextContent('~150');
    });

    // Zero tokens spent must remain strictly 0
    expect(screen.getByTestId('ui-tokens-spent')).toHaveTextContent('0');
  });

  it('triggers Doctor breach test and catches violation with warning list', async () => {
    render(<ZeroTokenContractCard chatId="test-chat-04" />);

    expect(screen.getByText(/Compliant/i)).toBeInTheDocument();

    const breachBtn = screen.getByRole('button', { name: /Test Doctor Breach/i });
    fireEvent.click(breachBtn);

    await waitFor(() => {
      expect(screen.getByText(/Breach Caught/i)).toBeInTheDocument();
      expect(screen.getByText(/Doctor intercepted unauthorized LLM call/i)).toBeInTheDocument();
      expect(screen.getByText(/Doctor Intercepted Violations/i)).toBeInTheDocument();
      expect(screen.getByTestId('doctor-violations-count')).toHaveTextContent('1');
    });
  });

  it('resets audit ledger when reset button is clicked', async () => {
    const customSnapshot: ZeroTokenAuditSnapshot = {
      chat_id: 'test-chat-05',
      total_events_mirrored: 10,
      total_tokens_spent: 0,
      saved_tokens_estimated: 1500,
      violations_intercepted: 3,
      is_compliant: false,
      recent_violations: [
        {
          caller_surface: '3d_office',
          prompt_chars: 30,
          is_violation: true,
          intercepted_reason: 'Breach intercepted',
          timestamp: '2026-08-22T10:00:00Z',
        },
      ],
      last_mirrored_at: '2026-08-22T10:00:00Z',
    };

    render(
      <ZeroTokenContractCard
        chatId="test-chat-05"
        initialSnapshot={customSnapshot}
      />
    );

    expect(screen.getByTestId('mirrored-events-count')).toHaveTextContent('10');
    expect(screen.getByTestId('doctor-violations-count')).toHaveTextContent('3');

    const resetBtn = screen.getByRole('button', { name: /Reset audit/i });
    fireEvent.click(resetBtn);

    await waitFor(() => {
      expect(screen.getByText(/Audit ledger reset/i)).toBeInTheDocument();
      expect(screen.getByText(/Compliant/i)).toBeInTheDocument();
      expect(screen.getByTestId('mirrored-events-count')).toHaveTextContent('0');
      expect(screen.getByTestId('doctor-violations-count')).toHaveTextContent('0');
    });
  });
});
