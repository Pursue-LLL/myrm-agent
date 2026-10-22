import React from 'react';
import {
  Laptop,
  Cloud,
  Cpu,
  Activity,
  CheckCircle2,
  PauseCircle,
  AlertTriangle,
  ArrowRight,
} from 'lucide-react';
import { useFleetObserverStore } from './useFleetObserverStore';
import type { FleetHostType, FleetNodeStatus } from './fleetObserverTypes';

export interface FleetTopologyCanvasProps {
  className?: string;
}

function getHostIcon(hostType: FleetHostType) {
  switch (hostType) {
    case 'mac_local':
      return <Laptop className="w-4 h-4 text-blue-500" />;
    case 'cloud_sandbox':
      return <Cloud className="w-4 h-4 text-sky-500" />;
    case 'gpu_cluster':
    default:
      return <Cpu className="w-4 h-4 text-purple-500" />;
  }
}

function getStatusBadge(status: FleetNodeStatus) {
  switch (status) {
    case 'busy':
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
          <Activity className="w-2.5 h-2.5 animate-pulse" />
          <span>执行中</span>
        </span>
      );
    case 'paused':
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
          <PauseCircle className="w-2.5 h-2.5" />
          <span>已暂停</span>
        </span>
      );
    case 'error':
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20">
          <AlertTriangle className="w-2.5 h-2.5" />
          <span>异常</span>
        </span>
      );
    case 'idle':
    default:
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground border border-border/60">
          <CheckCircle2 className="w-2.5 h-2.5" />
          <span>空闲待命</span>
        </span>
      );
  }
}

export function FleetTopologyCanvas({ className = '' }: FleetTopologyCanvasProps) {
  const nodes = useFleetObserverStore((s) => s.nodes);
  const links = useFleetObserverStore((s) => s.links);
  const selectedNodeId = useFleetObserverStore((s) => s.selectedNodeId);
  const selectNode = useFleetObserverStore((s) => s.selectNode);

  return (
    <section
      aria-label="分布式机队实时协同拓扑图"
      className={`relative p-5 rounded-xl border border-border bg-card/50 flex flex-col gap-5 select-none ${className}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-emerald-500 animate-ping" />
          <h4 className="text-xs font-bold text-foreground tracking-tight">
            机队协同拓扑流转 (跨机/跨端实时视界)
          </h4>
        </div>
        <span className="text-[11px] text-muted-foreground font-mono">
          {nodes.length} 活跃节点 · {links.length} 活动流转链路
        </span>
      </div>

      {/* 节点网格卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        {nodes.map((node) => {
          const isSelected = selectedNodeId === node.id;
          return (
            <button
              key={node.id}
              type="button"
              onClick={() => {
                selectNode(node.id);
              }}
              className={`text-left p-3.5 rounded-lg border transition-all cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-primary/50 ${
                isSelected
                  ? 'bg-primary/5 border-primary shadow-sm'
                  : 'bg-background hover:bg-muted/40 border-border/80'
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="p-1.5 rounded-md bg-muted/60 border border-border/40 shrink-0">
                    {getHostIcon(node.hostType)}
                  </div>
                  <span className="font-semibold text-xs text-foreground truncate">
                    {node.label}
                  </span>
                </div>
                {getStatusBadge(node.status)}
              </div>

              <p className="text-[11px] text-muted-foreground truncate mb-2">
                角色: {node.role}
              </p>

              {node.currentTask && (
                <div className="p-2 rounded bg-muted/30 border border-border/50 text-[11px] text-foreground/90 leading-snug line-clamp-2 mb-2">
                  {node.currentTask}
                </div>
              )}

              <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-1 border-t border-border/40 font-mono">
                <span>燃烧: {node.tokenBurnRate} tok/s</span>
                <span>已交付: {node.completedTasksCount} 任务</span>
              </div>
            </button>
          );
        })}
      </div>

      {/* 工单传递流向指示条 */}
      <div className="p-3 rounded-lg border border-border/60 bg-muted/20 space-y-2">
        <span className="text-[11px] font-semibold text-muted-foreground block">
          当前工单动态流光流转列表
        </span>
        <div className="space-y-2">
          {links.map((link) => {
            const source = nodes.find((n) => n.id === link.sourceId);
            const target = nodes.find((n) => n.id === link.targetId);
            return (
              <div
                key={link.id}
                className="flex items-center justify-between text-xs p-2 rounded bg-background border border-border/60"
              >
                <div className="flex items-center gap-2 min-w-0 flex-1 mr-3">
                  <span className="font-medium text-foreground truncate max-w-[120px]">
                    {source?.label.split(' ')[0] ?? link.sourceId}
                  </span>
                  <ArrowRight className="w-3.5 h-3.5 text-primary shrink-0 animate-pulse" />
                  <span className="font-medium text-foreground truncate max-w-[120px]">
                    {target?.label.split(' ')[0] ?? link.targetId}
                  </span>
                  <span className="text-[11px] text-muted-foreground truncate max-w-[200px]">
                    ({link.workOrderTitle})
                  </span>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <div className="w-20 bg-muted rounded-full h-1.5 overflow-hidden">
                    <div
                      className="bg-primary h-full transition-all duration-300"
                      style={{ width: `${link.progress}%` }}
                    />
                  </div>
                  <span className="text-[10px] font-mono text-muted-foreground w-8 text-right">
                    {link.progress}%
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
