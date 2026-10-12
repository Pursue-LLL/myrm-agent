/**
 * [INPUT]
 * - @/services/memory/decayLifecycle: evaluateMemoryLifecycle, reviveColdMemory, exportColdArchive
 * - @/services/memory/decayLifecycle: EvaluateLifecycleResponse, ReviveMemoryResponse, ColdArchiveItemSchema
 * - @/components/primitives: Card, Button, Badge, Input
 * - ./ColdArchiveRecordsView: ColdArchiveRecordsView
 *
 * [OUTPUT]
 * - EbbinghausLifecycleCard: React container rendering Ebbinghaus decay curve metrics,
 *   tiered storage lifecycle evaluation, cold memory revival, and cold archival inspector.
 *
 * [POS]
 * Personal Brain Command Center ActSection card for Ebbinghaus temporal decay and tiered storage governance.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Archive,
  CheckCircle,
  Clock,
  Download,
  Flame,
  Layers,
  Play,
  RotateCcw,
  Snowflake,
  Sun,
  TrendingDown,
} from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { cn } from '@/lib/utils/classnameUtils';
import {
  type ColdArchiveItemSchema,
  evaluateMemoryLifecycle,
  type EvaluateLifecycleResponse,
  exportColdArchive,
  reviveColdMemory,
  type ReviveMemoryResponse,
} from '@/services/memory/decayLifecycle';
import { ColdArchiveRecordsView } from './ColdArchiveRecordsView';

interface EbbinghausLifecycleCardProps {
  className?: string;
}

export function EbbinghausLifecycleCard({ className }: EbbinghausLifecycleCardProps) {
  const [report, setReport] = useState<EvaluateLifecycleResponse | null>(null);
  const [archiveRecords, setArchiveRecords] = useState<ColdArchiveItemSchema[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [isReviving, setIsReviving] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const [reviveMemoryId, setReviveMemoryId] = useState('');
  const [reviveBoostImportance, setReviveBoostImportance] = useState('0.9');
  const [reviveResult, setReviveResult] = useState<ReviveMemoryResponse | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const loadInitialData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [evalRes, archiveRes] = await Promise.all([
        evaluateMemoryLifecycle(),
        exportColdArchive(),
      ]);
      setReport(evalRes);
      setArchiveRecords(archiveRes.records);
    } catch {
      setStatusMessage('加载艾宾浩斯生命周期数据失败');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadInitialData();
  }, [loadInitialData]);

  const handleEvaluateLifecycle = async () => {
    setIsEvaluating(true);
    setStatusMessage(null);
    try {
      const res = await evaluateMemoryLifecycle();
      setReport(res);
      setStatusMessage(
        `评估流转完成：评估 ${res.total_evaluated} 条记忆，迁移 ${res.migrated_count} 条（HOT ${res.hot_count} / WARM ${res.warm_count} / COLD ${res.cold_count}）`,
      );
      // Refresh cold archive snapshot
      const archiveRes = await exportColdArchive();
      setArchiveRecords(archiveRes.records);
    } catch {
      setStatusMessage('运行艾宾浩斯生命周期衰减评估失败');
    } finally {
      setIsEvaluating(false);
    }
  };

  const handleReviveMemory = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!reviveMemoryId.trim()) return;

    setIsReviving(true);
    setStatusMessage(null);
    try {
      const boostVal = parseFloat(reviveBoostImportance) || 0.9;
      const res = await reviveColdMemory({
        memory_id: reviveMemoryId.trim(),
        boost_importance: boostVal,
      });
      setReviveResult(res);
      setStatusMessage(
        `冷记忆 [${res.memory_id}] 已激活唤醒并提升至 HOT 层（新分值 ${res.new_score}，访问次数 ${res.access_count}）`,
      );
      await loadInitialData();
    } catch {
      setStatusMessage(`唤醒记忆 [${reviveMemoryId}] 失败，可能不存在于生命周期跟踪池`);
    } finally {
      setIsReviving(false);
    }
  };

  const handleExportColdArchive = async () => {
    setIsExporting(true);
    try {
      const res = await exportColdArchive();
      setArchiveRecords(res.records);
      setStatusMessage(`已同步 ${res.total_archived} 条冷存储归档数据切片`);
    } catch {
      setStatusMessage('导出冷存储归档失败');
    } finally {
      setIsExporting(false);
    }
  };

  const total = report?.total_evaluated || (report ? report.hot_count + report.warm_count + report.cold_count : 0) || 1;
  const hotPct = Math.round(((report?.hot_count ?? 0) / total) * 100);
  const warmPct = Math.round(((report?.warm_count ?? 0) / total) * 100);
  const coldPct = Math.max(0, 100 - hotPct - warmPct);

  return (
    <Card className={cn('border-border/60 bg-card shadow-sm', className)}>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <TrendingDown className="h-5 w-5 text-amber-500" />
            <CardTitle className="text-base font-semibold">
              艾宾浩斯遗忘衰减与分层生命周期 (Ebbinghaus Decay & Tiered Storage)
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleEvaluateLifecycle}
              disabled={isEvaluating || isLoading}
              className="h-8 gap-1 text-xs"
            >
              <Play className={cn('h-3.5 w-3.5', isEvaluating && 'animate-spin')} />
              运行衰减评估与存储迁移
            </Button>
          </div>
        </div>
        <CardDescription className="text-xs">
          腾讯云 TencentDB Memory 架构标准：基于艾宾浩斯遗忘曲线融合时间距离、访问频次与重要度
          S(t) = I·e^(−λ·Δt)·(1+α·ln(1+f))，自动流转 HOT 热内存、WARM 温向量、COLD 冷归档。
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 pt-1">
        {/* Tier Distribution HUD */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded-lg border border-border/50 bg-rose-500/10 p-2.5">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-rose-600 dark:text-rose-400">
              <Flame className="h-3.5 w-3.5" />
              <span>HOT 热活跃内存</span>
            </div>
            <div className="mt-1 text-base font-bold text-foreground">
              {report?.hot_count ?? 0}
            </div>
            <div className="text-[10px] text-muted-foreground">{hotPct}% 占比</div>
          </div>

          <div className="rounded-lg border border-border/50 bg-amber-500/10 p-2.5">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
              <Sun className="h-3.5 w-3.5" />
              <span>WARM 温向量检索</span>
            </div>
            <div className="mt-1 text-base font-bold text-foreground">
              {report?.warm_count ?? 0}
            </div>
            <div className="text-[10px] text-muted-foreground">{warmPct}% 占比</div>
          </div>

          <div className="rounded-lg border border-border/50 bg-blue-500/10 p-2.5">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-blue-600 dark:text-blue-400">
              <Snowflake className="h-3.5 w-3.5" />
              <span>COLD 冷存储归档</span>
            </div>
            <div className="mt-1 text-base font-bold text-foreground">
              {report?.cold_count ?? 0}
            </div>
            <div className="text-[10px] text-muted-foreground">{coldPct}% 占比</div>
          </div>

          <div className="rounded-lg border border-border/50 bg-accent/20 p-2.5">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-foreground">
              <Activity className="h-3.5 w-3.5 text-primary" />
              <span>流转变更数</span>
            </div>
            <div className="mt-1 text-base font-bold text-foreground">
              {report?.migrated_count ?? 0}
            </div>
            <div className="text-[10px] text-muted-foreground">
              共评估 {report?.total_evaluated ?? 0} 条
            </div>
          </div>
        </div>

        {/* Tier Proportion Multi-bar */}
        <div className="space-y-1">
          <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted/40">
            <div
              style={{ width: `${hotPct}%` }}
              className="bg-rose-500 transition-all duration-300"
              title={`HOT: ${hotPct}%`}
            />
            <div
              style={{ width: `${warmPct}%` }}
              className="bg-amber-500 transition-all duration-300"
              title={`WARM: ${warmPct}%`}
            />
            <div
              style={{ width: `${coldPct}%` }}
              className="bg-blue-500 transition-all duration-300"
              title={`COLD: ${coldPct}%`}
            />
          </div>
        </div>

        {/* Cold Memory Revive Action Panel */}
        <div className="rounded-lg border border-border/70 bg-card p-3 shadow-xs">
          <div className="mb-2 flex items-center gap-1.5">
            <RotateCcw className="h-4 w-4 text-emerald-500" />
            <span className="text-xs font-semibold text-foreground">
              冷记忆唤醒与激活通道 (Deep Recall & Revive)
            </span>
          </div>

          <form onSubmit={handleReviveMemory} className="flex flex-wrap items-center gap-2">
            <Input
              value={reviveMemoryId}
              onChange={(e) => setReviveMemoryId(e.target.value)}
              placeholder="待唤醒记忆 ID (如 mem-old-rule)"
              className="h-8 min-w-[200px] flex-1 text-xs"
            />
            <Input
              type="number"
              step="0.05"
              min="0.1"
              max="1.0"
              value={reviveBoostImportance}
              onChange={(e) => setReviveBoostImportance(e.target.value)}
              placeholder="加权重要度 (0.1 - 1.0)"
              className="h-8 w-36 text-xs"
            />
            <Button
              type="submit"
              size="sm"
              disabled={isReviving || !reviveMemoryId.trim()}
              className="h-8 gap-1 text-xs"
            >
              <RotateCcw className={cn('h-3.5 w-3.5', isReviving && 'animate-spin')} />
              激活唤醒至 HOT 层
            </Button>
          </form>

          {reviveResult && (
            <div className="mt-2.5 flex items-center justify-between rounded-md border border-emerald-500/40 bg-emerald-500/10 p-2 text-xs text-foreground">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-emerald-500" />
                <span>
                  记忆 <strong>{reviveResult.memory_id}</strong> 唤醒成功！当前分值: <strong>{reviveResult.new_score}</strong>
                </span>
              </div>
              <Badge className="bg-emerald-600 text-white">
                {reviveResult.new_tier}
              </Badge>
            </div>
          )}
        </div>

        {/* Cold Storage Archival Inspector */}
        <div className="rounded-lg border border-border/70 bg-card p-3 shadow-xs">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Archive className="h-4 w-4 text-blue-500" />
              <span className="text-xs font-semibold text-foreground">
                冷存储 JSONL 归档探针 ({archiveRecords.length})
              </span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleExportColdArchive}
              disabled={isExporting}
              className="h-7 gap-1 text-xs"
            >
              <Download className={cn('h-3 w-3', isExporting && 'animate-spin')} />
              同步冷归档
            </Button>
          </div>

          <ColdArchiveRecordsView records={archiveRecords} />
        </div>

        {/* Status Notification */}
        {statusMessage && (
          <div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            {statusMessage.includes('失败') ? (
              <AlertTriangle className="h-4 w-4 text-destructive" />
            ) : (
              <CheckCircle className="h-4 w-4 text-emerald-500" />
            )}
            <span>{statusMessage}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
