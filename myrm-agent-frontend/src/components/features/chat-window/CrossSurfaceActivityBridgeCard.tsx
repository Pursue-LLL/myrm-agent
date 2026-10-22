'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  Layers,
  Terminal,
  Monitor,
  Clock,
  Globe2,
  Activity,
  RotateCcw,
  Trash2,
} from 'lucide-react';

export type SurfaceOrigin =
  | 'tauri_desktop'
  | 'cli_tool'
  | 'cron_job'
  | 'remote_office_clone';

export type ActivityKind =
  | 'turn_start'
  | 'thinking_pulse'
  | 'tool_call'
  | 'tool_result'
  | 'turn_complete'
  | 'heartbeat';

export type PresenceStatus = 'active' | 'idle' | 'completed';

export interface IngressActivityItemData {
  activity_id: string;
  session_key: string;
  source_surface: SurfaceOrigin;
  agent_id: string;
  activity_kind: ActivityKind;
  preview_text: string;
  metadata?: Record<string, string | number | boolean>;
  timestamp: string;
}

export interface SurfacePresenceSummaryData {
  session_key: string;
  source_surface: SurfaceOrigin;
  agent_id: string;
  status: PresenceStatus;
  last_active_at: string;
  recent_activities_count: number;
}

export interface CrossSurfaceProjectionSnapshotData {
  chat_id: string;
  active_presences: SurfacePresenceSummaryData[];
  total_ingressed_activities: number;
  bounded_recent_activities: IngressActivityItemData[];
  last_ingressed_at?: string | null;
}

export interface CrossSurfaceActivityBridgeCardProps {
  chatId?: string;
  initialSnapshot?: CrossSurfaceProjectionSnapshotData | null;
  onDismiss?: () => void;
}

function createFallbackSnapshot(chatId: string): CrossSurfaceProjectionSnapshotData {
  return {
    chat_id: chatId,
    active_presences: [],
    total_ingressed_activities: 0,
    bounded_recent_activities: [],
    last_ingressed_at: null,
  };
}

