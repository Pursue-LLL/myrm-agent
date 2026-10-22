import React, { useState } from 'react';
import {
  Play,
  Pause,
  SkipForward,
  Send,
  Terminal,
  ShieldAlert,
  History,
  CheckCircle2,
} from 'lucide-react';
import { useFleetObserverStore } from './useFleetObserverStore';

export interface FleetDirectorConsoleProps {
  className?: string;
}

export function FleetDirectorConsole({ className = '' }: FleetDirectorConsoleProps) {
  const executionMode = useFleetObserverStore((s) => s.executionMode);
  const pauseFleet = useFleetObserverStore((s) => s.pauseFleet);
  const resumeFleet = useFleetObserverStore((s) => s.resumeFleet);
  const stepFleet = useFleetObserverStore((s) => s.stepFleet);
  const nodes = useFleetObserverStore((s) => s.nodes);
  const selectedNodeId = useFleetObserverStore((s) => s.selectedNodeId);
  const interventions = useFleetObserverStore((s) => s.interventions);
  const injectDirectorCommand = useFleetObserverStore((s) => s.injectDirectorCommand);

  const [targetNode, setTargetNode] = useState(selectedNodeId || nodes[0]?.id || '');
  const [commandInput, setCommandInput] = useState('');

  const isPaused = executionMode === 'paused';

  function handleSubmitIntervention(e: React.FormEvent) {
    e.preventDefault();
    if (!commandInput.trim() || !targetNode) {
      return;
    }
    injectDirectorCommand(targetNode, commandInput.trim());
    setCommandInput('');
  }

  return (
    <section
      aria-label="全局观察者导演控制台"
      className={`p-5 rounded-xl border border-border bg-card shadow-xs space-y-4 select-none ${className}`}
    >
      {/* 头部控制栏：一键暂停/步进/继续 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border/60">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-primary" />
          <h4 className="text-xs font-bold text-foreground">
            观察者导演交互控制台 (Human-in-the-Loop Orchestration)
          </h4>
        </div>

        <div className="flex items-center gap-2">
          {isPaused ? (
            <button
              type="button"
              aria-label="继续运行机队"
              onClick={resumeFleet}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-600 text-white font-medium text-xs hover:bg-emerald-700 transition-colors shadow-xs"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>继续协同</span>
            </button>
          ) : (
            <button
              type="button"
              aria-label="暂停机队协同"
              onClick={pauseFleet}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 font-medium text-xs border border-amber-500/20 hover:bg-amber-500/20 transition-colors"
            >
              <Pause className="w-3.5 h-3.5 fill-current" />
              <span>一键暂停</span>
            </button>
          )}

          <button
            type="button"
            aria-label="单步步进机队协同"
            onClick={stepFleet}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-muted text-foreground font-medium text-xs hover:bg-muted/80 transition-colors border border-border/80"
          >
            <SkipForward className="w-3.5 h-3.5" />
            <span>单步步进</span>
          </button>
        </div>
      </div>

      {/* 导演指令即刻注入表单 */}
      <form
        onSubmit={handleSubmitIntervention}
        className="p-3.5 rounded-lg border border-border/60 bg-muted/20 space-y-3"
      >
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <ShieldAlert className="w-3.5 h-3.5 text-primary" />
            <span>人类最高仲裁指令注入</span>
          </span>
          <span className="text-[10px] text-muted-foreground">
            即刻中断节点当前推测，强制纠偏对齐
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
          <div>
            <label
              htmlFor="director-target-node"
              className="block text-[11px] font-medium text-muted-foreground mb-1"
            >
              目标执行节点
            </label>
            <select
              id="director-target-node"
              value={targetNode}
              onChange={(e) => {
                setTargetNode(e.target.value);
              }}
              className="w-full text-xs p-2 rounded-md border border-border bg-background text-foreground outline-none focus:border-primary"
            >
              {nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.label}
                </option>
              ))}
            </select>
          </div>

          <div className="sm:col-span-2">
            <label
              htmlFor="director-command-input"
              className="block text-[11px] font-medium text-muted-foreground mb-1"
            >
              仲裁指令内容
            </label>
            <div className="flex items-center gap-2">
              <input
                id="director-command-input"
                type="text"
                value={commandInput}
                onChange={(e) => {
                  setCommandInput(e.target.value);
                }}
                placeholder="例如: 停止发散重构，立即按照方案 B 规约直接落盘..."
                className="flex-1 text-xs px-3 py-2 rounded-md border border-border bg-background text-foreground outline-none focus:border-primary placeholder:text-muted-foreground/60"
                required
              />
              <button
                type="submit"
                aria-label="注入指令"
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-primary text-primary-foreground font-medium text-xs hover:bg-primary/90 transition-colors shrink-0 shadow-xs"
              >
                <Send className="w-3.5 h-3.5" />
                <span>下发指令</span>
              </button>
            </div>
          </div>
        </div>
      </form>

      {/* 导演指令干预历史审计流 */}
      {interventions.length > 0 && (
        <div className="space-y-2 pt-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
            <History className="w-3.5 h-3.5" />
            <span>干预历史审计记录 ({interventions.length})</span>
          </div>

          <div className="space-y-1.5 max-h-32 overflow-y-auto">
            {interventions.map((item) => {
              const node = nodes.find((n) => n.id === item.targetNodeId);
              return (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-2 rounded-md bg-background border border-border/50 text-[11px]"
                >
                  <div className="flex items-center gap-2 truncate">
                    <span className="font-medium text-primary">
                      [{node?.label.split(' ')[0] ?? item.targetNodeId}]
                    </span>
                    <span className="truncate text-foreground/90">{item.commandText}</span>
                  </div>
                  <span className="flex items-center gap-1 text-[10px] text-emerald-600 dark:text-emerald-400 font-mono shrink-0">
                    <CheckCircle2 className="w-3 h-3" />
                    <span>已强制注入</span>
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
