import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LifecycleWebhookSection } from './LifecycleWebhookSection';
import * as webhookService from '@/services/lifecycleWebhook';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/services/lifecycleWebhook', () => ({
  listLifecycleWebhooks: vi.fn(),
  createLifecycleWebhook: vi.fn(),
  updateLifecycleWebhook: vi.fn(),
  deleteLifecycleWebhook: vi.fn(),
  pingLifecycleWebhook: vi.fn(),
}));

describe('LifecycleWebhookSection', () => {
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

  it('renders loading skeleton initially and loads webhooks', async () => {
    (webhookService.listLifecycleWebhooks as any).mockResolvedValueOnce(mockWebhooks);
    render(<LifecycleWebhookSection />);

    expect(await screen.findByText('CI Webhook')).toBeInTheDocument();
    expect(screen.getByText('https://example.com/api/hook')).toBeInTheDocument();
    expect(screen.getByText('HMAC')).toBeInTheDocument();
    expect(screen.getByText('HTTP 200')).toBeInTheDocument();
  });

  it('allows toggling active state', async () => {
    (webhookService.listLifecycleWebhooks as any).mockResolvedValueOnce(mockWebhooks);
    (webhookService.updateLifecycleWebhook as any).mockResolvedValueOnce({
      ...mockWebhooks[0],
      is_active: false,
    });

    render(<LifecycleWebhookSection />);
    expect(await screen.findByText('CI Webhook')).toBeInTheDocument();

    const switchBtn = screen.getByRole('switch', { name: /toggle webhook/i });
    fireEvent.click(switchBtn);

    await waitFor(() => {
      expect(webhookService.updateLifecycleWebhook).toHaveBeenCalledWith('wh-1', {
        is_active: false,
      });
    });
  });

  it('executes ping test and displays results', async () => {
    (webhookService.listLifecycleWebhooks as any).mockResolvedValueOnce(mockWebhooks);
    (webhookService.pingLifecycleWebhook as any).mockResolvedValueOnce({
      success: true,
      status_code: 200,
      latency_ms: 45.2,
      error: null,
    });

    render(<LifecycleWebhookSection />);
    expect(await screen.findByText('CI Webhook')).toBeInTheDocument();

    const pingBtn = screen.getByRole('button', { name: /testPing/i });
    fireEvent.click(pingBtn);

    expect(await screen.findByText(/Ping Successful: HTTP 200 \(45.2ms\)/i)).toBeInTheDocument();
  });
});
