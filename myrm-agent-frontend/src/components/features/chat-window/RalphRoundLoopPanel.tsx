/**
 * [INPUT]
 * - react (POS: UI 组件与交互状态钩子)
 * - lucide-react (POS: 矢量图标库，包含 RotateCw, ShieldAlert, Sparkles, CheckCircle2, AlertOctagon, Terminal, FolderGit2, ChevronDown, ChevronUp, Clock)
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind 样式合并纯函数)
 *
 * [OUTPUT]
 * - RalphRoundLoopPanel: Ralph 式 Fresh-Agent 多轮循环与五字段交接监控面板
 * - RalphRoundLoopPanelProps: 组件属性契约
 * - RalphHandoffData: 五字段交接报告契约
 * - RalphRoundData: 单轮记录数据契约
 * - RalphSessionData: Ralph 循环会话全量契约
 *
 * [POS]
 * 对话窗口 Ralph 多轮循环可视化面板（RalphFreshAgentRoundLoopWorkflowPack）。
 * 呈现零历史满血 Fresh 子 Agent 轮次时间线、五字段结构化交接契约、Min-3-Round 阻断防御与共享工作区状态。
 */
import React, { useState } from 'react';
import {
  RotateCw,
  ShieldAlert,
  Sparkles,
  CheckCircle2,
  AlertOctagon,
  Terminal,
  FolderGit2,
  ChevronDown,
  ChevronUp,
  Clock,
  ArrowRight,
  ShieldCheck,
  FileCode2,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type RalphHandoffStatus = 'in_progress' | 'blocked' | 'completed';

export interface RalphHandoffData {
  status: RalphHandoffStatus;
  summary: string;
  evidence: string;
  nextSteps: string;
  blocker?: string;
}

export interface RalphRoundData {
  roundIndex: number;
  childSessionId: string;
  handoff: RalphHandoffData;
  createdAt?: number;
  durationSeconds?: number;
  tokensConsumed?: number;
  wasBlockedDowngraded?: boolean;
}

export interface RalphSessionData {
  sessionId: string;
  humanGoal: string;
  workspaceRoot: string;
  currentRound: number;
  maxRounds: number;
  minRoundsBeforeBlocked: number;
  status: RalphHandoffStatus;
  rounds: RalphRoundData[];
  nextDirective?: string;
}

export interface RalphRoundLoopPanelProps {
  session: RalphSessionData;
  isLoading?: boolean;
  onRefresh?: () => Promise<void> | void;
  onAdvanceRound?: (
    sessionId: string,
    childSessionId: string,
    handoff: RalphHandoffData
  ) => Promise<void> | void;
  className?: string;
}

function getStatusBadge(status: RalphHandoffStatus): React.ReactElement {
  switch (status) {
    case 'completed':
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-600 border border-emerald-500/30 flex items-center gap-1">
          <CheckCircle2 className="w-3 h-3" /> 已完成
        </span>
      );
    case 'blocked':
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-rose-500/10 text-rose-600 border border-rose-500/30 flex items-center gap-1">
          <AlertOctagon className="w-3 h-3" /> 阻断中
        </span>
      );
    case 'in_progress':
    default:
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-sky-500/10 text-sky-600 border border-sky-500/30 flex items-center gap-1">
          <RotateCw className="w-3 h-3 animate-spin" /> 执行中
        </span>
      );
  }
}

