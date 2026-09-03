import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LifecycleWebhookSection } from './LifecycleWebhookSection';
import * as webhookService from '@/services/lifecycleWebhook';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/services/lifecycleWebhook', () => ({
  listLifecycleWebhooks: vi.fn(),
  createLifecycleWebhook: vi.fn(),
  updateLifecycleWebhook: vi.fn(),
  deleteLifecycleWebhook: vi.fn(),
  pingSavedLifecycleWebhook: vi.fn(),
}));

vi.mock('@/services/agent', () => ({
  listAgents: vi.fn().mockResolvedValue({ items: [] }),
}));

describe('LifecycleWebhookSection - Full Flow', () => {
  const mockWebhooks: webhookService.LifecycleWebhook[] = [
    {
      id: 'wh-1',
      name: 'CI Webhook',
      url: 'https://example.com/api/hook',
      secret: 'whsec_secret123',
      has_secret: true,
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
    (webhookService.listLifecycleWebhooks as any).mockResolvedValueOnce(mockWebhooks).mockResolvedValueOnce([
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
    const goalBadge = screen.getByText('events.goal_terminal');
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

  it('disables save when all events are deselected', async () => {
    (webhookService.listLifecycleWebhooks as any).mockResolvedValueOnce([]);
    render(<LifecycleWebhookSection />);
    expect(await screen.findByText('noEndpoints')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /addEndpoint/i }));

    fireEvent.click(screen.getByText('events.session_completed'));
    fireEvent.click(screen.getByText('events.session_failed'));
    fireEvent.click(screen.getByText('events.approval_required'));

    expect(screen.getByText('eventsRequired')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /saveEndpoint/i })).toBeDisabled();
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
    (webhookService.pingSavedLifecycleWebhook as any).mockResolvedValueOnce({
      success: false,
      status_code: 500,
      latency_ms: 120.5,
      error: 'HTTP 500 Internal Server Error',
    });

    render(<LifecycleWebhookSection />);
    expect(await screen.findByText('CI Webhook')).toBeInTheDocument();

    const pingBtn = screen.getByRole('button', { name: /testPing/i });
    fireEvent.click(pingBtn);

    expect(await screen.findByText('pingFailed')).toBeInTheDocument();
    expect(webhookService.pingSavedLifecycleWebhook).toHaveBeenCalledWith('wh-1');
  });

  it('opens edit form and updates webhook without resending secret when blank', async () => {
    const scopedWebhook: webhookService.LifecycleWebhook = {
      ...mockWebhooks[0],
      agent_id: 'agent-1',
      events: ['session_completed'],
    };

    (webhookService.listLifecycleWebhooks as any)
      .mockResolvedValueOnce([scopedWebhook])
      .mockResolvedValueOnce([
        { ...scopedWebhook, name: 'CI Webhook Updated', events: ['session_completed', 'goal_terminal'] },
      ]);
    (webhookService.updateLifecycleWebhook as any).mockResolvedValueOnce({
      ...scopedWebhook,
      name: 'CI Webhook Updated',
      events: ['session_completed', 'goal_terminal'],
    });

    render(<LifecycleWebhookSection />);
    expect(await screen.findByText('CI Webhook')).toBeInTheDocument();

    const editBtn = screen.getByRole('button', { name: /editEndpoint/i });
    fireEvent.click(editBtn);

    expect(screen.getByText('editEndpoint')).toBeInTheDocument();

    const inputs = screen.getAllByRole('textbox');
    fireEvent.change(inputs[0], { target: { value: 'CI Webhook Updated' } });

    const goalBadge = screen.getByText('events.goal_terminal');
    fireEvent.click(goalBadge);

    const saveBtn = screen.getByRole('button', { name: /saveChanges/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(webhookService.updateLifecycleWebhook).toHaveBeenCalledWith(
        'wh-1',
        expect.objectContaining({
          name: 'CI Webhook Updated',
          url: 'https://example.com/api/hook',
          events: expect.arrayContaining(['session_completed', 'goal_terminal']),
        }),
      );
    });

    const updatePayload = (webhookService.updateLifecycleWebhook as any).mock.calls[0][1];
    expect(updatePayload.secret).toBeUndefined();
    expect(updatePayload.clear_agent_scope).toBeUndefined();
  });

  it('sends clear_agent_scope when agent scope is cleared on edit', async () => {
    const scopedWebhook: webhookService.LifecycleWebhook = {
      ...mockWebhooks[0],
      agent_id: 'agent-1',
    };

    (webhookService.listLifecycleWebhooks as any)
      .mockResolvedValueOnce([scopedWebhook])
      .mockResolvedValueOnce([{ ...scopedWebhook, agent_id: null }]);
    (webhookService.updateLifecycleWebhook as any).mockResolvedValueOnce({
      ...scopedWebhook,
      agent_id: null,
    });

    render(<LifecycleWebhookSection />);
    expect(await screen.findByText('CI Webhook')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /editEndpoint/i }));

    const agentScopeTrigger = screen.getByRole('combobox');
    fireEvent.click(agentScopeTrigger);

    const allAgentsOption = await screen.findByRole('option', { name: 'agentScopeAll' });
    fireEvent.click(allAgentsOption);

    fireEvent.click(screen.getByRole('button', { name: /saveChanges/i }));

    await waitFor(() => {
      expect(webhookService.updateLifecycleWebhook).toHaveBeenCalledWith(
        'wh-1',
        expect.objectContaining({
          clear_agent_scope: true,
        }),
      );
    });
  });
});
