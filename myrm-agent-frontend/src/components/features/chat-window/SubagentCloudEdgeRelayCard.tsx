import React, { useState, useMemo } from 'react';
import {
  Cloud,
  Laptop,
  Layers,
  ArrowRightLeft,
  ShieldAlert,
  PlusCircle,
  X,
  ChevronRight,
  ChevronDown,
  CheckCircle2,
  Clock,
  Sparkles,
} from 'lucide-react';

export type RelayNodeRole = 'local_sandbox' | 'cloud_sandbox' | 'edge_gateway';
export type NetworkEgressStatus = 'direct_ok' | 'relay_requested' | 'relay_completed' | 'relay_failed';

export interface ArtifactChunkItem {
  chunk_id: string;
  artifact_id: string;
  version: number;
  author_role: RelayNodeRole;
  content_delta: string;
  row_count: number;
  timestamp: string;
  checksum: string;
}

export interface HybridArtifactItem {
  artifact_id: string;
  name: string;
  current_version: number;
  total_rows: number;
  chunks: ArtifactChunkItem[];
  last_synced_at: string;
  is_divergent: boolean;
}

export interface EgressRelayItem {
  relay_id: string;
  target_url: string;
  intent: string;
  source_node: RelayNodeRole;
  status: NetworkEgressStatus;
  status_code: number;
  latency_ms: number;
  extracted_data_preview: string;
  error_message?: string;
}

export interface SubagentCloudEdgeRelayCardProps {
  chatId?: string;
  onDismiss?: () => void;
  onSyncComplete?: (artifactId: string, newVersion: number) => void;
}

const INITIAL_ARTIFACTS: HybridArtifactItem[] = [
  {
    artifact_id: 'art-sales-q3',
    name: 'q3_ecommerce_transactions.csv',
    current_version: 2,
    total_rows: 154,
    last_synced_at: '2m ago',
    is_divergent: false,
    chunks: [
      {
        chunk_id: 'chunk-init-01',
        artifact_id: 'art-sales-q3',
        version: 1,
        author_role: 'local_sandbox',
        content_delta: 'order_id,user_id,amount,currency\nORD-101,USR-41,120.50,USD',
        row_count: 50,
        timestamp: '14:20:00',
        checksum: 'a89c2f10d4',
      },
      {
        chunk_id: 'chunk-cloud-02',
        artifact_id: 'art-sales-q3',
        version: 2,
        author_role: 'cloud_sandbox',
        content_delta: 'ORD-102,USR-88,430.00,USD\nORD-103,USR-19,89.00,USD',
        row_count: 104,
        timestamp: '14:28:15',
        checksum: 'b33e4198c2',
      },
    ],
  },
  {
    artifact_id: 'art-sys-metrics',
    name: 'cluster_telemetry_batch.jsonl',
    current_version: 1,
    total_rows: 42,
    last_synced_at: '5m ago',
    is_divergent: false,
    chunks: [
      {
        chunk_id: 'chunk-init-02',
        artifact_id: 'art-sys-metrics',
        version: 1,
        author_role: 'local_sandbox',
        content_delta: '{"host":"node-alpha","cpu_pct":44.2,"mem_pct":68.1}',
        row_count: 42,
        timestamp: '14:15:30',
        checksum: 'c45b78912e',
      },
    ],
  },
];

const INITIAL_RELAYS: EgressRelayItem[] = [
  {
    relay_id: 'relay-ext-01',
    target_url: 'https://api.github.com/repos/org/packages',
    intent: 'Crawl release metadata from network-restricted cloud node',
    source_node: 'cloud_sandbox',
    status: 'relay_completed',
    status_code: 200,
    latency_ms: 142.6,
    extracted_data_preview: '{"tag_name": "v3.8.1", "assets_count": 4}',
  },
  {
    relay_id: 'relay-ext-02',
    target_url: 'https://docs.enterprise.internal/spec',
    intent: 'Verify compliance checklist on local corporate intranet',
    source_node: 'cloud_sandbox',
    status: 'relay_completed',
    status_code: 200,
    latency_ms: 88.4,
    extracted_data_preview: '{"status": "compliant", "audit_score": 98}',
  },
];

