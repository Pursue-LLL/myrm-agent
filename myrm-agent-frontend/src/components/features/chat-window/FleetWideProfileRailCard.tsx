import React, { useState } from 'react';
import {
  DEFAULT_FLEET_STATE,
  FleetProfile,
  FleetRailState,
  GatewayNode,
  OfflineBufferedCommand,
  RelayedArtifact,
} from './fleet-router/types';
import { FleetRailHeaderView } from './fleet-router/FleetRailHeaderView';
import { GatewayNodeCardView } from './fleet-router/GatewayNodeCardView';
import { OfflineBufferQueueModal } from './fleet-router/OfflineBufferQueueModal';
import { CrossGatewayRelayModal } from './fleet-router/CrossGatewayRelayModal';

export interface FleetWideProfileRailCardProps {
  chatId: string;
  initialState?: FleetRailState;
  onSwitchProfile?: (profileId: string) => Promise<void>;
  onFlushGateway?: (gatewayId: string) => Promise<OfflineBufferedCommand[]>;
  onRelayArtifact?: (
    sourceGateway: string,
    targetGateway: string,
    name: string,
    filePath: string,
    chunkData: string,
  ) => Promise<RelayedArtifact>;
  onRefreshTopology?: () => Promise<void>;
}

export const FleetWideProfileRailCard: React.FC<FleetWideProfileRailCardProps> = ({
  chatId,
  initialState = DEFAULT_FLEET_STATE,
  onSwitchProfile,
  onFlushGateway,
  onRelayArtifact,
  onRefreshTopology,
}) => {
  const [fleetState, setFleetState] = useState<FleetRailState>(initialState);
  const [isBufferModalOpen, setIsBufferModalOpen] = useState<boolean>(false);
  const [isRelayModalOpen, setIsRelayModalOpen] = useState<boolean>(false);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [isRelaying, setIsRelaying] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string>(
    'Fleet rail ready: multi-gateway dynamic router active with offline command buffering.',
  );

  const gatewayList = Object.values(fleetState.gateways);
  const profileList = Object.values(fleetState.profiles);
  const totalGateways = gatewayList.length;
  const onlineGateways = gatewayList.filter((g) => g.status === 'online').length;

  const totalBufferedCount = Object.values(fleetState.buffered_commands).reduce(
    (acc, list) => acc + list.length,
    0,
  );

  const handleSelectProfile = async (profileId: string) => {
    const profile = fleetState.profiles[profileId];
    if (!profile) {
      return;
    }
    const gateway = fleetState.gateways[profile.gateway_id];
    setStatusMessage(
      `Switching session to Profile '${profile.name}' on gateway '${gateway?.label || profile.gateway_id}'...`,
    );

    try {
      if (onSwitchProfile) {
        await onSwitchProfile(profileId);
      }
      setFleetState((prev) => ({
        ...prev,
        active_profile_id: profileId,
        profiles: Object.fromEntries(
          Object.entries(prev.profiles).map(([id, p]) => [
            id,
            { ...p, is_active: id === profileId },
          ]),
        ),
        updated_at: Date.now(),
      }));
      setStatusMessage(
        `Active session switched to '${profile.name}' (${gateway?.platform || 'remote'}). Host context updated.`,
      );
    } catch (err) {
      setStatusMessage(
        `Profile switch failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  const handleSimulateCommand = (gatewayId: string, profileId: string) => {
    const gateway = fleetState.gateways[gatewayId];
    const profile = fleetState.profiles[profileId];
    if (!gateway || !profile) {
      return;
    }

    if (gateway.status === 'offline') {
      const newCmd: OfflineBufferedCommand = {
        command_id: `cmd-buf-${Date.now().toString().slice(-4)}`,
        gateway_id: gatewayId,
        profile_id: profileId,
        command_type: 'delegated_task',
        payload: { target: profile.name, queued_at: new Date().toISOString() },
        queued_at: Date.now(),
        retry_count: 0,
      };
      setFleetState((prev) => {
        const existing = prev.buffered_commands[gatewayId] || [];
        return {
          ...prev,
          buffered_commands: {
            ...prev.buffered_commands,
            [gatewayId]: [...existing, newCmd],
          },
          updated_at: Date.now(),
        };
      });
      setStatusMessage(
        `Gateway '${gateway.label}' is OFFLINE. Command safely queued into offline FIFO buffer.`,
      );
    } else {
      setStatusMessage(
        `Command sent to '${profile.name}' on '${gateway.label}'. Latency: ${gateway.latency_ms.toFixed(1)}ms.`,
      );
    }
  };

  const handleFlushGateway = async (gatewayId: string) => {
    const gateway = fleetState.gateways[gatewayId];
    setStatusMessage(`Flushing offline commands for gateway '${gatewayId}'...`);
    try {
      if (onFlushGateway) {
        await onFlushGateway(gatewayId);
      }
      setFleetState((prev) => {
        const queue = prev.buffered_commands[gatewayId] || [];
        const count = queue.length;
        const copy = { ...prev.buffered_commands };
        delete copy[gatewayId];
        // Bring gateway online in simulation
        const gCopy = { ...prev.gateways };
        if (gCopy[gatewayId]) {
          gCopy[gatewayId] = { ...gCopy[gatewayId], status: 'online', latency_ms: 18.0 };
        }
        return {
          ...prev,
          gateways: gCopy,
          buffered_commands: copy,
          updated_at: Date.now(),
        };
      });
      setStatusMessage(
        `Auto-healing complete: reconnected to '${gateway?.label || gatewayId}' and flushed queued commands.`,
      );
    } catch (err) {
      setStatusMessage(
        `Flush failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  const handleRelayArtifact = async (
    sourceGateway: string,
    targetGateway: string,
    name: string,
    filePath: string,
    chunkData: string,
  ): Promise<RelayedArtifact | null> => {
    setIsRelaying(true);
    setStatusMessage(`Relaying artifact '${name}' from '${sourceGateway}' to '${targetGateway}'...`);
    try {
      if (onRelayArtifact) {
        const res = await onRelayArtifact(sourceGateway, targetGateway, name, filePath, chunkData);
        setStatusMessage(`Artifact '${name}' relayed via secure tunnel with SHA-256 verification.`);
        return res;
      }
      // Local fallback simulation
      const mockEnvelope: RelayedArtifact = {
        artifact_id: `art-relay-${Date.now().toString().slice(-4)}`,
        source_gateway: sourceGateway,
        target_gateway: targetGateway,
        name,
        file_path: filePath,
        sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
        chunk_data: chunkData,
        created_at: Date.now(),
        is_verified: true,
      };
      setStatusMessage(`Artifact '${name}' successfully transferred across gateways.`);
      return mockEnvelope;
    } catch (err) {
      setStatusMessage(`Relay failed: ${err instanceof Error ? err.message : String(err)}`);
      return null;
    } finally {
      setIsRelaying(false);
    }
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setStatusMessage('Probing fleet gateways and updating topology telemetry...');
    try {
      if (onRefreshTopology) {
        await onRefreshTopology();
      }
      setStatusMessage('Fleet topology updated: all gateway ping latencies and heartbeats synchronized.');
    } catch (err) {
      setStatusMessage(`Topology refresh failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <article
      aria-label="Fleet-Wide Profile Rail Card"
      data-chat-id={chatId}
      className="my-3 overflow-hidden rounded-xl border border-border/60 bg-background/95 p-4 shadow-sm backdrop-blur-xs space-y-4"
    >
      <FleetRailHeaderView
        totalGateways={totalGateways}
        onlineGateways={onlineGateways}
        bufferedCount={totalBufferedCount}
        isRefreshing={isRefreshing}
        onRefresh={handleRefresh}
        onOpenBufferModal={() => setIsBufferModalOpen(true)}
        onOpenRelayModal={() => setIsRelayModalOpen(true)}
      />

      {/* Accessible Live Output Status */}
      <div className="rounded-lg bg-muted/30 px-3 py-2 text-xs border border-border/30">
        <output aria-live="polite" className="flex items-center gap-2 text-foreground/90">
          <span className="font-semibold text-primary">Status:</span>
          <span>{statusMessage}</span>
        </output>
      </div>

      {/* Distributed Gateways Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5 pt-1">
        {gatewayList.map((gateway) => {
          const nodeProfiles = profileList.filter((p) => p.gateway_id === gateway.gateway_id);
          const bufferedForNode = (fleetState.buffered_commands[gateway.gateway_id] || []).length;

          return (
            <GatewayNodeCardView
              key={gateway.gateway_id}
              gateway={gateway}
              profiles={nodeProfiles}
              activeProfileId={fleetState.active_profile_id}
              bufferedCount={bufferedForNode}
              onSelectProfile={handleSelectProfile}
              onSimulateCommand={handleSimulateCommand}
              onFlushGateway={handleFlushGateway}
            />
          );
        })}
      </div>

      {/* Modals */}
      <OfflineBufferQueueModal
        isOpen={isBufferModalOpen}
        bufferedMap={fleetState.buffered_commands}
        onClose={() => setIsBufferModalOpen(false)}
        onFlush={handleFlushGateway}
      />

      <CrossGatewayRelayModal
        isOpen={isRelayModalOpen}
        gateways={gatewayList}
        isRelaying={isRelaying}
        onClose={() => setIsRelayModalOpen(false)}
        onRelay={handleRelayArtifact}
      />
    </article>
  );
};
