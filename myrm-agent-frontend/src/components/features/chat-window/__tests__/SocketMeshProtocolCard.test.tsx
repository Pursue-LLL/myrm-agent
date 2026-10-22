import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SocketMeshProtocolCard } from '../SocketMeshProtocolCard';

describe('SocketMeshProtocolCard', () => {
  it('renders section, header, project identifier, and active peers grid', () => {
    render(<SocketMeshProtocolCard chatId="chat-mesh-99" project="alpha-mesh" />);

    expect(
      screen.getByRole('region', {
        name: /P2P Agent Socket Mesh Protocol/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/chat-mesh-99/i)).toBeInTheDocument();
    expect(screen.getByText('alpha-mesh')).toBeInTheDocument();

    // Default peers
    expect(screen.getByText('planner')).toBeInTheDocument();
    expect(screen.getByText('coder')).toBeInTheDocument();
    expect(screen.getByText('security-auditor')).toBeInTheDocument();
  });

  it('triggers peer ping probe and displays status response', async () => {
    const handlePing = vi.fn().mockResolvedValue('PONG from coder: Active worker');

    render(
      <SocketMeshProtocolCard
        chatId="chat-mesh-99"
        onPingPeer={handlePing}
      />,
    );

    const pingButtons = screen.getAllByRole('button', { name: /Ping Peer Health/i });
    expect(pingButtons.length).toBeGreaterThanOrEqual(1);

    fireEvent.click(pingButtons[0]);

    expect(handlePing).toHaveBeenCalledWith('planner');
    expect(await screen.findByText('PONG from coder: Active worker')).toBeInTheDocument();
  });

  it('switches to Envelope Console, dispatches prompt envelope and displays response', async () => {
    const handleSend = vi.fn().mockResolvedValue('Consensus DAG validated in 1.2ms');

    render(
      <SocketMeshProtocolCard
        chatId="chat-mesh-99"
        onSendEnvelope={handleSend}
      />,
    );

    const consoleTab = screen.getByRole('button', { name: /Atomic Envelope Console/i });
    fireEvent.click(consoleTab);

    expect(screen.getByText(/Prompt Payload \(Envelope Content\):/i)).toBeInTheDocument();

    const textarea = screen.getByLabelText(/Prompt Payload \(Envelope Content\):/i);
    fireEvent.change(textarea, { target: { value: 'Run invariant checks on ledger' } });

    const sendBtn = screen.getByRole('button', { name: /Dispatch Prompt & Await/i });
    fireEvent.click(sendBtn);

    expect(handleSend).toHaveBeenCalledWith('planner', 'coder', 'Run invariant checks on ledger');
    expect(await screen.findByText(/Consensus DAG validated in 1.2ms/i)).toBeInTheDocument();
  });

  it('switches to Mesh Audit Trail tab and displays chronological events', () => {
    render(<SocketMeshProtocolCard chatId="chat-mesh-99" />);

    const auditTab = screen.getByRole('button', { name: /Mesh Audit Trail/i });
    fireEvent.click(auditTab);

    expect(screen.getAllByText('NODE_STARTED').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Registered at \/tmp\/\.myrm\/coms\/sockets\/planner\.sock/i)).toBeInTheDocument();
  });
});