export const RalphRoundLoopPanel: React.FC<RalphRoundLoopPanelProps> = ({
  session,
  isLoading = false,
  onRefresh,
  onAdvanceRound,
  className,
}) => {
  const [selectedRoundIdx, setSelectedRoundIdx] = useState<number>(
    session.rounds.length > 0 ? session.rounds[session.rounds.length - 1].roundIndex : 1
  );
  const [showNextDirective, setShowNextDirective] = useState<boolean>(false);

  const activeRound = session.rounds.find((r) => r.roundIndex === selectedRoundIdx);

  return (
    <div
      data-testid="ralph-round-loop-panel"
      className={cn(
        'w-full max-w-2xl rounded-xl border border-border/80 bg-card/95 text-card-foreground shadow-sm overflow-hidden text-xs transition-all',
        className
      )}
    >
      {/* 头部：任务根目标与满血 Fresh 标记 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50 bg-muted/20">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-sm text-foreground">Ralph Fresh-Agent 多轮循环</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                Fresh Context 零会话历史
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              会话: <span className="font-mono">{session.sessionId}</span> · 共享工作区:{' '}
              <span className="font-mono">{session.workspaceRoot}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {getStatusBadge(session.status)}
          {onRefresh && (
            <button
              type="button"
              data-testid="refresh-button"
              onClick={onRefresh}
              disabled={isLoading}
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <RotateCw className={cn('w-3.5 h-3.5', isLoading && 'animate-spin')} />
            </button>
          )}
        </div>
      </div>

      {/* 人类不可篡改根本目标展示 */}
      <div className="px-4 py-2.5 bg-background border-b border-border/40 flex items-start gap-2">
        <ShieldCheck className="w-4 h-4 text-primary shrink-0 mt-0.5" />
        <div className="text-[11px] leading-relaxed">
          <span className="font-semibold text-foreground">[人类根目标 锁定]:</span>{' '}
          <span className="text-foreground/90 font-medium">{session.humanGoal}</span>
        </div>
      </div>

      {/* 轮次时间线 Stepper */}
      <div className="px-4 py-2 bg-muted/10 border-b border-border/40 overflow-x-auto">
        <div className="flex items-center gap-1.5 min-w-max" data-testid="round-stepper">
          {Array.from({ length: Math.max(session.maxRounds, session.currentRound) }).map((_, idx) => {
            const rIdx = idx + 1;
            const isCompleted = rIdx < session.currentRound || (rIdx === session.currentRound && session.status === 'completed');
            const isCurrent = rIdx === session.currentRound && session.status === 'in_progress';
            const isSelected = rIdx === selectedRoundIdx;
            const roundData = session.rounds.find((r) => r.roundIndex === rIdx);

            return (
              <button
                key={rIdx}
                type="button"
                onClick={() => setSelectedRoundIdx(rIdx)}
                className={cn(
                  'px-2.5 py-1 rounded-md text-[11px] font-medium transition-all flex items-center gap-1 border',
                  isSelected && 'ring-1 ring-primary border-primary bg-primary/5 text-primary',
                  !isSelected && isCompleted && 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20',
                  !isSelected && isCurrent && 'bg-sky-500/10 text-sky-600 border-sky-500/30',
                  !isSelected && !isCompleted && !isCurrent && 'bg-muted/40 text-muted-foreground border-border/30 opacity-60'
                )}
              >
                <span>Round {rIdx}</span>
                {roundData?.wasBlockedDowngraded && (
                  <ShieldAlert className="w-3 h-3 text-amber-500 shrink-0" />
                )}
                {isCompleted && <CheckCircle2 className="w-3 h-3 text-emerald-500 shrink-0" />}
              </button>
            );
          })}
        </div>
      </div>

      {/* 选中轮次的五字段交接展示 */}
      <div className="p-4 space-y-3">
        {activeRound ? (
          <div data-testid="round-detail-card" className="space-y-2.5">
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-foreground text-xs">
                  Round {activeRound.roundIndex} 五字段结构化交接
                </span>
                <span className="font-mono text-[10px] text-muted-foreground">
                  Child: {activeRound.childSessionId}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {activeRound.tokensConsumed !== undefined && (
                  <span className="text-[10px] text-muted-foreground font-mono">
                    {activeRound.tokensConsumed.toLocaleString()} Tokens
                  </span>
                )}
                {getStatusBadge(activeRound.handoff.status)}
              </div>
            </div>

            {/* 若触发 Min-3-Round 阻断防御降级，展示醒目黄盾提示 */}
            {activeRound.wasBlockedDowngraded && (
              <div
                data-testid="guardrail-downgraded-banner"
                className="flex items-center gap-2 p-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-800 dark:text-amber-300 text-[11px]"
              >
                <ShieldAlert className="w-4 h-4 text-amber-500 shrink-0" />
                <div>
                  <span className="font-semibold">[Ralph Guardrail 拦截]:</span> 未满{' '}
                  {session.minRoundsBeforeBlocked} 轮门槛禁止声明 BLOCKED，已强制防御降级为 IN_PROGRESS 并在下轮调整重试。
                </div>
              </div>
            )}

            {/* 五字段逐项渲染 */}
            <div className="space-y-2">
              {/* 1. Summary */}
              <div className="p-2.5 rounded-lg bg-muted/30 border border-border/50">
                <div className="font-semibold text-foreground flex items-center gap-1.5 mb-1">
                  <Terminal className="w-3.5 h-3.5 text-primary" />
                  1. Summary (本轮执行摘要)
                </div>
                <p className="text-[11px] text-foreground/90 leading-relaxed font-mono whitespace-pre-wrap">
                  {activeRound.handoff.summary}
                </p>
              </div>

              {/* 2. Evidence */}
              <div className="p-2.5 rounded-lg bg-muted/30 border border-border/50">
                <div className="font-semibold text-foreground flex items-center gap-1.5 mb-1">
                  <FileCode2 className="w-3.5 h-3.5 text-emerald-500" />
                  2. Evidence (产物与验证凭据)
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed font-mono whitespace-pre-wrap">
                  {activeRound.handoff.evidence}
                </p>
              </div>

              {/* 3. Next Steps */}
              <div className="p-2.5 rounded-lg bg-muted/30 border border-border/50">
                <div className="font-semibold text-foreground flex items-center gap-1.5 mb-1">
                  <ArrowRight className="w-3.5 h-3.5 text-sky-500" />
                  3. Next Steps (指引下一轮全新子 Agent)
                </div>
                <p className="text-[11px] text-foreground/90 leading-relaxed whitespace-pre-wrap">
                  {activeRound.handoff.nextSteps}
                </p>
              </div>

              {/* 4. Blocker (若有) */}
              {activeRound.handoff.blocker && (
                <div className="p-2.5 rounded-lg bg-rose-500/5 border border-rose-500/20">
                  <div className="font-semibold text-rose-600 flex items-center gap-1.5 mb-1">
                    <AlertOctagon className="w-3.5 h-3.5 text-rose-500" />
                    4. Blocker (阻塞原因)
                  </div>
                  <p className="text-[11px] text-rose-700 dark:text-rose-300 font-mono">
                    {activeRound.handoff.blocker}
                  </p>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div data-testid="round-empty-state" className="p-6 text-center text-muted-foreground">
            <Clock className="w-6 h-6 mx-auto mb-2 text-muted-foreground/60" />
            <p>第 {selectedRoundIdx} 轮尚未完成交接，正在由全新 Fresh Agent 满血执行中...</p>
          </div>
        )}

        {/* 下一轮启动 Prompt 指令折叠展示 */}
        {session.nextDirective && (
          <div className="rounded-lg border border-border/60 bg-muted/20 overflow-hidden">
            <button
              type="button"
              data-testid="toggle-directive-button"
              onClick={() => setShowNextDirective(!showNextDirective)}
              className="w-full flex items-center justify-between p-2.5 text-left font-medium text-foreground hover:bg-muted/30 transition-colors"
            >
              <span className="flex items-center gap-1.5">
                <FolderGit2 className="w-3.5 h-3.5 text-primary" />
                下轮 Fresh Agent 启动指令 (Zero-Seed Prompt)
              </span>
              {showNextDirective ? (
                <ChevronUp className="w-3.5 h-3.5 text-muted-foreground" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
              )}
            </button>
            {showNextDirective && (
              <div className="p-3 border-t border-border/40 bg-background/80">
                <pre
                  data-testid="next-directive-content"
                  className="text-[10px] font-mono text-muted-foreground whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto"
                >
                  {session.nextDirective}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 底部信息条 */}
      <div className="flex items-center justify-between px-4 py-2 border-t border-border/50 bg-muted/10 text-[10px] text-muted-foreground">
        <div>
          规则门禁: 至少尝试满{' '}
          <span className="font-semibold font-mono text-foreground">{session.minRoundsBeforeBlocked}</span> 轮后方可声称
          BLOCKED
        </div>
        <div className="font-mono">
          进度: Round {session.currentRound} / {session.maxRounds}
        </div>
      </div>
    </div>
  );
};
