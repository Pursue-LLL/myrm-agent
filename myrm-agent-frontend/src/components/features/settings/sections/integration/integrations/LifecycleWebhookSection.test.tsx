import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LifecycleWebhookSection } from './LifecycleWebhookSection';
import * as webhookService from '@/services/lifecycleWebhook';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/lifecycleWebhook', () => ({
  listLifecycleWebhooks: vi.fn(),
  createLifecycleWebhook: vi.fn(),
  updateLifecycleWebhook: vi.fn(),
  deleteLifecycleWebhook: vi.fn(),
  pingLifecycleWebhook: vi.fn(),
}));

describe('LifecycleWebhookSection - Full Flow', () => {
  const mockWebhooks: webhookService.LifecycleWebhook[] = [
    {
      id: 'wh-1',
      name: 'CI Webhook',
      url: 'https://example.com/api/hook',
      secret: 'whsec_secret123',
      events: ['session_completed', 'session_failed'],
      agent_id: null,
      is_active: true,
      timeout_seconds: 10,
      last_delivery_at: '2026-08-22T00:00:00Z',
      last_delivery_status: 200,
      last_error: null,
      created_at: '2026-08-22T00:00:00Z',
      updated_at: '2026-08-22T00:00:00Z',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state when no webhooks exist', async () => {
    (webhookService.listLifecycleWebhooks as any).mockResolvedValueOnce([]);
    render(<LifecycleWebhookSection />);

    expect(await screen.findByText('noEndpoints')).toBeInTheDocument();
    expect(screen.getByText('noEndpointsDesc')).toBeInTheDocument();
  });

  it('renders populated webhooks list with status badges', async () => {
    (webhookService.listLifecycleWebhooks as any).mockResolvedValueOnce(mockWebhooks);
    render(<LifecycleWebhookSection />);

    expect(await screen.findByText('CI Webhook')).toBeInTheDocument();
    expect(screen.getByText('https://example.com/api/hook')).toBeInTheDocument();
    expect(screen.getByText('HMAC')).toBeInTheDocument();
    expect(screen.getByText('HTTP 200')).toBeInTheDocument();
  });

  it('opens creation form and creates a new webhook with random secret and custom events', async () => {
    (webhookService.listLifecycleWebhooks as any)
      .mockResolvedValueOnce(mockWebhooks)
      .mockResolvedValueOnce([
        ...mockWebhooks,
        {
          id: 'wh-2',
          name: 'Alert Bot',
          url: 'https://feishu.example.com/hook',
          secret: 'whsec_random123',
          events: ['session_completed', 'session_failed', 'approval_required', 'goal_terminal'],
          agent_id: null,
          is_active: true,
          timeout_seconds: 10,
          last_delivery_at: null,
          last_delivery_status: null,
          last_error: null,
          created_at: '2026-08-22T00:00:00Z',
          updated_at: '2026-08-22T00:00:00Z',
        },
      ]);
    (webhookService.createLifecycleWebhook as any).mockResolvedValueOnce({
      id: 'wh-2',
      name: 'Alert Bot',
      url: 'https://feishu.example.com/hook',
      events: ['session_completed', 'session_failed', 'approval_required', 'goal_terminal'],
      is_active: true,
      timeout_seconds: 10,
      created_at: '2026-08-22T00:00:00Z',
      updated_at: '2026-08-22T00:00:00Z',
    });

    render(<LifecycleWebhookSection />);
    expect(await screen.findByText('CI Webhook')).toBeInTheDocument();

    // Click Add Webhook button
    const addBtn = screen.getByRole('button', { name: /addEndpoint/i });
    fireEvent.click(addBtn);

    expect(screen.getByText('newEndpoint')).toBeInTheDocument();

    // Fill inputs
    const inputs = screen.getAllByRole('textbox');
    // inputs[0]: name, inputs[1]: url, inputs[2]: secret
    fireEvent.change(inputs[0], { target: { value: 'Alert Bot' } });
    fireEvent.change(inputs[1], { target: { value: 'https://feishu.example.com/hook' } });

    // Generate random secret
    const genBtn = screen.getByText('generateRandom');
    fireEvent.click(genBtn);
    expect(inputs[2].getAttribute('value')).toMatch(/^whsec_[0-9a-f]{32}$/);

    // Toggle event selection
    const goalBadge = screen.getByText('Goal Terminal');
    fireEvent.click(goalBadge);

    // Save
    const saveBtn = screen.getByRole('button', { name: /saveEndpoint/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(webhookService.createLifecycleWebhook).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Alert Bot',
          url: 'https://feishu.example.com/hook',
          events: expect.arrayContaining(['goal_terminal']),
          is_active: true,
        }),
      );
    });
  });

  it('deletes an existing webhook', async () => {
    (webhookService.listLifecycleWebhooks as any).mockResolvedValueOnce(mockWebhooks);
    (webhookService.deleteLifecycleWebhook as any).mockResolvedValueOnce(undefined);

    render(<LifecycleWebhookSection />);
    expect(await screen.findByText('CI Webhook')).toBeInTheDocument();

    const deleteBtns = screen.getAllByRole('button');
    const deleteBtn = deleteBtns[deleteBtns.length - 1]; // Last button is delete
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(webhookService.deleteLifecycleWebhook).toHaveBeenCalledWith('wh-1');
    });
  });

  it('handles ping failure gracefully', async () => {
    (webhookService.listLifecycleWebhooks as any).mockResolvedValueOnce(mockWebhooks);
    (webhookService.pingLifecycleWebhook as any).mockResolvedValueOnce({
      success: false,
      status_code: 500,
      latency_ms: 120.5,
      error: 'HTTP 500 Internal Server Error',
    });

    render(<LifecycleWebhookSection />);
    expect(await screen.findByText('CI Webhook')).toBeInTheDocument();

    const pingBtn = screen.getByRole('button', { name: /testPing/i });
    fireEvent.click(pingBtn);

    expect(await screen.findByText(/Ping Failed: HTTP 500 Internal Server Error/i)).toBeInTheDocument();
  });
});
