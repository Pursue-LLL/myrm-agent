import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Clock,
  GitCompare,
  Layers,
  Sparkles,
  Wrench,
  X,
  Zap,
} from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import {
  getSessionTrajectory,
  getChatHistory,
  type SessionTrajectoryResponse,
  type ChatItem,
  type TrajectoryStep,
} from '@/services/chat';

interface TrajectoryDiffModalProps {
  open: boolean;
  currentSessionId: string;
  onClose: () => void;
}

export default function TrajectoryDiffModal({ open, currentSessionId, onClose }: TrajectoryDiffModalProps) {
  const t = useTranslations('trajectoryDiff');
  const [trajectoryA, setTrajectoryA] = useState<SessionTrajectoryResponse | null>(null);
  const [trajectoryB, setTrajectoryB] = useState<SessionTrajectoryResponse | null>(null);
  const [sessionList, setSessionList] = useState<ChatItem[]>([]);
  const [selectedSessionBId, setSelectedSessionBId] = useState<string>('');
  const [loading, setLoading] = useState(false);

  // Load Session A trajectory and session list
  useEffect(() => {
    if (!open || !currentSessionId) {
      return;
    }
    setLoading(true);
    Promise.all([
      getSessionTrajectory(currentSessionId).catch(() => null),
      getChatHistory(1, 30).catch(() => ({ items: [] })),
    ]).then(([trajA, history]) => {
      setTrajectoryA(trajA);
      const filtered = (history.items || []).filter((item) => item.id !== currentSessionId);
      setSessionList(filtered);
      setLoading(false);
    });
  }, [open, currentSessionId]);

  // Load Session B trajectory when selected
  useEffect(() => {
    if (!selectedSessionBId) {
      setTrajectoryB(null);
      return;
    }
    getSessionTrajectory(selectedSessionBId)
      .then(setTrajectoryB)
      .catch(() => setTrajectoryB(null));
  }, [selectedSessionBId]);

  // Find divergence index between Session A and Session B
  const divergenceStepIdx = React.useMemo(() => {
    if (!trajectoryA || !trajectoryB) {
      return null;
    }
    const stepsA: TrajectoryStep[] = trajectoryA.turns.flatMap((t) => t.steps);
    const stepsB: TrajectoryStep[] = trajectoryB.turns.flatMap((t) => t.steps);
    const minLen = Math.min(stepsA.length, stepsB.length);

    for (let i = 0; i < minLen; i++) {
      if (
        stepsA[i].tool_name !== stepsB[i].tool_name ||
        JSON.stringify(stepsA[i].tool_args) !== JSON.stringify(stepsB[i].tool_args)
      ) {
        return i;
      }
    }
    return stepsA.length !== stepsB.length ? minLen : null;
  }, [trajectoryA, trajectoryB]);

  return (
    <Dialog open={open} onOpenChange={(val) => !val && onClose()}>
      <DialogContent className="max-w-6xl max-h-[85vh] flex flex-col p-6 overflow-hidden">
        <DialogHeader className="flex flex-row items-center justify-between pb-4 border-b border-border">
          <div className="flex items-center gap-2">
            <GitCompare className="w-5 h-5 text-primary" />
            <DialogTitle className="text-base font-semibold">{t('title')}</DialogTitle>
          </div>
        </DialogHeader>

        {/* Toolbar & Target Session Selector */}
        <div className="flex items-center justify-between py-2 border-b border-border/60 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">{t('compareWith')}:</span>
            <select
              value={selectedSessionBId}
              onChange={(e) => setSelectedSessionBId(e.target.value)}
              className="px-2 py-1 bg-background border border-border rounded text-xs outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">{t('selectSessionPlaceholder')}</option>
              {sessionList.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title || item.id.slice(0, 8)} ({new Date(item.createdAt).toLocaleDateString()})
                </option>
              ))}
            </select>
          </div>

          {divergenceStepIdx !== null && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 font-mono text-xs">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>{t('divergenceDetected', { step: divergenceStepIdx + 1 })}</span>
            </div>
          )}
        </div>

        {/* Dual Waterfall Container */}
        <div className="flex-1 overflow-y-auto grid grid-cols-1 md:grid-cols-2 gap-4 py-4">
          {/* Left: Session A */}
          <div className="space-y-4 border-r border-border/50 pr-2">
            <div className="flex items-center justify-between font-semibold text-xs text-foreground bg-muted/40 p-2 rounded">
              <span>Session A (Current: {trajectoryA?.title || currentSessionId.slice(0, 8)})</span>
              <span className="font-mono text-muted-foreground">
                {trajectoryA?.total_tool_calls || 0} calls | {trajectoryA?.total_tokens.toLocaleString()} tokens
              </span>
            </div>

            {trajectoryA?.turns.map((turn, tIdx) => (
              <div key={turn.turn_id || tIdx} className="space-y-2">
                <div className="text-[11px] font-medium text-primary bg-primary/5 p-1.5 rounded border border-primary/20 truncate">
                  Prompt: {turn.user_prompt}
                </div>
                {turn.steps.map((step, sIdx) => {
                  const isDiv = divergenceStepIdx === sIdx;
                  return (
                    <div
                      key={sIdx}
                      className={`p-2.5 rounded-lg border text-xs space-y-1.5 transition-colors ${
                        isDiv
                          ? 'border-amber-500 bg-amber-500/10'
                          : step.is_error
                            ? 'border-destructive/50 bg-destructive/5'
                            : 'border-border/80 bg-card'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5 font-medium">
                          <Wrench className="w-3.5 h-3.5 text-primary" />
                          <span className="font-mono text-[11px]">{step.tool_name}</span>
                          <span className="text-[10px] text-muted-foreground">#{step.step_index}</span>
                        </div>
                        <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
                          <span>{step.duration_ms.toFixed(0)}ms</span>
                          {step.tokens_used > 0 && <span>{step.tokens_used} tok</span>}
                        </div>
                      </div>
                      <pre className="text-[10px] font-mono p-1.5 rounded bg-muted/40 overflow-x-auto text-muted-foreground max-h-20">
                        {JSON.stringify(step.tool_args, null, 2)}
                      </pre>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>

          {/* Right: Session B */}
          <div className="space-y-4 pl-2">
            <div className="flex items-center justify-between font-semibold text-xs text-foreground bg-muted/40 p-2 rounded">
              <span>
                Session B ({trajectoryB?.title || (selectedSessionBId ? selectedSessionBId.slice(0, 8) : 'None')})
              </span>
              <span className="font-mono text-muted-foreground">
                {trajectoryB?.total_tool_calls || 0} calls | {trajectoryB?.total_tokens.toLocaleString() || 0} tokens
              </span>
            </div>

            {trajectoryB ? (
              trajectoryB.turns.map((turn, tIdx) => (
                <div key={turn.turn_id || tIdx} className="space-y-2">
                  <div className="text-[11px] font-medium text-primary bg-primary/5 p-1.5 rounded border border-primary/20 truncate">
                    Prompt: {turn.user_prompt}
                  </div>
                  {turn.steps.map((step, sIdx) => {
                    const isDiv = divergenceStepIdx === sIdx;
                    return (
                      <div
                        key={sIdx}
                        className={`p-2.5 rounded-lg border text-xs space-y-1.5 transition-colors ${
                          isDiv
                            ? 'border-amber-500 bg-amber-500/10'
                            : step.is_error
                              ? 'border-destructive/50 bg-destructive/5'
                              : 'border-border/80 bg-card'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5 font-medium">
                            <Wrench className="w-3.5 h-3.5 text-primary" />
                            <span className="font-mono text-[11px]">{step.tool_name}</span>
                            <span className="text-[10px] text-muted-foreground">#{step.step_index}</span>
                          </div>
                          <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
                            <span>{step.duration_ms.toFixed(0)}ms</span>
                            {step.tokens_used > 0 && <span>{step.tokens_used} tok</span>}
                          </div>
                        </div>
                        <pre className="text-[10px] font-mono p-1.5 rounded bg-muted/40 overflow-x-auto text-muted-foreground max-h-20">
                          {JSON.stringify(step.tool_args, null, 2)}
                        </pre>
                      </div>
                    );
                  })}
                </div>
              ))
            ) : (
              <div className="flex flex-col items-center justify-center h-48 text-muted-foreground text-xs gap-2">
                <Layers className="w-8 h-8 opacity-20" />
                <span>{t('noSessionSelected')}</span>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
