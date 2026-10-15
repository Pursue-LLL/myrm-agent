import React, { useEffect } from 'react';
import {
  Activity,
  CheckCircle2,
  Clock,
  Cpu,
  Database,
  ExternalLink,
  Globe,
  Radio,
  Shield,
  Terminal,
  X,
  Zap,
} from 'lucide-react';
import {
  computeOverallSystemHealth,
  formatLatency,
  getCircuitBreakerLabel,
} from './gracefulDegradationEngine';
import {
  ComponentHealthRecord,
  DependencyComponentType,
} from './gracefulDegradationTypes';
import { useGracefulDegradationStore } from './useGracefulDegradationStore';

interface LiveComponentHealthIndicatorProps {
  className?: string;
}

function renderComponentIcon(type: DependencyComponentType) {
  if (type === 'model') {
    return <Cpu className="h-4 w-4 text-purple-500" />;
  }
  if (type === 'search') {
    return <Globe className="h-4 w-4 text-blue-500" />;
  }
  if (type === 'sandbox') {
    return <Terminal className="h-4 w-4 text-emerald-500" />;
  }
  if (type === 'knowledge_base') {
    return <Database className="h-4 w-4 text-amber-500" />;
  }
  return <Radio className="h-4 w-4 text-indigo-500" />;
}

export const LiveComponentHealthIndicator: React.FC<
  LiveComponentHealthIndicatorProps
> = ({ className = '' }) => {
  const components = useGracefulDegradationStore((state) => state.components);
  const isHealthIndicatorModalOpen = useGracefulDegradationStore(
    (state) => state.isHealthIndicatorModalOpen,
  );
  const toggleHealthModal = useGracefulDegradationStore(
    (state) => state.toggleHealthModal,
  );

  const compList: ComponentHealthRecord[] = Object.values(components);
  const summary = computeOverallSystemHealth(compList);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isHealthIndicatorModalOpen) {
        toggleHealthModal(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isHealthIndicatorModalOpen, toggleHealthModal]);

  return (
    <div className={`relative inline-flex items-center ${className}`}>
      {/* 状态栏极简呼吸指示灯与触发胶囊 */}
      <button
        type="button"
        onClick={() => {
          toggleHealthModal(true);
        }}
        aria-label="查看系统核心组件健康状态与断路器指标"
        className="flex items-center gap-1.5 rounded-full border border-border/50 bg-background/80 px-2 py-1 text-xs text-muted-foreground shadow-2xs backdrop-blur-md transition-colors hover:bg-muted hover:text-foreground"
      >
        <span className="relative flex h-2 w-2">
          {summary.overallStatus === 'healthy' && (
            <>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </>
          )}
          {summary.overallStatus === 'degraded' && (
            <>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
            </>
          )}
          {summary.overallStatus === 'maintenance' && (
            <>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-rose-500" />
            </>
          )}
        </span>

        <span className="text-[11px] font-medium">
          {summary.overallStatus === 'healthy' && '系统健康'}
          {summary.overallStatus === 'degraded' && '部分降级'}
          {summary.overallStatus === 'maintenance' && '服务维护'}
        </span>
        <span className="text-[10px] font-mono text-muted-foreground/80">
          {summary.averageLatencyMs}ms
        </span>
      </button>

      {/* 弹出的多维组件健康透视模态视窗 */}
      {isHealthIndicatorModalOpen && (
        <dialog
          open
          aria-label="系统核心组件健康度透视面板"
          className="fixed inset-0 z-50 m-0 flex h-full w-full items-center justify-center border-0 bg-background/80 p-4 backdrop-blur-md"
        >
          <div
            data-testid="health-diagnostic-modal"
            className="w-full max-w-2xl rounded-2xl border border-border/80 bg-background p-5 shadow-2xl"
          >
            {/* 头部标题与总览评分 */}
            <div className="flex items-center justify-between border-b border-border/40 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Activity className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    系统服务链路与熔断器健康透视
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    白盒化展示各核心依赖可用率、P95 延迟与优雅降级容灾策略
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1.5 rounded-lg border border-border/50 bg-muted/40 px-2.5 py-1 text-xs">
                  <Zap className="h-3.5 w-3.5 text-amber-500" />
                  <span className="text-muted-foreground">健康指数</span>
                  <span className="font-mono font-bold text-foreground">
                    {summary.healthScore}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    toggleHealthModal(false);
                  }}
                  aria-label="关闭健康透视弹窗"
                  className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* 组件健康明细列表 */}
            <div className="mt-4 max-h-[60vh] space-y-2.5 overflow-y-auto pr-1">
              {compList.map((comp) => {
                const latency = formatLatency(comp.latencyMs);
                const breaker = getCircuitBreakerLabel(comp.status);

                return (
                  <div
                    key={comp.id}
                    className="rounded-xl border border-border/50 bg-muted/10 p-3 transition-colors hover:bg-muted/20"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-2.5">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-background shadow-2xs">
                          {renderComponentIcon(comp.type)}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-foreground">
                              {comp.name}
                            </span>
                            <span
                              className={`rounded border px-1.5 py-0.5 text-[10px] font-mono font-medium ${breaker.badgeClass}`}
                            >
                              {breaker.label}
                            </span>
                          </div>

                          <div className="mt-1 flex items-center gap-3 text-[11px] text-muted-foreground">
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              响应延迟:{' '}
                              <span
                                className={`font-mono font-medium ${
                                  latency.level === 'slow'
                                    ? 'text-destructive'
                                    : latency.level === 'moderate'
                                    ? 'text-amber-500'
                                    : 'text-emerald-500'
                                }`}
                              >
                                {latency.text}
                              </span>
                            </span>
                            <span>错误率: {comp.errorRatePercent}%</span>
                          </div>
                        </div>
                      </div>

                      <div className="text-right">
                        <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                          <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                          已纳管
                        </span>
                      </div>
                    </div>

                    {/* 失败原因提示 */}
                    {comp.failureReason && (
                      <div className="mt-2 rounded bg-amber-500/10 px-2 py-1 text-[11px] text-amber-700 dark:text-amber-300">
                        {comp.failureReason}
                      </div>
                    )}

                    {/* 容灾与降级策略 */}
                    <div className="mt-2 flex items-center justify-between border-t border-border/30 pt-1.5 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Shield className="h-3 w-3 text-primary" />
                        容灾策略: {comp.fallbackStrategy}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* 底部关闭按钮 */}
            <div className="mt-4 flex items-center justify-end border-t border-border/40 pt-3">
              <button
                type="button"
                onClick={() => {
                  toggleHealthModal(false);
                }}
                className="rounded-lg bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
              >
                确定并关闭
              </button>
            </div>
          </div>
        </dialog>
      )}
    </div>
  );
};
