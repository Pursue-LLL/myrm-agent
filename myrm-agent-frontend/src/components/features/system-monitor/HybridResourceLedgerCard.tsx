'use client';

/**
 * [INPUT]
 * - ./types::HybridLedgerReport (POS: 混合对账单契约)
 * - ./BudgetQuotaIndicator::BudgetQuotaIndicator (POS: 预算水位指示器)
 * - lucide-react::Cpu, Zap, HardDrive, ShieldAlert, DollarSign, Clock, Layers (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - HybridResourceLedgerCard: 物理硬件占用与认知 Token 双轨混合全景对账单卡片
 *
 * [POS]
 * src/components/features/system-monitor/HybridResourceLedgerCard.tsx — 混合算力多维对账单可视化卡片。
 */

import React from 'react';
import {
  Cpu,
  Zap,
  HardDrive,
  ShieldAlert,
  DollarSign,
  Clock,
  Layers,
} from 'lucide-react';
import type { HybridLedgerReport } from './types';
import { BudgetQuotaIndicator } from './BudgetQuotaIndicator';

interface HybridResourceLedgerCardProps {
  report: HybridLedgerReport;
  maxSeconds?: number | null;
  maxTokens?: number | null;
  maxCredits?: number | null;
  className?: string;
}

const formatSeconds = (sec: number): string => {
  if (sec < 60) return `${sec.toFixed(0)} 秒`;
  const mins = Math.floor(sec / 60);
  const remainingSec = Math.floor(sec % 60);
  return `${mins} 分 ${remainingSec} 秒`;
};

export const HybridResourceLedgerCard: React.FC<HybridResourceLedgerCardProps> = ({
  report,
  maxSeconds,
  maxTokens,
  maxCredits,
  className = '',
}) => {
  const { hardware, cognitive } = report;
  const totalTokens = cognitive.prompt_tokens + cognitive.completion_tokens;

  return (
    <div
      className={`bg-card border rounded-xl shadow-sm overflow-hidden flex flex-col ${
        report.is_budget_exceeded
          ? 'border-destructive/40 ring-1 ring-destructive/30'
          : 'border-border'
      } ${className}`}
    >
      {/* 熔断告警横幅 (若超支) */}
      {report.is_budget_exceeded && (
        <div className="px-4 py-2 bg-destructive/15 border-b border-destructive/30 text-destructive dark:text-red-400 text-xs flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 shrink-0 animate-pulse" />
          <span className="font-medium">
            预算熔断拦截: {report.budget_exceeded_reason || '已超过配置的资源上限配额'}
          </span>
        </div>
      )}

      {/* 顶部总览 */}
      <div className="p-4 sm:p-5 border-b border-border bg-muted/20 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
              <Layers className="w-4 h-4 text-primary" />
              混合算力对账单 (Compute-Cognitive Ledger)
            </h3>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground border border-border">
              AFP 协议
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            任务 ID: {report.task_id}
          </p>
        </div>

        {/* 综合总投入与法币 */}
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-[10px] text-muted-foreground">总算力积分消耗</div>
            <div className="text-base font-bold font-mono text-primary">
              {report.total_credits.toFixed(2)}{' '}
              <span className="text-xs font-normal">Credits</span>
            </div>
          </div>
          <div className="h-8 w-px bg-border hidden sm:block" />
          <div className="text-right">
            <div className="text-[10px] text-muted-foreground">等效法币成本</div>
            <div className="text-base font-bold font-mono text-foreground flex items-center justify-end gap-0.5">
              <DollarSign className="w-3.5 h-3.5 text-muted-foreground" />
              {report.estimated_cost_usd.toFixed(4)}
            </div>
          </div>
        </div>
      </div>

      {/* 双轨消耗明细网格 */}
      <div className="p-4 sm:p-5 grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 轨道 1：物理硬件沙箱占用 */}
        <div className="p-3.5 rounded-lg border border-border bg-background space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-border/60">
            <span className="text-xs font-medium text-foreground flex items-center gap-1.5">
              <Cpu className="w-4 h-4 text-blue-500" />
              物理机器与沙箱执行 (Hardware)
            </span>
            <span className="font-mono text-xs font-semibold text-blue-600 dark:text-blue-400">
              {hardware.hardware_credits.toFixed(2)} Credits
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="p-2 rounded bg-muted/30 border border-border/40">
              <div className="text-[10px] text-muted-foreground flex items-center gap-1">
                <Clock className="w-3 h-3" />
                容器运行耗时
              </div>
              <div className="font-mono font-medium text-foreground mt-0.5">
                {formatSeconds(hardware.execution_seconds)}
              </div>
            </div>

            <div className="p-2 rounded bg-muted/30 border border-border/40">
              <div className="text-[10px] text-muted-foreground flex items-center gap-1">
                <Cpu className="w-3 h-3" />
                沙箱规格配额
              </div>
              <div className="font-mono font-medium text-foreground mt-0.5">
                {hardware.cpu_cores}C / {hardware.memory_gb}GB
              </div>
            </div>

            <div className="col-span-2 p-2 rounded bg-muted/30 border border-border/40 flex items-center justify-between">
              <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                <HardDrive className="w-3 h-3" />
                持久卷 Volume 吞吐
              </span>
              <span className="font-mono text-[11px] text-foreground">
                读 {hardware.volume_read_mb.toFixed(1)}MB / 写 {hardware.volume_write_mb.toFixed(1)}MB
              </span>
            </div>
          </div>
        </div>

        {/* 轨道 2：认知 Token 消耗 */}
        <div className="p-3.5 rounded-lg border border-border bg-background space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-border/60">
            <span className="text-xs font-medium text-foreground flex items-center gap-1.5">
              <Zap className="w-4 h-4 text-amber-500" />
              大模型认知计算 (Cognitive LLM)
            </span>
            <span className="font-mono text-xs font-semibold text-amber-600 dark:text-amber-400">
              {cognitive.cognitive_credits.toFixed(2)} Credits
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="p-2 rounded bg-muted/30 border border-border/40">
              <div className="text-[10px] text-muted-foreground">调用模型</div>
              <div className="font-mono font-medium text-foreground truncate mt-0.5">
                {cognitive.model_name}
              </div>
            </div>

            <div className="p-2 rounded bg-muted/30 border border-border/40">
              <div className="text-[10px] text-muted-foreground">总消耗 Token</div>
              <div className="font-mono font-medium text-foreground mt-0.5">
                {totalTokens.toLocaleString()}
              </div>
            </div>

            <div className="col-span-2 p-2 rounded bg-muted/30 border border-border/40 flex items-center justify-between text-[11px] font-mono">
              <span className="text-muted-foreground">输入: {cognitive.prompt_tokens.toLocaleString()}</span>
              <span className="text-muted-foreground">输出: {cognitive.completion_tokens.toLocaleString()}</span>
              <span className="text-emerald-600 dark:text-emerald-400">
                缓存: {cognitive.cached_prompt_tokens.toLocaleString()}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 底部预算水位指示器 (若有配额) */}
      {(maxSeconds || maxTokens || maxCredits) && (
        <div className="px-4 pb-4 sm:px-5 sm:pb-5">
          <BudgetQuotaIndicator
            currentSeconds={hardware.execution_seconds}
            maxSeconds={maxSeconds}
            currentTokens={totalTokens}
            maxTokens={maxTokens}
            currentCredits={report.total_credits}
            maxCredits={maxCredits}
          />
        </div>
      )}
    </div>
  );
};
