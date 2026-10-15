import React from 'react';
import {
  Activity,
  CheckCircle2,
  Clock,
  Sparkles,
  Wrench,
  X,
  Zap,
} from 'lucide-react';
import { formatElapsedMs } from './ttftDecouplingEngine';
import { SpeculativeAckPayload } from './ttftDecouplingTypes';
import { useTtftDecouplingStore } from './useTtftDecouplingStore';

interface SpeculativeEarlyAckCardProps {
  ack: SpeculativeAckPayload;
  className?: string;
}

export const SpeculativeEarlyAckCard: React.FC<
  SpeculativeEarlyAckCardProps
> = ({ ack, className = '' }) => {
  const dismissAck = useTtftDecouplingStore((state) => state.dismissAck);

  return (
    <div
      data-testid={`speculative-ack-${ack.id}`}
      className={`my-2 w-full max-w-xl rounded-xl border border-primary/25 bg-primary/5 p-3 text-xs shadow-xs backdrop-blur-md transition-all dark:bg-primary/10 ${className}`}
    >
      <div className="flex items-center justify-between gap-2 border-b border-primary/15 pb-2">
        <div className="flex items-center gap-2">
          <div className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/15 text-primary">
            <Zap className="h-3 w-3 animate-pulse" />
          </div>
          <span className="font-semibold text-foreground">
            即时握手确认 (Speculative Ack)
          </span>
          <span className="flex items-center gap-1 rounded bg-background/80 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground border border-border/40">
            <Clock className="h-2.5 w-2.5 text-primary" />
            TTFT 解耦: {formatElapsedMs(ack.elapsedMs)}
          </span>
        </div>

        <button
          type="button"
          onClick={() => {
            dismissAck(ack.id);
          }}
          aria-label="关闭即时握手卡片"
          className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="h-3 w-3" />
        </button>
      </div>

      <div className="mt-2.5 flex items-start gap-2">
        <div className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center text-primary">
          <Sparkles className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-muted-foreground leading-relaxed">
            {ack.intentSummary}
          </p>

          {/* 预推测工具准备胶囊 */}
          {ack.speculativeTools && ack.speculativeTools.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                <Wrench className="h-2.5 w-2.5" />
                推测性工具预加载:
              </span>
              {ack.speculativeTools.map((tool) => (
                <span
                  key={tool}
                  className="rounded bg-muted/80 px-1.5 py-0.5 font-mono text-[10px] text-foreground/80 border border-border/30"
                >
                  {tool}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="mt-2.5 flex items-center justify-between border-t border-border/30 pt-2 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <Activity className="h-3 w-3 animate-pulse text-primary" />
          正式模型流式正在接入，即将吐出正文...
        </span>
        <span className="flex items-center gap-0.5 text-emerald-600 dark:text-emerald-400 font-medium">
          <CheckCircle2 className="h-3 w-3" />
          意图骨架已锁定
        </span>
      </div>
    </div>
  );
};
