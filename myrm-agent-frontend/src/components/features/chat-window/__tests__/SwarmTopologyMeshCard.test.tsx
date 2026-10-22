import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  SwarmTopologyMeshCard,
  SwarmTopologyStateData,
} from '../SwarmTopologyMeshCard';

describe('SwarmTopologyMeshCard', () => {
  it('renders initial star topology state with active nodes and edges metrics', () => {
    const handleDismiss = vi.fn();
    render(<SwarmTopologyMeshCard chatId="test-chat-01" onDismiss={handleDismiss} />);

    expect(screen.getByTestId('swarm-topology-mesh-card')).toBeInTheDocument();
    expect(screen.getByTestId('stat-nodes-count')).toHaveTextContent('4');
    expect(screen.getByTestId('stat-edges-count')).toHaveTextContent('3');
    expect(screen.getByTestId('stat-facts-count')).toHaveTextContent('1');
    expect(screen.getByTestId('stat-messages-count')).toHaveTextContent('0');

    // Dismiss button
    const dismissBtn = screen.getByRole('button', { name: /Dismiss dialog/i });
    fireEvent.click(dismissBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('switches topology type dynamically to peer_mesh and updates edges count', () => {
    const handleTopologyChange = vi.fn();
    render(
      <SwarmTopologyMeshCard
        chatId="test-chat-02"
        onTopologyChange={handleTopologyChange}
      />
    );

    const switchMeshBtn = screen.getByTestId('btn-switch-peer_mesh');
    fireEvent.click(switchMeshBtn);

    expect(handleTopologyChange).toHaveBeenCalledWith('peer_mesh');
    // 4 nodes in full mesh -> 6 edges
    expect(screen.getByTestId('stat-edges-count')).toHaveTextContent('6');
    expect(screen.getByTestId('status-banner')).toHaveTextContent(
      'Swarm topology switched to peer_mesh.'
    );
  });

  it('switches to pipeline and ring layouts properly', () => {
    render(<SwarmTopologyMeshCard chatId="test-chat-03" />);

    // Switch to pipeline -> 3 edges
    fireEvent.click(screen.getByTestId('btn-switch-pipeline'));
    expect(screen.getByTestId('stat-edges-count')).toHaveTextContent('3');

    // Switch to ring -> 4 edges
    fireEvent.click(screen.getByTestId('btn-switch-ring'));
    expect(screen.getByTestId('stat-edges-count')).toHaveTextContent('4');
  });

  it('transmits broadcast message over P2P mesh bus and updates message feed', () => {
    render(<SwarmTopologyMeshCard chatId="test-chat-04" />);

    const input = screen.getByTestId('input-broadcast-text');
    const sendBtn = screen.getByTestId('btn-send-broadcast');
    expect(sendBtn).toBeDisabled();

    fireEvent.change(input, { target: { value: 'Cluster heartbeat: all green' } });
    expect(sendBtn).not.toBeDisabled();
    fireEvent.click(sendBtn);

    expect(screen.getByTestId('stat-messages-count')).toHaveTextContent('1');
    expect(screen.getByTestId('status-banner')).toHaveTextContent(
      'Broadcast message delivered to all mesh nodes.'
    );
    expect(input).toHaveValue('');
  });

  it('records and increments version of shared blackboard facts', () => {
    render(<SwarmTopologyMeshCard chatId="test-chat-05" />);

    const keyInput = screen.getByTestId('input-fact-key');
    const valInput = screen.getByTestId('input-fact-value');
    const addBtn = screen.getByTestId('btn-add-fact');

    // Add new fact
    fireEvent.change(keyInput, { target: { value: 'release.version' } });
    fireEvent.change(valInput, { target: { value: '2.5.0-rc1' } });
    fireEvent.click(addBtn);

    expect(screen.getByTestId('stat-facts-count')).toHaveTextContent('2');
    const factCard = screen.getByTestId('blackboard-fact-release.version');
    expect(within(factCard).getByText('v1')).toBeInTheDocument();

    // Update same fact -> version increments to v2
    fireEvent.change(keyInput, { target: { value: 'release.version' } });
    fireEvent.change(valInput, { target: { value: '2.5.0-final' } });
    fireEvent.click(addBtn);

    expect(within(factCard).getByText('v2')).toBeInTheDocument();
    expect(within(factCard).getByText('2.5.0-final')).toBeInTheDocument();
  });

  it('performs live role migration on a worker node', () => {
    render(<SwarmTopologyMeshCard chatId="test-chat-06" />);

    const migrateWorker01Btn = screen.getByTestId('btn-migrate-agent-worker-01');
    fireEvent.click(migrateWorker01Btn);

    expect(screen.getByTestId('status-banner')).toHaveTextContent(
      'Node agent-worker-01 migrated to reviewer.'
    );

    const workerCard = screen.getByTestId('node-card-agent-worker-01');
    expect(within(workerCard).getByText('reviewer')).toBeInTheDocument();
  });
});
