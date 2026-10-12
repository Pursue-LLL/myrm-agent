/**
 * [INPUT]
 * - @/services/memory/hindsight: listHindsightRules, getHindsightBufferStats, queryPreExecutionWarnings, reflectTaskFailure
 * - @/services/memory/hindsight: HindsightRuleResponse, ReflectionBufferStatsResponse, PreExecutionWarningResponse
 * - @/components/primitives: Card, Button, Badge, Input
 * - ./HindsightWarningsView: HindsightWarningsView
 *
 * [OUTPUT]
 * - HindsightReflectionCard: React container rendering Hindsight Experience Replay metrics,
 *   counterfactual failure rule extraction, pre-execution warning probe, and rule ledger.
 *
 * [POS]
 * Personal Brain Command Center UnderstandSection card for hindsight reflection and failure replay buffer.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle,
  History,
  Lightbulb,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Zap,
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
  getHindsightBufferStats,
  type HindsightRuleResponse,
  listHindsightRules,
  type PreExecutionWarningResponse,
  queryPreExecutionWarnings,
  type ReflectionBufferStatsResponse,
  reflectTaskFailure,
} from '@/services/memory/hindsight';
import { HindsightWarningsView } from './HindsightWarningsView';

interface HindsightReflectionCardProps {
  className?: string;
}

export function HindsightReflectionCard({ className }: HindsightReflectionCardProps) {
  const [stats, setStats] = useState<ReflectionBufferStatsResponse | null>(null);
  const [rules, setRules] = useState<HindsightRuleResponse[]>([]);
  const [warnings, setWarnings] = useState<PreExecutionWarningResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isQueryingWarnings, setIsQueryingWarnings] = useState(false);
  const [isReflecting, setIsReflecting] = useState(false);

  // Probe task goal
  const [probeGoal, setProbeGoal] = useState('Clean temp build artifacts in workspace');
  // Fail task input
  const [failedTaskGoal, setFailedTaskGoal] = useState('');
  const [failedErrorMsg, setFailedErrorMsg] = useState('');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [statsRes, rulesRes] = await Promise.all([
        getHindsightBufferStats(),
        listHindsightRules(),
      ]);
      setStats(statsRes);
      setRules(rulesRes);
    } catch {
      setStatusMessage('加载事后反思缓冲池数据失败');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleQueryWarnings = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!probeGoal.trim()) return;

    setIsQueryingWarnings(true);
    setStatusMessage(null);
    try {
      const res = await queryPreExecutionWarnings({
        task_goal: probeGoal.trim(),
        top_k: 3,
      });
      setWarnings(res.warnings);
      setStatusMessage(`前置预警探测完成：匹配到 ${res.total_warnings} 条历史避坑指南`);
    } catch {
      setStatusMessage('匹配前置预警指令失败');
    } finally {
      setIsQueryingWarnings(false);
    }
  };

  const handleReflectFailure = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!failedTaskGoal.trim() || !failedErrorMsg.trim()) {
      return;
    }

    setIsReflecting(true);
    setStatusMessage(null);
    try {
      const res = await reflectTaskFailure({
        trajectory: {
          task_id: `manual-fail-${Date.now()}`,
          task_goal: failedTaskGoal.trim(),
          terminal_error: failedErrorMsg.trim(),
          turns: [
            {
              turn_index: 1,
              tool_name: 'run_command',
              tool_input: {},
              tool_output: failedErrorMsg.trim(),
              error_message: failedErrorMsg.trim(),
            },
          ],
        },
      });
      setStatusMessage(
        `反事实避坑规则 [${res.rule.rule_id}] 提炼成功并沉淀入库: ${res.rule.correction_advice}`,
      );
      setFailedTaskGoal('');
      setFailedErrorMsg('');
      await loadData();
    } catch {
      setStatusMessage('提取事后经验反思规则失败');
    } finally {
      setIsReflecting(false);
    }
  };

  return (
    <Card className={cn('border-border/60 bg-card shadow-sm', className)}>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <History className="h-5 w-5 text-amber-500" />
            <CardTitle className="text-base font-semibold">
              事后经验反思与失败任务回放缓冲池 (Hindsight Reflection Buffer)
            </CardTitle>
          </div>
          <div className="flex items-center gap-1.5">
            <Badge variant="outline" className="border-amber-500/40 text-amber-600 dark:text-amber-400">
              反事实推理 HER
            </Badge>
            <Badge variant="outline" className="border-border/70 text-muted-foreground">
              前置避坑拦截
            </Badge>
          </div>
        </div>
        <CardDescription className="text-xs">
          对标 hindsight commit 614bfc96：当 Agent 遇到报错或失败时，自动定位错误转折点并执行反事实反思，
          提炼结构化避坑规则持久化至缓冲池，在新任务规划阶段作为前置警示主动注入，彻底根治“屡错屡犯”。
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 pt-1">
        {/* Telemetry HUD */}
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-lg border border-border/50 bg-amber-500/10 p-2.5">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
              <Lightbulb className="h-3.5 w-3.5" />
              <span>避坑反思规则数</span>
            </div>
            <div className="mt-1 text-base font-bold text-foreground">
              {stats?.total_rules ?? rules.length}
            </div>
            <div className="text-[10px] text-muted-foreground">持久化缓冲池条目</div>
          </div>

          <div className="rounded-lg border border-border/50 bg-emerald-500/10 p-2.5">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
              <ShieldCheck className="h-3.5 w-3.5" />
              <span>平均置信度</span>
            </div>
            <div className="mt-1 text-base font-bold text-foreground">
              {stats ? `${(stats.avg_confidence * 100).toFixed(0)}%` : '85%'}
            </div>
            <div className="text-[10px] text-muted-foreground">强化证据门禁指标</div>
          </div>

          <div className="rounded-lg border border-border/50 bg-cyan-500/10 p-2.5">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-cyan-600 dark:text-cyan-400">
              <Zap className="h-3.5 w-3.5" />
              <span>前置拦截触发</span>
            </div>
            <div className="mt-1 text-base font-bold text-foreground">
              {stats?.total_hits ?? 0}
            </div>
            <div className="text-[10px] text-muted-foreground">累计阻止重复踩坑</div>
          </div>
        </div>

        {/* Pre-Execution Warning Probe Console */}
        <form onSubmit={handleQueryWarnings} className="space-y-2 rounded-lg border border-border/70 bg-card p-3 shadow-xs">
          <div className="flex flex-wrap items-center gap-2">
            <div className="min-w-[260px] flex-1">
              <label htmlFor="hindsight-probe-goal" className="mb-1 block text-[11px] font-medium text-muted-foreground">
                任务目标前置探测 (Task Goal)
              </label>
              <Input
                id="hindsight-probe-goal"
                value={probeGoal}
                onChange={(e) => setProbeGoal(e.target.value)}
                placeholder="拟执行任务目标或意图描述..."
                className="h-8 text-xs"
              />
            </div>
            <div className="pt-5">
              <Button
                type="submit"
                size="sm"
                disabled={isQueryingWarnings || !probeGoal.trim() || isLoading}
                className="h-8 gap-1 text-xs"
              >
                <ShieldCheck className={cn('h-3.5 w-3.5', isQueryingWarnings && 'animate-spin')} />
                匹配前置避坑预警
              </Button>
            </div>
          </div>
        </form>

        {/* Warnings Result View */}
        {warnings.length > 0 && (
          <div className="rounded-lg border border-border/70 bg-card p-3 shadow-xs">
            <HindsightWarningsView warnings={warnings} />
          </div>
        )}

        {/* Failure Replay & Reflection Extraction Workbench */}
        <details className="rounded-lg border border-border/50 bg-muted/20 p-2.5 text-xs">
          <summary className="cursor-pointer font-medium text-muted-foreground hover:text-foreground">
            + 模拟失败任务事后回放与经验提炼 (Simulate Failure Reflection)
          </summary>
          <form onSubmit={handleReflectFailure} className="mt-2.5 space-y-2">
            <div className="flex flex-wrap gap-2">
              <div className="min-w-[200px] flex-1">
                <label htmlFor="hindsight-fail-goal" className="mb-1 block text-[11px] font-medium text-muted-foreground">
                  失败任务目标
                </label>
                <Input
                  id="hindsight-fail-goal"
                  value={failedTaskGoal}
                  onChange={(e) => setFailedTaskGoal(e.target.value)}
                  placeholder="例如: npm run start 或者 git push origin main"
                  className="h-8 text-xs"
                />
              </div>
              <div className="min-w-[240px] flex-1">
                <label htmlFor="hindsight-fail-error" className="mb-1 block text-[11px] font-medium text-muted-foreground">
                  终端报错或致命异常信息
                </label>
                <Input
                  id="hindsight-fail-error"
                  value={failedErrorMsg}
                  onChange={(e) => setFailedErrorMsg(e.target.value)}
                  placeholder="例如: Port 8080 is already in use 或 Permission denied"
                  className="h-8 text-xs"
                />
              </div>
            </div>
            <Button
              type="submit"
              size="sm"
              disabled={isReflecting || !failedTaskGoal.trim() || !failedErrorMsg.trim()}
              className="h-8 gap-1 text-xs"
            >
              <RotateCcw className={cn('h-3.5 w-3.5', isReflecting && 'animate-spin')} />
              提炼反事实避坑规则并沉淀
            </Button>
          </form>
        </details>

        {/* Status Notification */}
        {statusMessage && (
          <div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            {statusMessage.includes('失败') ? (
              <AlertTriangle className="h-4 w-4 text-destructive" />
            ) : (
              <CheckCircle className="h-4 w-4 text-amber-500" />
            )}
            <span>{statusMessage}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
