'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  ShieldCheck,
  Zap,
  Activity,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  CheckCircle2,
  XCircle,
  Eye,
} from 'lucide-react';

export type ZeroTokenEventSource =
  | 'runtime_sse'
  | 'gateway_webhook'
  | 'liveness_heartbeat'
  | 'kanban_webhook';

export type ZeroTokenEventType =
  | 'subagent_spawned'
  | 'subagent_status_update'
  | 'subagent_terminated'
  | 'tool_start'
  | 'tool_finish'
  | 'node_heartbeat'
  | 'kanban_transition';

export interface VizCallAuditRecord {
  caller_surface: string;
  prompt_chars: number;
  is_violation: boolean;
  intercepted_reason: string;
  timestamp: string;
}

export interface ZeroTokenAuditSnapshot {
  chat_id: string;
  total_events_mirrored: number;
  total_tokens_spent: number;
  saved_tokens_estimated: number;
  violations_intercepted: number;
  is_compliant: boolean;
  recent_violations: VizCallAuditRecord[];
  last_mirrored_at?: string | null;
}

export interface ZeroTokenContractCardProps {
  chatId?: string;
  initialSnapshot?: ZeroTokenAuditSnapshot | null;
  onDismiss?: () => void;
}

function createFallbackSnapshot(chatId: string): ZeroTokenAuditSnapshot {
  return {
    chat_id: chatId,
    total_events_mirrored: 0,
    total_tokens_spent: 0,
    saved_tokens_estimated: 0,
    violations_intercepted: 0,
    is_compliant: true,
    recent_violations: [],
    last_mirrored_at: null,
  };
}

