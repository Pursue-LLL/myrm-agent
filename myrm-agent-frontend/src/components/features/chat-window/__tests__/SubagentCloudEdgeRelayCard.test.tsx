import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SubagentCloudEdgeRelayCard } from '../SubagentCloudEdgeRelayCard';

describe('SubagentCloudEdgeRelayCard', () => {
  it('renders initial metrics banner and default shared artifacts', () => {
    const handleDismiss = vi.fn();
    render(
      <SubagentCloudEdgeRelayCard
        chatId="test-chat-relay-01"
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByTestId('subagent-cloud-edge-relay-card')).toBeInTheDocument();
    expect(screen.getByText('Hybrid Cloud-Edge Sandbox Relay')).toBeInTheDocument();
    expect(screen.getByText('Item 58 Active')).toBeInTheDocument();
    expect(screen.getByText('q3_ecommerce_transactions.csv')).toBeInTheDocument();
    expect(screen.getByText('cluster_telemetry_batch.jsonl')).toBeInTheDocument();

    // Verify initial metric values
    expect(screen.getByText('Synced Rows')).toBeInTheDocument();
    expect(screen.getByText('196')).toBeInTheDocument();

    // Test dismiss callback
    const dismissBtn = screen.getByTestId('relay-card-dismiss');
    fireEvent.click(dismissBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('toggles artifact chunk details and displays local/cloud sandbox provenance', () => {
    render(<SubagentCloudEdgeRelayCard chatId="test-chat-relay-02" />);

    // Initially art-sales-q3 is expanded
    expect(screen.getByText('Cloud Sandbox')).toBeInTheDocument();
    expect(screen.getByText('Local Sandbox')).toBeInTheDocument();
    expect(screen.getByText(/chunk-init-01/i)).toBeInTheDocument();

    // Collapse it
    const artifactHeader = screen.getByText('q3_ecommerce_transactions.csv');
    fireEvent.click(artifactHeader);
    expect(screen.queryByText('chunk-init-01')).not.toBeInTheDocument();

    // Expand it again
    fireEvent.click(artifactHeader);
    expect(screen.getByText(/chunk-init-01/i)).toBeInTheDocument();
  });

  it('simulates cloud append incrementing version and rows', async () => {
    const handleSyncComplete = vi.fn();
    render(
      <SubagentCloudEdgeRelayCard
        chatId="test-chat-relay-03"
        onSyncComplete={handleSyncComplete}
      />
    );

    const appendBtn = screen.getByTestId('btn-cloud-append');
    fireEvent.click(appendBtn);

    // Wait for simulate timeout
    await waitFor(() => {
      expect(screen.getByText('v3')).toBeInTheDocument();
    }, { timeout: 1000 });

    expect(handleSyncComplete).toHaveBeenCalledWith('art-sales-q3', 3);
  });

  it('switches to egress relays tab and lists network fetch traffic', () => {
    render(<SubagentCloudEdgeRelayCard chatId="test-chat-relay-04" />);

    const relaysTab = screen.getByTestId('tab-relays');
    fireEvent.click(relaysTab);

    expect(screen.getByTestId('relay-item-relay-ext-01')).toBeInTheDocument();
    expect(screen.getByText('https://api.github.com/repos/org/packages')).toBeInTheDocument();
    expect(screen.getAllByText(/200\s*OK/i).length).toBeGreaterThanOrEqual(1);
  });

  it('triggers SSRF guard probe and increments defensive counter', () => {
    render(<SubagentCloudEdgeRelayCard chatId="test-chat-relay-05" />);

    const relaysTab = screen.getByTestId('tab-relays');
    fireEvent.click(relaysTab);

    const ssrfBtn = screen.getByTestId('btn-test-ssrf');
    fireEvent.click(ssrfBtn);

    expect(screen.getByText('4 blocked')).toBeInTheDocument();
    expect(screen.getByText(/SSRF policy violation/i)).toBeInTheDocument();
    expect(screen.getByText('http://169.254.169.254/latest/meta-data')).toBeInTheDocument();
  });
});
