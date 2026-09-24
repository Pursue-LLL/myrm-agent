import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AgentCommerceBudgetSection from '../AgentCommerceBudgetSection';
import {
  getCommerceBudgetStatus,
  updateCommerceBudgetConfig,
  setEmergencyFreeze,
  getCommerceSpendingLedger,
  type CommerceBudgetStatus,
  type SpendingLedgerEntry,
} from '@/services/commerceBudget';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/services/commerceBudget', () => ({
  getCommerceBudgetStatus: vi.fn(),
  updateCommerceBudgetConfig: vi.fn(),
  setEmergencyFreeze: vi.fn(),
  getCommerceSpendingLedger: vi.fn(),
}));

describe('AgentCommerceBudgetSection', () => {
  const mockBudgetStatus: CommerceBudgetStatus = {
    dailyCapCents: 1000,
    perActionCapCents: 200,
    dailySpentCents: 150,
    activeReservedCents: 50,
    remainingCents: 800,
    currency: 'USD',
    isFrozen: false,
    allowedMerchants: ['namesilo.com', '*.openai.com'],
    totalLeasesTracked: 3,
  };

  const mockLedger: SpendingLedgerEntry[] = [
    {
      lease_id: 'lease_abc123',
      merchant_domain: 'namesilo.com',
      amount_cents: 99,
      currency: 'USD',
      status: 'committed',
      session_id: 'sess_1',
      task_id: 'task_1',
      idempotency_key: 'idemp_1',
      created_at: '2026-09-24T00:00:00Z',
      committed_at: '2026-09-24T00:01:00Z',
      refunded_at: null,
      entry_hash: 'hash123',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getCommerceBudgetStatus).mockResolvedValue(mockBudgetStatus);
    vi.mocked(getCommerceSpendingLedger).mockResolvedValue(mockLedger);
  });

  it('renders budget metrics and ledger entries successfully', async () => {
    render(<AgentCommerceBudgetSection />);

    await waitFor(() => {
      expect(screen.getByText('title')).toBeInTheDocument();
    });

    expect(screen.getByDisplayValue('10.00')).toBeInTheDocument();
    expect(screen.getByDisplayValue('2.00')).toBeInTheDocument();
    expect(screen.getByText('namesilo.com')).toBeInTheDocument();
    expect(screen.getByText('*.openai.com')).toBeInTheDocument();
    expect(screen.getByText('$0.99')).toBeInTheDocument();
    expect(screen.getByText('committed')).toBeInTheDocument();
  });

  it('toggles emergency freeze breaker', async () => {
    vi.mocked(setEmergencyFreeze).mockResolvedValue({
      ...mockBudgetStatus,
      isFrozen: true,
    });

    render(<AgentCommerceBudgetSection />);

    await waitFor(() => {
      expect(screen.getByText('activeStatus')).toBeInTheDocument();
    });

    const freezeBtn = screen.getByRole('button', { name: /activeStatus/i });
    fireEvent.click(freezeBtn);

    await waitFor(() => {
      expect(setEmergencyFreeze).toHaveBeenCalledWith(true);
    });
  });

  it('adds and removes merchant domain in whitelist and saves config', async () => {
    vi.mocked(updateCommerceBudgetConfig).mockResolvedValue({
      ...mockBudgetStatus,
      allowedMerchants: ['namesilo.com', '*.openai.com', '2captcha.com'],
    });

    render(<AgentCommerceBudgetSection />);

    await waitFor(() => {
      expect(screen.getByText('namesilo.com')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('addMerchantPlaceholder');
    fireEvent.change(input, { target: { value: '2captcha.com' } });

    const addBtn = screen.getByRole('button', { name: /addMerchant/i });
    fireEvent.click(addBtn);

    expect(screen.getByText('2captcha.com')).toBeInTheDocument();

    const saveBtn = screen.getByRole('button', { name: /save/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(updateCommerceBudgetConfig).toHaveBeenCalledWith({
        daily_cap_cents: 1000,
        per_action_cap_cents: 200,
        currency: 'USD',
        is_frozen: false,
        lease_ttl_seconds: 300,
        allowed_merchants: ['namesilo.com', '*.openai.com', '2captcha.com'],
      });
    });
  });
});