export const SubagentCloudEdgeRelayCard: React.FC<SubagentCloudEdgeRelayCardProps> = ({
  chatId,
  onDismiss,
  onSyncComplete,
}) => {
  const [activeTab, setActiveTab] = useState<'artifacts' | 'relays'>('artifacts');
  const [artifacts, setArtifacts] = useState<HybridArtifactItem[]>(INITIAL_ARTIFACTS);
  const [relays, setRelays] = useState<EgressRelayItem[]>(INITIAL_RELAYS);
  const [expandedArtifactId, setExpandedArtifactId] = useState<string | null>('art-sales-q3');
  const [isAppending, setIsAppending] = useState<boolean>(false);
  const [ssrfGuardCount, setSsrfGuardCount] = useState<number>(3);

  const stats = useMemo(() => {
    const totalRows = artifacts.reduce((acc, a) => acc + a.total_rows, 0);
    const totalChunks = artifacts.reduce((acc, a) => acc + a.chunks.length, 0);
    const completedRelays = relays.filter((r) => r.status === 'relay_completed').length;
    return { totalRows, totalChunks, completedRelays };
  }, [artifacts, relays]);

  const handleSimulateCloudAppend = (targetId: string): void => {
    setIsAppending(true);
    setTimeout(() => {
      setArtifacts((prev) =>
        prev.map((art) => {
          if (art.artifact_id !== targetId) {
            return art;
          }
          const nextVersion = art.current_version + 1;
          const addedRows = 25;
          const newChunk: ArtifactChunkItem = {
            chunk_id: `chunk-cloud-${Date.now().toString(36)}`,
            artifact_id: art.artifact_id,
            version: nextVersion,
            author_role: 'cloud_sandbox',
            content_delta: `ORD-${nextVersion}01,USR-${nextVersion}9,210.00,USD (cloud append)`,
            row_count: addedRows,
            timestamp: new Date().toLocaleTimeString(),
            checksum: Math.random().toString(16).substring(2, 12),
          };
          return {
            ...art,
            current_version: nextVersion,
            total_rows: art.total_rows + addedRows,
            last_synced_at: 'Just now',
            chunks: [...art.chunks, newChunk],
          };
        })
      );
      setIsAppending(false);
      onSyncComplete?.(targetId, (artifacts.find((a) => a.artifact_id === targetId)?.current_version ?? 1) + 1);
    }, 400);
  };

  const handleSimulateSsrfProbe = (): void => {
    setSsrfGuardCount((prev) => prev + 1);
    const blockedRelay: EgressRelayItem = {
      relay_id: `relay-block-${Date.now().toString(36)}`,
      target_url: 'http://169.254.169.254/latest/meta-data',
      intent: 'Blocked SSRF instance metadata probe',
      source_node: 'cloud_sandbox',
      status: 'relay_failed',
      status_code: 400,
      latency_ms: 1.2,
      extracted_data_preview: '',
      error_message: 'SSRF policy violation: Target host disallowed for egress relay',
    };
    setRelays((prev) => [blockedRelay, ...prev]);
  };

  return (
    <div
      data-testid="subagent-cloud-edge-relay-card"
      className="rounded-xl border border-border/80 bg-card/95 p-4 text-card-foreground shadow-lg backdrop-blur-md transition-all duration-200"
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-border/60">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500">
            <ArrowRightLeft className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold tracking-tight">Hybrid Cloud-Edge Sandbox Relay</h3>
              <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                Item 58 Active
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Bidirectional Append-Only CAS Synchronization & SSRF-Guarded Local Egress
              {chatId ? ` • Chat ${chatId}` : ''}
            </p>
          </div>
        </div>

        {onDismiss && (
          <button
            type="button"
            data-testid="relay-card-dismiss"
            onClick={onDismiss}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted/70 hover:text-foreground transition-colors"
            title="Dismiss card"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-4 gap-2.5 py-3">
        <div className="rounded-lg border border-border/50 bg-background/50 p-2.5">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Layers className="h-3.5 w-3.5 text-blue-500" />
            <span>Artifacts</span>
          </div>
          <div className="mt-1 text-base font-semibold">{artifacts.length}</div>
        </div>
        <div className="rounded-lg border border-border/50 bg-background/50 p-2.5">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5 text-emerald-500" />
            <span>Synced Rows</span>
          </div>
          <div className="mt-1 text-base font-semibold text-emerald-600 dark:text-emerald-400">
            {stats.totalRows}
          </div>
        </div>
        <div className="rounded-lg border border-border/50 bg-background/50 p-2.5">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Laptop className="h-3.5 w-3.5 text-purple-500" />
            <span>Relay Fetches</span>
          </div>
          <div className="mt-1 text-base font-semibold">{stats.completedRelays} ok</div>
        </div>
        <div className="rounded-lg border border-border/50 bg-background/50 p-2.5">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
            <span>SSRF Defenses</span>
          </div>
          <div className="mt-1 text-base font-semibold text-amber-600 dark:text-amber-400">
            {ssrfGuardCount} blocked
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex items-center justify-between border-b border-border/60 pb-2 mb-3">
        <div className="flex gap-2">
          <button
            type="button"
            data-testid="tab-artifacts"
            onClick={() => setActiveTab('artifacts')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
              activeTab === 'artifacts'
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-muted/60'
            }`}
          >
            CAS Artifact Chains ({artifacts.length})
          </button>
          <button
            type="button"
            data-testid="tab-relays"
            onClick={() => setActiveTab('relays')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
              activeTab === 'relays'
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-muted/60'
            }`}
          >
            Egress Relay Traffic ({relays.length})
          </button>
        </div>

        <div className="flex items-center gap-2">
          {activeTab === 'artifacts' && expandedArtifactId && (
            <button
              type="button"
              data-testid="btn-cloud-append"
              onClick={() => handleSimulateCloudAppend(expandedArtifactId)}
              disabled={isAppending}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20 disabled:opacity-50 transition-colors"
            >
              <PlusCircle className="h-3.5 w-3.5" />
              <span>{isAppending ? 'Syncing...' : 'Simulate Cloud Append'}</span>
            </button>
          )}
          {activeTab === 'relays' && (
            <button
              type="button"
              data-testid="btn-test-ssrf"
              onClick={handleSimulateSsrfProbe}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-amber-500/10 text-amber-600 hover:bg-amber-500/20 transition-colors"
            >
              <ShieldAlert className="h-3.5 w-3.5" />
              <span>Trigger SSRF Guard</span>
            </button>
          )}
        </div>
      </div>

      {/* Tab 1: Shared Artifacts & CAS Chain */}
      {activeTab === 'artifacts' && (
        <div className="space-y-2.5">
          {artifacts.map((art) => {
            const isExpanded = expandedArtifactId === art.artifact_id;
            return (
              <div
                key={art.artifact_id}
                data-testid={`artifact-item-${art.artifact_id}`}
                className="rounded-lg border border-border/60 bg-muted/20 p-2.5 transition-all"
              >
                <button
                  type="button"
                  className="w-full flex items-center justify-between cursor-pointer text-left bg-transparent border-0 p-0"
                  onClick={() => setExpandedArtifactId(isExpanded ? null : art.artifact_id)}
                >
                  <div className="flex items-center gap-2">
                    {isExpanded ? (
                      <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    )}
                    <span className="text-xs font-semibold">{art.name}</span>
                    <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-mono text-primary">
                      v{art.current_version}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      ({art.total_rows} rows, {art.chunks.length} chunks)
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    <span>{art.last_synced_at}</span>
                  </div>
                </button>

                {/* Expanded Chunk Timeline */}
                {isExpanded && (
                  <div className="mt-2.5 pl-5 border-l-2 border-primary/20 space-y-2">
                    {art.chunks.map((chk) => (
                      <div
                        key={chk.chunk_id}
                        className="rounded-md border border-border/40 bg-background/60 p-2 text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5">
                            {chk.author_role === 'cloud_sandbox' ? (
                              <span className="flex items-center gap-1 rounded bg-blue-500/10 px-1.5 py-0.5 text-[10px] text-blue-600 font-medium">
                                <Cloud className="h-3 w-3" /> Cloud Sandbox
                              </span>
                            ) : (
                              <span className="flex items-center gap-1 rounded bg-purple-500/10 px-1.5 py-0.5 text-[10px] text-purple-600 font-medium">
                                <Laptop className="h-3 w-3" /> Local Sandbox
                              </span>
                            )}
                            <span className="font-mono text-[10px] text-muted-foreground">
                              {chk.chunk_id} • v{chk.version}
                            </span>
                          </div>
                          <span className="font-mono text-[10px] text-muted-foreground">
                            +{chk.row_count} rows • {chk.checksum}
                          </span>
                        </div>
                        <div className="mt-1 text-[11px] font-mono text-muted-foreground truncate bg-muted/40 px-1.5 py-0.5 rounded">
                          {chk.content_delta}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Tab 2: Egress Relays */}
      {activeTab === 'relays' && (
        <div className="space-y-2">
          {relays.map((rel) => {
            const isSuccess = rel.status === 'relay_completed';
            return (
              <div
                key={rel.relay_id}
                data-testid={`relay-item-${rel.relay_id}`}
                className="rounded-lg border border-border/60 bg-muted/20 p-2.5 text-xs flex items-center justify-between"
              >
                <div className="space-y-1 max-w-[70%]">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-medium text-foreground">{rel.target_url}</span>
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {rel.source_node}
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground truncate">{rel.intent}</p>
                  {rel.extracted_data_preview && (
                    <div className="font-mono text-[10px] text-muted-foreground bg-muted/40 px-1.5 py-0.5 rounded truncate">
                      {rel.extracted_data_preview}
                    </div>
                  )}
                  {rel.error_message && (
                    <div className="text-[10px] text-rose-500 font-medium">
                      {rel.error_message}
                    </div>
                  )}
                </div>

                <div className="flex flex-col items-end gap-1">
                  {isSuccess ? (
                    <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      {rel.status_code} OK
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-[11px] font-medium text-rose-600 dark:text-rose-400">
                      <ShieldAlert className="h-3.5 w-3.5" />
                      Blocked ({rel.status_code})
                    </span>
                  )}
                  <span className="text-[10px] font-mono text-muted-foreground">
                    {rel.latency_ms.toFixed(1)} ms
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
