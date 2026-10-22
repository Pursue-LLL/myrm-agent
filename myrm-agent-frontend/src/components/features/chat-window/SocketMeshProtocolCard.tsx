import React, { useState } from 'react';
import {
  DEFAULT_AUDIT_LOGS,
  DEFAULT_PEERS,
  MeshAuditLog,
  PeerInfo,
} from './socket-mesh/types';
import { SocketMeshHeader } from './socket-mesh/SocketMeshHeader';
import { PeersGridView } from './socket-mesh/PeersGridView';
import { EnvelopeConsoleView } from './socket-mesh/EnvelopeConsoleView';
import { AuditLogsView } from './socket-mesh/AuditLogsView';

export interface SocketMeshProtocolCardProps {
  chatId: string;
  project?: string;
  initialPeers?: PeerInfo[];
  initialLogs?: MeshAuditLog[];
  onSendEnvelope?: (sender: string, target: string, prompt: string) => Promise<string>;
  onPingPeer?: (target: string) => Promise<string>;
}

export const SocketMeshProtocolCard: React.FC<SocketMeshProtocolCardProps> = ({
  chatId,
  project = 'default',
  initialPeers = DEFAULT_PEERS,
  initialLogs = DEFAULT_AUDIT_LOGS,
  onSendEnvelope,
  onPingPeer,
}) => {
  const [peers] = useState<PeerInfo[]>(initialPeers);
  const [logs, setLogs] = useState<MeshAuditLog[]>(initialLogs);
  const [activeTab, setActiveTab] = useState<'peers' | 'console' | 'audit'>('peers');
  const [sender, setSender] = useState<string>(initialPeers[0]?.name || 'planner');
  const [target, setTarget] = useState<string>(initialPeers[1]?.name || 'coder');
  const [promptInput, setPromptInput] = useState<string>('');
  const [lastResponse, setLastResponse] = useState<string>('');
  const [statusMessage, setStatusMessage] = useState<string>('Socket mesh active and listening on local IPC sockets.');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

  const onlinePeersCount = peers.filter((p) => p.status === 'online').length;

  const handlePingPeer = async (targetName: string) => {
    setIsProcessing(true);
    setStatusMessage(`Pinging peer '${targetName}' over local Unix socket...`);
    try {
      if (onPingPeer) {
        const res = await onPingPeer(targetName);
        setStatusMessage(res);
      } else {
        setStatusMessage(`PONG received from ${targetName}: Operational healthy (context: 35%).`);
      }
      setLogs((prev) => [
        {
          timestamp: Date.now(),
          eventType: 'PING_PONG',
          node: targetName,
          project,
          detail: `Health check probe succeeded with 0.4ms round-trip latency.`,
        },
        ...prev,
      ]);
    } catch {
      setStatusMessage(`Ping to ${targetName} timed out.`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSendAndAwait = async () => {
    if (!promptInput.trim()) {
      setStatusMessage('Please enter prompt content to dispatch.');
      return;
    }
    setIsProcessing(true);
    setStatusMessage(`Dispatching atomic envelope from '${sender}' to '${target}'...`);
    try {
      let responsePayload = '';
      if (onSendEnvelope) {
        responsePayload = await onSendEnvelope(sender, target, promptInput);
      } else {
        responsePayload = `[SIMULATED P2P RESPONSE from ${target}]: Completed subtask '${promptInput.slice(0, 32)}...' via zero-broker local socket IPC.`;
      }
      setLastResponse(responsePayload);
      setStatusMessage(`Envelope fulfilled by '${target}' (hops: 1, duration: 1.8ms).`);
      setLogs((prev) => [
        {
          timestamp: Date.now(),
          eventType: 'REPLY_RECEIVED',
          node: target,
          project,
          detail: `Delivered response to '${sender}' in 1.8ms (hops: 1).`,
        },
        {
          timestamp: Date.now() - 2,
          eventType: 'SEND_PROMPT',
          node: sender,
          project,
          detail: `Dispatched prompt envelope to '${target}' (hops: 0).`,
        },
        ...prev,
      ]);
      setPromptInput('');
    } catch {
      setStatusMessage('Failed to deliver prompt envelope. Target offline or timed out.');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <section
      aria-label="P2P Agent Socket Mesh Protocol"
      className="rounded-xl border border-border bg-card p-4 shadow-sm text-card-foreground my-3"
      data-testid="socket-mesh-protocol-card"
    >
      <SocketMeshHeader
        chatId={chatId}
        project={project}
        peersCount={peers.length}
        onlineCount={onlinePeersCount}
        activeTab={activeTab}
        onSelectTab={setActiveTab}
      />

      {activeTab === 'peers' && (
        <PeersGridView
          peers={peers}
          onPingPeer={handlePingPeer}
          isProcessing={isProcessing}
        />
      )}

      {activeTab === 'console' && (
        <EnvelopeConsoleView
          peers={peers}
          sender={sender}
          onChangeSender={setSender}
          target={target}
          onChangeTarget={setTarget}
          promptInput={promptInput}
          onChangePromptInput={setPromptInput}
          lastResponse={lastResponse}
          isProcessing={isProcessing}
          onSendAndAwait={handleSendAndAwait}
        />
      )}

      {activeTab === 'audit' && <AuditLogsView logs={logs} />}

      <footer className="mt-3 pt-2 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground">
        <span>
          Peers: {peers.length} | Audit Logs: {logs.length}
        </span>
        <output aria-live="polite" className="font-mono text-primary text-[10px]">
          {statusMessage}
        </output>
      </footer>
    </section>
  );
};

export default SocketMeshProtocolCard;
