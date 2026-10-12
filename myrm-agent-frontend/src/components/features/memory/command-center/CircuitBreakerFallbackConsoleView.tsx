/**
 * Embedding Circuit Breaker and Zero-Crash Fallback Console.
 */

import React from 'react';
import { ShieldCheck, ShieldAlert, RefreshCw, Cpu, Database, CheckCircle2, AlertOctagon } from 'lucide-react';
import type { CircuitBreakerStatsDTO } from '@/services/memory/hybridSearch';

interface CircuitBreakerFallbackConsoleViewProps {
  stats: CircuitBreakerStatsDTO;
  onTripBreaker: () => void;
  onResetBreaker: () => void;
  isLoading: boolean;
}

export const CircuitBreakerFallbackConsoleView: React.FC<CircuitBreakerFallbackConsoleViewProps> = ({
  stats,
  onTripBreaker,
  onResetBreaker,
  isLoading,
}) => {
  const isTrip = stats.state === 'open';
  const isHalfOpen = stats.state === 'half_open';

  return (
    <section className="space-y-6">
      {/* Breaker State Machine & Telemetry */}
      <div className="rounded-xl border border-border/70 bg-card p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/50 pb-4">
          <div className="flex items-center gap-2">
            {isTrip ? (
              <ShieldAlert className="h-5 w-5 text-rose-500" aria-hidden="true" />
            ) : isHalfOpen ? (
              <AlertOctagon className="h-5 w-5 text-amber-500" aria-hidden="true" />
            ) : (
              <ShieldCheck className="h-5 w-5 text-emerald-500" aria-hidden="true" />
            )}
            <h3 className="text-sm font-semibold text-foreground">
              向量检索断路器状态机与容灾遥测
            </h3>
          </div>

          <div className="flex items-center gap-2">
            {isTrip ? (
              <button
                type="button"
                onClick={onResetBreaker}
                disabled={isLoading}
                aria-label="复位断路器并恢复向量检索服务"
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white shadow hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                复位并恢复向量检索
              </button>
            ) : (
              <button
                type="button"
                onClick={onTripBreaker}
                disabled={isLoading}
                aria-label="模拟向量服务异常跳闸"
                className="inline-flex items-center gap-1.5 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/20 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50"
              >
                <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
                注入故障跳闸 (Trip)
              </button>
            )}
          </div>
        </div>

        {/* State Pipeline Diagram */}
        <div className="mt-4 rounded-lg bg-muted/40 p-4">
          <div className="text-xs font-medium text-muted-foreground">三态自愈工作拓扑</div>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div
              className={`rounded-lg border p-3 ${
                stats.state === 'closed'
                  ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                  : 'border-border/60 bg-background/50 text-muted-foreground'
              }`}
            >
              <div className="flex items-center gap-1.5 text-xs font-bold">
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                CLOSED 闭合常态
              </div>
              <div className="mt-1 text-[11px]">向量与 FTS5 双路并行，RRF 融合输出</div>
            </div>

            <div
              className={`rounded-lg border p-3 ${
                stats.state === 'open'
                  ? 'border-rose-500/50 bg-rose-500/10 text-rose-700 dark:text-rose-300'
                  : 'border-border/60 bg-background/50 text-muted-foreground'
              }`}
            >
              <div className="flex items-center gap-1.5 text-xs font-bold">
                <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
                OPEN 熔断断开
              </div>
              <div className="mt-1 text-[11px]">短路向量调用，纯 SQLite FTS5 零崩溃响应</div>
            </div>

            <div
              className={`rounded-lg border p-3 ${
                stats.state === 'half_open'
                  ? 'border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-300'
                  : 'border-border/60 bg-background/50 text-muted-foreground'
              }`}
            >
              <div className="flex items-center gap-1.5 text-xs font-bold">
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                HALF_OPEN 半开探测
              </div>
              <div className="mt-1 text-[11px]">发送试探请求，成功恢复闭合，失败重新熔断</div>
            </div>
          </div>
        </div>

        {/* Telemetry Grid */}
        <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-lg border border-border/60 bg-background p-3">
            <div className="text-xs text-muted-foreground">当前运行状态</div>
            <div className="mt-1 text-sm font-bold uppercase tracking-tight text-foreground">
              {stats.state}
            </div>
          </div>

          <div className="rounded-lg border border-border/60 bg-background p-3">
            <div className="text-xs text-muted-foreground">连续异常失败次数</div>
            <div className="mt-1 text-sm font-bold text-foreground">
              {stats.failure_count} 次
            </div>
          </div>

          <div className="rounded-lg border border-border/60 bg-background p-3">
            <div className="text-xs text-muted-foreground">半开探针连续成功</div>
            <div className="mt-1 text-sm font-bold text-foreground">
              {stats.consecutive_successes} 次
            </div>
          </div>

          <div className="rounded-lg border border-border/60 bg-background p-3">
            <div className="text-xs text-muted-foreground">累计跳闸熔断次数</div>
            <div className="mt-1 text-sm font-bold text-foreground">
              {stats.tripped_count} 次
            </div>
          </div>
        </div>
      </div>

      {/* Graceful Fallback Architecture Principles */}
      <div className="rounded-xl border border-border/70 bg-card p-5 shadow-sm">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          无缝平滑降级架构设计保障
        </h4>
        <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="flex items-start gap-3 rounded-lg border border-border/40 p-3.5">
            <Cpu className="mt-0.5 h-4 w-4 text-primary" aria-hidden="true" />
            <div>
              <div className="text-xs font-semibold text-foreground">低于 0.1ms 极速短路拦截</div>
              <div className="mt-1 text-[11px] text-muted-foreground">
                断路器处于 OPEN 状态时，检索管道在主线程直接短路向量网络调用，避免阻塞等待超时，保持系统响应极致敏捷。
              </div>
            </div>
          </div>

          <div className="flex items-start gap-3 rounded-lg border border-border/40 p-3.5">
            <Database className="mt-0.5 h-4 w-4 text-primary" aria-hidden="true" />
            <div>
              <div className="text-xs font-semibold text-foreground">本地 SQLite FTS5 零外部依赖保底</div>
              <div className="mt-1 text-[11px] text-muted-foreground">
                全文本地持久化在嵌入式 SQLite 虚拟表中，支持离线同义词扩展与 BM25 精确命中，外部向量宕机时用户体验平稳不中断。
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
