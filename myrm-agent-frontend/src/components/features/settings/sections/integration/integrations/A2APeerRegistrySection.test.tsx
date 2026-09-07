import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { A2APeerRegistrySection } from './A2APeerRegistrySection';
import * as a2aService from '@/services/a2aPeer';

const stableT = (key: string, values?: Record<string, unknown>) => {
  if (values?.latency !== undefined) {
    return `${key}:${values.latency}ms`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/services/a2aPeer', () => ({
  listA2APeers: vi.fn(),
  createA2APeer: vi.fn(),
  updateA2APeer: vi.fn(),
  deleteA2APeer: vi.fn(),
  probeA2APeer: vi.fn(),
}));

describe('A2APeerRegistrySection - Full Flow', () => {
  const mockPeers: a2aService.A2APeer[] = [
    {
      id: 'peer-1',
      name: 'Hermes Research Agent',
      base_url: 'https://hermes.example.com',
      description: 'Deep research multi-agent node',
      auth_type: 'bearer',
      is_active: true,
      has_token: true,
      masked_token: 'sk-****5678',
      last_probed_at: '2026-09-06T12:00:00Z',
      last_probe_status: 'ok',
      last_probe_error: null,
      cached_card_json: {
        name: 'Hermes Research Agent',
        description: 'Deep research multi-agent node',
        skills: ['research', 'synthesize'],
      },
      created_at: '2026-09-06T10:00:00Z',
      updated_at: '2026-09-06T12:00:00Z',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state when no peers exist', async () => {
    (a2aService.listA2APeers as any).mockResolvedValueOnce([]);
    render(<A2APeerRegistrySection />);

    expect(await screen.findByText('noPeers')).toBeInTheDocument();
    expect(screen.getByText('noPeersDesc')).toBeInTheDocument();
  });

  it('renders populated peer card with status and masked credential', async () => {
    (a2aService.listA2APeers as any).mockResolvedValueOnce(mockPeers);
    render(<A2APeerRegistrySection />);

    expect(await screen.findByText('Hermes Research Agent')).toBeInTheDocument();
    expect(screen.getByText('https://hermes.example.com')).toBeInTheDocument();
    expect(screen.getByText('sk-****5678')).toBeInTheDocument();
    expect(screen.getByText('statusOk')).toBeInTheDocument();
  });

  it('probes a saved peer and updates feedback banner', async () => {
    (a2aService.listA2APeers as any).mockResolvedValue(mockPeers);
    (a2aService.probeA2APeer as any).mockResolvedValueOnce({
      success: true,
      status: 'ok',
      latency_ms: 45.2,
      agent_card: { name: 'Hermes Research Agent' },
    });

    render(<A2APeerRegistrySection />);
    expect(await screen.findByText('Hermes Research Agent')).toBeInTheDocument();

    const probeButtons = screen.getAllByRole('button', { name: /probe/i });
    fireEvent.click(probeButtons[0]);

    await waitFor(() => {
      expect(a2aService.probeA2APeer).toHaveBeenCalledWith({ peer_id: 'peer-1' });
    });

    expect(await screen.findByText('probeSuccess:45.2ms')).toBeInTheDocument();
  });

  it('opens create modal and registers new peer', async () => {
    (a2aService.listA2APeers as any).mockResolvedValueOnce([]);
    (a2aService.createA2APeer as any).mockResolvedValueOnce({
      id: 'peer-new',
      name: 'OpenClaw Reviewer',
      base_url: 'https://claw.example.com',
      auth_type: 'bearer',
      is_active: true,
      has_token: true,
      created_at: '2026-09-06T12:00:00Z',
      updated_at: '2026-09-06T12:00:00Z',
    });

    render(<A2APeerRegistrySection />);
    expect(await screen.findByText('noPeers')).toBeInTheDocument();

    const addButtons = screen.getAllByRole('button', { name: /addPeer/i });
    fireEvent.click(addButtons[0]);

    expect(screen.getByText('newPeer')).toBeInTheDocument();

    const nameInput = screen.getByPlaceholderText('peerNamePlaceholder');
    const urlInput = screen.getByPlaceholderText('baseUrlPlaceholder');

    fireEvent.change(nameInput, { target: { value: 'OpenClaw Reviewer' } });
    fireEvent.change(urlInput, { target: { value: 'https://claw.example.com' } });

    const saveButton = screen.getByRole('button', { name: /savePeer/i });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(a2aService.createA2APeer).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'OpenClaw Reviewer',
          base_url: 'https://claw.example.com',
        }),
      );
    });
  });

  it('deletes a peer when confirmed', async () => {
    (a2aService.listA2APeers as any).mockResolvedValueOnce(mockPeers);
    (a2aService.deleteA2APeer as any).mockResolvedValueOnce({ success: true });
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    render(<A2APeerRegistrySection />);
    expect(await screen.findByText('Hermes Research Agent')).toBeInTheDocument();

    const deleteButtons = screen.getAllByRole('button').filter((b) => b.querySelector('svg.lucide-trash-2'));
    expect(deleteButtons.length).toBeGreaterThan(0);
    fireEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(a2aService.deleteA2APeer).toHaveBeenCalledWith('peer-1');
    });
  });
});
