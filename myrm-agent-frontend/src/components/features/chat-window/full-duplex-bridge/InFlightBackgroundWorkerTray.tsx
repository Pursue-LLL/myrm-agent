import React from 'react';
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Cpu,
  Trash2,
  X,
  XCircle,
} from 'lucide-react';
import {
  calculateAggregatedProgress,
  calculateWorkerEta,
  formatDuration,
} from './fullDuplexBridgeEngine';
import { useFullDuplexBridgeStore } from './useFullDuplexBridgeStore';
import { BackgroundWorkerTask } from './fullDuplexBridgeTypes';

interface InFlightBackgroundWorkerTrayProps {
  className?: string;
}

export const InFlightBackgroundWorkerTray: React.FC<
  InFlightBackgroundWorkerTrayProps
> = ({ className = '' }) => {
  const activeWorkers = useFullDuplexBridgeStore((state) => state.activeWorkers);
  const isTrayDrawerOpen = useFullDuplexBridgeStore(
    (state) => state.isTrayDrawerOpen,
  );
  const toggleTrayDrawer = useFullDuplexBridgeStore(
    (state) => state.toggleTrayDrawer,
  );
  const cancelWorker = useFullDuplexBridgeStore((state) => state.cancelWorker);
  const removeWorker = useFullDuplexBridgeStore((state) => state.removeWorker);

  const workersList: BackgroundWorkerTask[] = Object.values(activeWorkers);
  const aggregate = calculateAggregatedProgress(workersList);

  if (workersList.length === 0) {
    return null;
  }

  return (
    <div
      data-testid="in-flight-worker-tray"
      className={`relative z-20 w-full select-none border-b border-border/40 bg-background/80 backdrop-blur-md transition-all ${className}`}
    >
      {/* 顶部紧凑吸顶胶囊条 */}
      <div className="flex h-11 items-center justify-between px-3 text-xs">
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
            {aggregate.hasActive ? (
              <Activity className="h-3.5 w-3.5 animate-pulse" />
            ) : (
              <Cpu className="h-3.5 w-3.5" />
            )}
          </div>

          <div className="flex items-center gap-2 overflow-hidden truncate">
            <span className="font-semibold text-foreground">
              后台长任务并发通道
            </span>
            {aggregate.hasActive ? (
              <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[11px] font-medium text-primary">
                {aggregate.runningCount} 个进行中 · 均度 {aggregate.averageProgress}%
              </span>
            ) : (
              <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                已就绪（{aggregate.completedCount} 完成）
              </span>
            )}

            {aggregate.topActiveTitle && (
              <span className="hidden truncate text-muted-foreground md:inline">
                · {aggregate.topActiveTitle}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {aggregate.hasActive && (
            <div className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-muted sm:block">
              <div
                className="h-full bg-primary transition-all duration-300"
                style={{ width: `${aggregate.averageProgress}%` }}
              />
            </div>
          )}

          <button
            type="button"
            onClick={() => {
              toggleTrayDrawer();
            }}
            aria-label={isTrayDrawerOpen ? '收起后台任务抽屉' : '展开后台任务抽屉'}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <span className="text-[11px]">
              {isTrayDrawerOpen ? '收起面板' : '查看在途任务'}
            </span>
            {isTrayDrawerOpen ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* 展开的在途长任务管理抽屉 */}
      {isTrayDrawerOpen && (
        <div
          data-testid="worker-drawer-panel"
          className="border-t border-border/30 bg-muted/20 px-3 py-3"
        >
          <div className="flex items-center justify-between pb-2 text-[11px] text-muted-foreground">
            <span>在途与已就绪 Worker 任务队列 ({workersList.length})</span>
            <button
              type="button"
              onClick={() => {
                toggleTrayDrawer(false);
              }}
              className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label="关闭抽屉"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="grid gap-2 max-h-72 overflow-y-auto pr-1">
            {workersList.map((worker) => {
              const eta = calculateWorkerEta(
                worker.progress,
                worker.elapsedSec,
                worker.estimatedTotalSec,
              );

              return (
                <div
                  key={worker.id}
                  className="rounded-lg border border-border/50 bg-background/90 p-3 shadow-xs"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                          {worker.category}
                        </span>
                        <h4 className="truncate text-xs font-medium text-foreground">
                          {worker.title}
                        </h4>
                      </div>

                      <div className="mt-1 flex items-center gap-3 text-[11px] text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          已耗时 {formatDuration(worker.elapsedSec)}
                        </span>
                        {worker.status === 'running' && (
                          <span>预估剩余 ~{formatDuration(eta)}</span>
                        )}
                        <span className="font-mono text-primary font-medium">
                          {worker.progress}%
                        </span>
                      </div>
                    </div>

                    <div className="flex shrink-0 items-center gap-1">
                      {worker.status === 'running' && (
                        <button
                          type="button"
                          onClick={() => {
                            cancelWorker(worker.id);
                          }}
                          className="rounded border border-destructive/30 px-2 py-0.5 text-[10px] text-destructive hover:bg-destructive/10"
                        >
                          取消任务
                        </button>
                      )}

                      {(worker.status === 'completed' ||
                        worker.status === 'canceled' ||
                        worker.status === 'failed') && (
                        <button
                          type="button"
                          onClick={() => {
                            removeWorker(worker.id);
                          }}
                          aria-label={`移除任务 ${worker.title}`}
                          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* 进度条 */}
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className={`h-full transition-all duration-300 ${
                        worker.status === 'completed'
                          ? 'bg-emerald-500'
                          : worker.status === 'failed' || worker.status === 'canceled'
                          ? 'bg-destructive/80'
                          : 'bg-primary'
                      }`}
                      style={{ width: `${worker.progress}%` }}
                    />
                  </div>

                  {/* 当前步骤标签 */}
                  <div className="mt-1.5 text-[11px] text-muted-foreground truncate">
                    {worker.currentStepLabel}
                  </div>

                  {/* 详细阶段微步进 */}
                  {worker.steps && worker.steps.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5 pt-1.5 border-t border-border/30">
                      {worker.steps.map((step) => {
                        return (
                          <div
                            key={step.id}
                            className={`flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] ${
                              step.status === 'completed'
                                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                                : step.status === 'running'
                                ? 'bg-primary/10 text-primary font-medium animate-pulse'
                                : step.status === 'failed'
                                ? 'bg-destructive/10 text-destructive'
                                : 'bg-muted/50 text-muted-foreground'
                            }`}
                          >
                            {step.status === 'completed' && (
                              <CheckCircle2 className="h-2.5 w-2.5" />
                            )}
                            {step.status === 'running' && (
                              <Activity className="h-2.5 w-2.5" />
                            )}
                            {step.status === 'failed' && (
                              <XCircle className="h-2.5 w-2.5" />
                            )}
                            <span>{step.label}</span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
