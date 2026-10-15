import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FleetWideProfileRailCard } from '../FleetWideProfileRailCard';
import { DEFAULT_FLEET_STATE, RelayedArtifact } from '../fleet-router/types';

describe('FleetWideProfileRailCard', () => {
  it('renders card header, distributed fleet badges, gateways and accessible live output', () => {
    render(<FleetWideProfileRailCard chatId="chat-fleet-1" />);

    expect(
      screen.getByRole('article', { name: /Fleet-Wide Profile Rail Card/i }),
    ).toBeInTheDocument();
    expect(screen.getByText('Fleet-Wide Profile Rail')).toBeInTheDocument();
    expect(screen.getByText('Distributed Fleet')).toBeInTheDocument();
    expect(screen.getByText('Host Context Aware')).toBeInTheDocument();

    // Verify gateway cards
    expect(screen.getByText('MacBook Pro Host')).toBeInTheDocument();
    expect(screen.getByText('Ubuntu GPU Cluster')).toBeInTheDocument();
    expect(screen.getByText('Tokyo VPS Relay')).toBeInTheDocument();

    // Verify accessible status element
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(
      screen.getByText(/multi-gateway dynamic router active with offline command buffering/i),
    ).toBeInTheDocument();
  });

  it('switches active session between agent profiles across gateways', async () => {
    const handleSwitch = vi.fn().mockResolvedValue(undefined);

    render(
      <FleetWideProfileRailCard
        chatId="chat-fleet-1"
        initialState={DEFAULT_FLEET_STATE}
        onSwitchProfile={handleSwitch}
      />,
    );

    // Initial state: Primary Orchestrator is active
    expect(screen.getByText('Primary Orchestrator')).toBeInTheDocument();

    // Switch to DeepCoder V2 on the Ubuntu GPU Cluster
    const coderBtn = screen.getByRole('button', { name: /DeepCoder V2/i });
    fireEvent.click(coderBtn);

    expect(handleSwitch).toHaveBeenCalledWith('prof-gpu-coder');
    await waitFor(() => {
      expect(
        screen.getByText(/Active session switched to 'DeepCoder V2'/i),
      ).toBeInTheDocument();
    });
  });

  it('buffers command into FIFO queue when target gateway is offline', () => {
    render(
      <FleetWideProfileRailCard
        chatId="chat-fleet-1"
        initialState={DEFAULT_FLEET_STATE}
      />,
    );

    // Initial buffer count badge is 1
    expect(screen.getByText(/Offline Buffer:/i)).toBeInTheDocument();

    // Find Buffer Cmd button on Tokyo VPS Relay (offline)
    const bufferCmdButtons = screen.getAllByRole('button', { name: /Buffer Cmd/i });
    expect(bufferCmdButtons.length).toBeGreaterThanOrEqual(1);

    // Click buffer command for Tokyo Crawler
    fireEvent.click(bufferCmdButtons[0]);

    // Live status should announce buffering
    expect(
      screen.getByText(/Command safely queued into offline FIFO buffer/i),
    ).toBeInTheDocument();
  });

  it('opens offline buffer modal and triggers auto-healing flush', async () => {
    const handleFlush = vi.fn().mockResolvedValue([]);

    render(
      <FleetWideProfileRailCard
        chatId="chat-fleet-1"
        initialState={DEFAULT_FLEET_STATE}
        onFlushGateway={handleFlush}
      />,
    );

    // Open buffer modal
    const bufferModalBtn = screen.getByText(/Offline Buffer:/i);
    fireEvent.click(bufferModalBtn);

    expect(
      screen.getByRole('dialog', { name: /Offline Command Buffer Modal/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Target Profile:/i)).toBeInTheDocument();

    // Trigger flush
    const flushBtn = screen.getByRole('button', { name: /Flush Queue/i });
    fireEvent.click(flushBtn);

    expect(handleFlush).toHaveBeenCalledWith('gw-vps-edge');

    await waitFor(() => {
      expect(
        screen.getByText(/Auto-healing complete: reconnected to 'Tokyo VPS Relay'/i),
      ).toBeInTheDocument();
    });
  });

  it('opens cross-gateway artifact relay modal and verifies SHA-256 transmission', async () => {
    const handleRelay = vi.fn().mockResolvedValue({
      artifact_id: 'art-relay-5501',
      source_gateway: 'gw-mac-local',
      target_gateway: 'gw-cloud-gpu',
      name: 'benchmark_summary.json',
      file_path: 'reports/eval.json',
      sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
      chunk_data: '{"model": "qwen2.5-coder", "pass_rate": 0.942}',
      created_at: Date.now(),
      is_verified: true,
    } as RelayedArtifact);

    render(
      <FleetWideProfileRailCard
        chatId="chat-fleet-1"
        initialState={DEFAULT_FLEET_STATE}
        onRelayArtifact={handleRelay}
      />,
    );

    // Open relay modal
    const openRelayBtn = screen.getByRole('button', { name: /Relay Artifact/i });
    fireEvent.click(openRelayBtn);

    expect(
      screen.getByRole('dialog', { name: /Cross-Gateway Artifact Relay Modal/i }),
    ).toBeInTheDocument();

    // Submit form
    const submitBtn = screen.getByRole('button', {
      name: /Relay Artifact via Secure Tunnel/i,
    });
    fireEvent.click(submitBtn);

    expect(handleRelay).toHaveBeenCalledWith(
      'gw-mac-local',
      expect.any(String),
      'benchmark_summary.json',
      'reports/eval.json',
      '{"model": "qwen2.5-coder", "pass_rate": 0.942}',
    );

    await waitFor(() => {
      expect(screen.getByText(/✓ Relayed Successfully/i)).toBeInTheDocument();
      expect(screen.getByText(/Verified SHA-256/i)).toBeInTheDocument();
      expect(screen.getByText(/art-relay-5501/i)).toBeInTheDocument();
    });
  });
});