export function ZeroTokenContractCard({
  chatId = 'default-chat',
  initialSnapshot,
  onDismiss,
}: ZeroTokenContractCardProps) {
  const [snapshot, setSnapshot] = useState<ZeroTokenAuditSnapshot>(() => {
    return initialSnapshot ?? createFallbackSnapshot(chatId);
  });

  const [loading, setLoading] = useState<boolean>(false);
  const [notice, setNotice] = useState<string | null>(null);

  const fetchAuditReport = useCallback(async () => {
    try {
      const resp = await fetch(`/api/chats/${chatId}/zero-token/audit`);
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
      void fetchAuditReport();
    }
  }, [fetchAuditReport, initialSnapshot]);

  const applyLocalMirrorIncrement = () => {
    setSnapshot((prev) => {
      const newTotal = prev.total_events_mirrored + 1;
      return {
        ...prev,
        total_events_mirrored: newTotal,
        total_tokens_spent: 0,
        saved_tokens_estimated: newTotal * 150,
        last_mirrored_at: new Date().toISOString(),
      };
    });
    setNotice('Runtime event mirrored locally: 0 tokens spent.');
  };

  const handleSimulateEvent = async () => {
    setLoading(true);
    setNotice(null);
    try {
      const payload = {
        event_id: `evt-${Date.now()}`,
        source: 'runtime_sse' as ZeroTokenEventSource,
        event_type: 'subagent_status_update' as ZeroTokenEventType,
        agent_id: 'scout-worker',
        payload: { progress: 80, step: 'analyzing_ast' },
      };

      const resp = await fetch(`/api/chats/${chatId}/zero-token/mirror`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (resp.ok) {
        const json = await resp.json();
        if (json.data) {
          setSnapshot(json.data);
          setNotice('Runtime event mirrored into Canvas with 0 tokens spent.');
          return;
        }
      }
      applyLocalMirrorIncrement();
    } catch {
      applyLocalMirrorIncrement();
    } finally {
      setLoading(false);
    }
  };

  const applyLocalViolationIntercept = () => {
    const mockViolation: VizCallAuditRecord = {
      caller_surface: 'fleet_canvas',
      prompt_chars: 48,
      is_violation: true,
      intercepted_reason: "ZeroTokenContractViolation on surface 'fleet_canvas': Attempted LLM call.",
      timestamp: new Date().toISOString(),
    };
    setSnapshot((prev) => ({
      ...prev,
      violations_intercepted: prev.violations_intercepted + 1,
      is_compliant: false,
      recent_violations: [mockViolation, ...prev.recent_violations].slice(0, 5),
    }));
    setNotice('Doctor intercepted unauthorized LLM call from fleet_canvas!');
  };

  const handleSimulateDoctorViolation = async () => {
    setLoading(true);
    setNotice(null);
    try {
      const resp = await fetch(`/api/chats/${chatId}/zero-token/simulate-violation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          caller_surface: 'fleet_canvas',
          test_prompt: 'Generate 3D avatar facial expression and mood animation',
        }),
      });

      if (resp.ok) {
        const json = await resp.json();
        if (json.data?.updated_audit) {
          setSnapshot(json.data.updated_audit);
          setNotice('Doctor intercepted unauthorized LLM call from fleet_canvas!');
          return;
        }
      }
      applyLocalViolationIntercept();
    } catch {
      applyLocalViolationIntercept();
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    setLoading(true);
    setNotice(null);
    try {
      const resp = await fetch(`/api/chats/${chatId}/zero-token/reset`, { method: 'POST' });
      if (resp.ok) {
        const json = await resp.json();
        if (json.data) {
          setSnapshot(json.data);
          setNotice('Audit ledger reset.');
          return;
        }
      }
      setSnapshot(createFallbackSnapshot(chatId));
      setNotice('Audit ledger reset.');
    } catch {
      setSnapshot(createFallbackSnapshot(chatId));
      setNotice('Audit ledger reset.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <dialog
      open
      aria-label="Zero-Token Visualization Contract"
      className="p-5 bg-card/95 backdrop-blur-md rounded-2xl border border-border shadow-xl space-y-4 max-w-xl text-card-foreground text-sm block"
    >
      <div className="flex items-center justify-between pb-3 border-b border-border/60">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold text-base leading-tight">Zero-Token Visualization Contract</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Deterministic runtime event projection · Hermes3D alignment
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
        <div className="p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="flex items-center gap-1 font-medium">
              <Zap className="w-3.5 h-3.5 text-emerald-500" /> UI Tokens Spent
            </span>
            <span className="text-[10px] uppercase font-bold text-emerald-600 bg-emerald-500/10 px-1.5 py-0.5 rounded">
              Contract
            </span>
          </div>
          <div
            data-testid="ui-tokens-spent"
            className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-2"
          >
            {snapshot.total_tokens_spent}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">Zero LLM tokens used for rendering</p>
        </div>

        <div className="p-3 rounded-xl bg-muted/30 border border-border flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="flex items-center gap-1 font-medium">
              <Sparkles className="w-3.5 h-3.5 text-amber-500" /> Tokens Saved
            </span>
            <span className="text-[10px] text-muted-foreground">Estimated</span>
          </div>
          <div data-testid="tokens-saved-estimated" className="text-2xl font-bold text-foreground mt-2">
            ~{snapshot.saved_tokens_estimated.toLocaleString()}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            Across {snapshot.total_events_mirrored} mirrored events
          </p>
        </div>

        <div className="p-3 rounded-xl bg-muted/30 border border-border flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="flex items-center gap-1 font-medium">
              <Eye className="w-3.5 h-3.5 text-blue-500" /> Mirrored Events
            </span>
          </div>
          <div data-testid="mirrored-events-count" className="text-2xl font-bold text-foreground mt-2">
            {snapshot.total_events_mirrored}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            {snapshot.last_mirrored_at ? 'Active stream' : 'Awaiting events'}
          </p>
        </div>

        <div className="p-3 rounded-xl bg-muted/30 border border-border flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="flex items-center gap-1 font-medium">
              <ShieldCheck className="w-3.5 h-3.5 text-purple-500" /> Doctor Guard
            </span>
            {snapshot.is_compliant ? (
              <span className="flex items-center gap-1 text-[10px] text-emerald-600 font-semibold">
                <CheckCircle2 className="w-3 h-3" /> Compliant
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[10px] text-rose-500 font-semibold">
                <XCircle className="w-3 h-3" /> Breach Caught
              </span>
            )}
          </div>
          <div data-testid="doctor-violations-count" className="text-2xl font-bold text-foreground mt-2">
            {snapshot.violations_intercepted}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">Unauthorized LLM calls blocked</p>
        </div>
      </div>

      {snapshot.recent_violations.length > 0 && (
        <div className="p-3 rounded-xl bg-rose-500/5 border border-rose-500/20 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-rose-600 dark:text-rose-400">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>Doctor Intercepted Violations ({snapshot.recent_violations.length})</span>
          </div>
          <div className="space-y-1.5 max-h-28 overflow-y-auto pr-1">
            {snapshot.recent_violations.map((violation, idx) => (
              <div
                key={`${violation.timestamp}-${idx}`}
                className="text-xs p-2 rounded-lg bg-background/80 border border-rose-500/20 text-muted-foreground flex flex-col gap-0.5"
              >
                <div className="flex items-center justify-between font-mono text-[11px] text-rose-500">
                  <span>Surface: {violation.caller_surface}</span>
                  <span>{violation.prompt_chars} chars blocked</span>
                </div>
                <div className="text-[11px] line-clamp-1 text-foreground/80">
                  {violation.intercepted_reason}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between pt-1 gap-2">
        <button
          type="button"
          onClick={handleSimulateEvent}
          disabled={loading}
          className="flex-1 py-2 px-3 rounded-xl bg-primary text-primary-foreground font-medium text-xs hover:bg-primary/90 transition-all flex items-center justify-center gap-1.5 disabled:opacity-50"
        >
          <Activity className="w-3.5 h-3.5" />
          <span>Mirror Event</span>
        </button>

        <button
          type="button"
          onClick={handleSimulateDoctorViolation}
          disabled={loading}
          className="flex-1 py-2 px-3 rounded-xl bg-rose-500/10 text-rose-600 hover:bg-rose-500/20 border border-rose-500/20 font-medium text-xs transition-all flex items-center justify-center gap-1.5 disabled:opacity-50"
        >
          <AlertTriangle className="w-3.5 h-3.5 text-rose-500" />
          <span>Test Doctor Breach</span>
        </button>

        <button
          type="button"
          onClick={handleReset}
          disabled={loading}
          aria-label="Reset audit"
          className="p-2 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-50"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>
    </dialog>
  );
}
export default ZeroTokenContractCard;