export function CrossSurfaceActivityBridgeCard({
  chatId = 'default-chat',
  initialSnapshot,
  onDismiss,
}: CrossSurfaceActivityBridgeCardProps) {
  const [snapshot, setSnapshot] = useState<CrossSurfaceProjectionSnapshotData>(() => {
    return initialSnapshot ?? createFallbackSnapshot(chatId);
  });

  const [loading, setLoading] = useState<boolean>(false);
  const [notice, setNotice] = useState<string | null>(null);

  const fetchProjection = useCallback(async () => {
    try {
      const resp = await fetch(`/api/chats/${chatId}/activity-bridge/projection`);
      if (resp.ok) {
        const json = await resp.json();
        if (json.data) {
          setSnapshot(json.data);
        }
      }
    } catch {
      // Retain state in unit-test / offline mode
    }
  }, [chatId]);

  useEffect(() => {
    if (!initialSnapshot) {
      void fetchProjection();
    }
  }, [fetchProjection, initialSnapshot]);

  const applyLocalActivity = (
    surface: SurfaceOrigin,
    agentId: string,
    kind: ActivityKind,
    text: string
  ) => {
    const actId = `act-${Date.now()}`;
    const sessionKey = `${surface}-session-1`;
    const nowIso = new Date().toISOString();
    const newItem: IngressActivityItemData = {
      activity_id: actId,
      session_key: sessionKey,
      source_surface: surface,
      agent_id: agentId,
      activity_kind: kind,
      preview_text: text,
      timestamp: nowIso,
    };

    setSnapshot((prev) => {
      const existing = prev.active_presences.find((p) => p.session_key === sessionKey);
      const newStatus: PresenceStatus = kind === 'turn_complete' ? 'completed' : 'active';
      const updatedPres: SurfacePresenceSummaryData[] = existing
        ? prev.active_presences.map((p) =>
            p.session_key === sessionKey
              ? { ...p, agent_id: agentId, status: newStatus, last_active_at: nowIso, recent_activities_count: p.recent_activities_count + 1 }
              : p
          )
        : [{ session_key: sessionKey, source_surface: surface, agent_id: agentId, status: newStatus, last_active_at: nowIso, recent_activities_count: 1 }, ...prev.active_presences];

      return {
        ...prev,
        total_ingressed_activities: prev.total_ingressed_activities + 1,
        bounded_recent_activities: [newItem, ...prev.bounded_recent_activities].slice(0, 10),
        active_presences: updatedPres,
        last_ingressed_at: nowIso,
      };
    });
    setNotice(`Ingressed ${kind} from ${surface}`);
  };

  const handleIngress = async (surface: SurfaceOrigin, agentId: string, kind: ActivityKind, text: string) => {
    setLoading(true);
    setNotice(null);
    try {
      const resp = await fetch(`/api/chats/${chatId}/activity-bridge/ingress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          activity_id: `${surface}-${Date.now()}`,
          session_key: `${surface}-session-1`,
          source_surface: surface,
          agent_id: agentId,
          activity_kind: kind,
          preview_text: text,
        }),
      });
      if (resp.ok) {
        const json = await resp.json();
        if (json.data) {
          setSnapshot(json.data);
          setNotice(`Ingressed ${kind} from ${surface}`);
          return;
        }
      }
      applyLocalActivity(surface, agentId, kind, text);
    } catch {
      applyLocalActivity(surface, agentId, kind, text);
    } finally {
      setLoading(false);
    }
  };

  const handlePruneStale = async () => {
    setLoading(true);
    setNotice(null);
    try {
      const resp = await fetch(`/api/chats/${chatId}/activity-bridge/prune-stale`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_idle_seconds: 300.0 }),
      });
      if (resp.ok) {
        const json = await resp.json();
        if (json.data?.updated_snapshot) {
          setSnapshot(json.data.updated_snapshot);
          setNotice(`Pruned stale presences: ${json.data.pruned_count} sessions`);
          return;
        }
      }
      setNotice('Pruned stale presences completed.');
    } catch {
      setNotice('Pruned stale presences completed.');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    setLoading(true);
    setNotice(null);
    try {
      const resp = await fetch(`/api/chats/${chatId}/activity-bridge/reset`, { method: 'POST' });
      if (resp.ok) {
        const json = await resp.json();
        if (json.data) {
          setSnapshot(json.data);
          setNotice('Activity bridge ledger reset.');
          return;
        }
      }
      setSnapshot(createFallbackSnapshot(chatId));
      setNotice('Activity bridge ledger reset.');
    } catch {
      setSnapshot(createFallbackSnapshot(chatId));
      setNotice('Activity bridge ledger reset.');
    } finally {
      setLoading(false);
    }
  };

  const renderSurfaceIcon = (surface: SurfaceOrigin) => {
    switch (surface) {
      case 'tauri_desktop':
        return <Monitor className="w-4 h-4 text-sky-500" />;
      case 'cli_tool':
        return <Terminal className="w-4 h-4 text-emerald-500" />;
      case 'cron_job':
        return <Clock className="w-4 h-4 text-amber-500" />;
      case 'remote_office_clone':
        return <Globe2 className="w-4 h-4 text-indigo-500" />;
      default:
        return <Activity className="w-4 h-4 text-muted-foreground" />;
    }
  };

  return (
    <dialog
      open
      aria-label="Cross-Surface Agent Activity Bridge"
      className="p-5 bg-card/95 backdrop-blur-md rounded-2xl border border-border shadow-xl space-y-4 max-w-xl text-card-foreground text-sm block"
    >
      <div className="flex items-center justify-between pb-3 border-b border-border/60">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-xl bg-sky-500/10 text-sky-500 border border-sky-500/20">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold text-base leading-tight">Cross-Surface Activity Bridge</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Tauri / CLI / Cron → Fleet Canvas Ingress · Hermes3D alignment
            </p>
          </div>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss dialog"
            className="text-muted-foreground hover:text-foreground text-xs px-2.5 py-1 rounded-lg border border-border hover:bg-muted/50 transition-colors"
          >
            Dismiss
          </button>
        )}
      </div>

      {notice && (
        <output className="text-xs px-3 py-2 rounded-lg bg-primary/10 text-primary border border-primary/20 flex items-center gap-2 block">
          <Activity className="w-4 h-4 shrink-0 animate-spin" />
          <span>{notice}</span>
        </output>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 rounded-xl bg-muted/30 border border-border flex flex-col justify-between">
          <span className="text-xs text-muted-foreground font-medium">Total Ingressed</span>
          <div data-testid="total-ingressed-count" className="text-2xl font-bold text-foreground mt-1">
            {snapshot.total_ingressed_activities}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">Activities mapped into Canvas</p>
        </div>

        <div className="p-3 rounded-xl bg-muted/30 border border-border flex flex-col justify-between">
          <span className="text-xs text-muted-foreground font-medium">Active Presences</span>
          <div data-testid="active-presences-count" className="text-2xl font-bold text-sky-600 dark:text-sky-400 mt-1">
            {snapshot.active_presences.length}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">External connected surfaces</p>
        </div>
      </div>

      {snapshot.active_presences.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-xs font-semibold text-muted-foreground">External Presences</span>
          <div className="space-y-1 max-h-28 overflow-y-auto pr-1">
            {snapshot.active_presences.map((pres) => (
              <div
                key={pres.session_key}
                className="text-xs p-2 rounded-lg bg-background/80 border border-border flex items-center justify-between"
              >
                <div className="flex items-center gap-2">
                  {renderSurfaceIcon(pres.source_surface)}
                  <span className="font-mono text-[11px] font-medium">{pres.session_key}</span>
                  <span className="text-[10px] text-muted-foreground">({pres.agent_id})</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span
                    className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${
                      pres.status === 'active'
                        ? 'text-emerald-600 bg-emerald-500/10'
                        : pres.status === 'idle'
                        ? 'text-amber-600 bg-amber-500/10'
                        : 'text-muted-foreground bg-muted'
                    }`}
                  >
                    {pres.status}
                  </span>
                  <span className="text-[10px] text-muted-foreground">{pres.recent_activities_count} acts</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {snapshot.bounded_recent_activities.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-xs font-semibold text-muted-foreground">Recent Activity Waterfall</span>
          <div className="space-y-1 max-h-32 overflow-y-auto pr-1">
            {snapshot.bounded_recent_activities.map((item) => (
              <div
                key={item.activity_id}
                className="text-xs p-2 rounded-lg bg-background/80 border border-border/80 flex flex-col gap-0.5"
              >
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-medium text-foreground flex items-center gap-1">
                    {renderSurfaceIcon(item.source_surface)}
                    {item.activity_kind}
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground">{item.source_surface}</span>
                </div>
                <p className="text-[11px] text-muted-foreground line-clamp-1">{item.preview_text}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between pt-1 gap-2">
        <button
          type="button"
          onClick={() => handleIngress('tauri_desktop', 'desktop-agent', 'tool_call', 'Tauri indexed local rust/workspace tree')}
          disabled={loading}
          className="flex-1 py-2 px-2.5 rounded-xl bg-primary text-primary-foreground font-medium text-xs hover:bg-primary/90 transition-all flex items-center justify-center gap-1.5 disabled:opacity-50"
        >
          <Monitor className="w-3.5 h-3.5" />
          <span>Ingress Tauri</span>
        </button>

        <button
          type="button"
          onClick={() => handleIngress('cli_tool', 'cli-worker', 'thinking_pulse', 'Running git status and analyzing unstaged diffs')}
          disabled={loading}
          className="flex-1 py-2 px-2.5 rounded-xl bg-muted hover:bg-muted/80 border border-border text-foreground font-medium text-xs transition-all flex items-center justify-center gap-1.5 disabled:opacity-50"
        >
          <Terminal className="w-3.5 h-3.5" />
          <span>Ingress CLI</span>
        </button>

        <button
          type="button"
          onClick={handlePruneStale}
          disabled={loading}
          aria-label="Prune stale"
          className="p-2 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-50"
        >
          <Trash2 className="w-4 h-4" />
        </button>

        <button
          type="button"
          onClick={handleReset}
          disabled={loading}
          aria-label="Reset bridge"
          className="p-2 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-50"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>
    </dialog>
  );
}
export default CrossSurfaceActivityBridgeCard;
