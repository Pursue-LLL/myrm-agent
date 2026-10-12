/**
 * [INPUT]
 * - @/services/memory/autoRecall: evaluateAutoRecall, getSlidingWindowStats, clearSessionAutoRecall
 * - @/services/memory/autoRecall: AutoRecallDecisionResponse, SlidingWindowStatsResponse, RecallCandidateDTO
 * - @/components/primitives: Card, Button, Badge, Input
 * - ./AutoRecallFilterTraceView: AutoRecallFilterTraceView
 *
 * [OUTPUT]
 * - AutoRecallGovernanceCard: React container rendering targeted experience auto-recall gate,
 *   5-scenario sensitive trigger evaluation, 5-turn sliding dedup inspection, and fail-open rerank telemetry.
 *
 * [POS]
 * Personal Brain Command Center UnderstandSection card for targeted auto-recall governance.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  CheckCircle,
  Clock,
  Filter,
  Layers,
  Play,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Trash2,
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
  type AutoRecallDecisionResponse,
  clearSessionAutoRecall,
  evaluateAutoRecall,
  getSlidingWindowStats,
  type RecallCandidateDTO,
  type SlidingWindowStatsResponse,
} from '@/services/memory/autoRecall';
import { AutoRecallFilterTraceView } from './AutoRecallFilterTraceView';

interface AutoRecallGovernanceCardProps {
  className?: string;
}

const DEFAULT_CANDIDATES: RecallCandidateDTO[] = [
  {
    memory_id: 'rec-01',
    content: '在执行递归清理时，始终预检路径是否存在于沙箱工作区之内。',
    initial_score: 0.9,
  },
  {
    memory_id: 'rec-02',
    content: 'Docker Socket 权限不足时应通过用户组映射解决，严禁直接 chmod 777。',
    initial_score: 0.85,
  },
  {
    memory_id: 'rec-03',
    content: 'Webpack/Vite 插件热更新冲突时优先核查双重缓存锁机制。',
    initial_score: 0.72,
  },
];

export function AutoRecallGovernanceCard({ className }: AutoRecallGovernanceCardProps) {
  const [sessionId, setSessionId] = useState('session_main_active');
  const [currentTurn, setCurrentTurn] = useState(1);
  const [selectedEvent, setSelectedEvent] = useState<string>('task_start');
  const [toolName, setToolName] = useState('bash');
  const [queryPrompt, setQueryPrompt] = useState('执行新模块工程构建与配置更新');

  const [windowStats, setWindowStats] = useState<SlidingWindowStatsResponse | null>(null);
  const [decision, setDecision] = useState<AutoRecallDecisionResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const loadStats = useCallback(async () => {
    setIsLoading(true);
    try {
      const stats = await getSlidingWindowStats(sessionId);
      setWindowStats(stats);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '获取滑窗统计失败';
      setStatusMessage(`错误: ${msg}`);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const handleEvaluate = async () => {
    setIsEvaluating(true);
    setStatusMessage(null);
    try {
      const res = await evaluateAutoRecall({
        session_id: sessionId,
        current_turn: currentTurn,
        raw_candidates: DEFAULT_CANDIDATES,
        event_name: selectedEvent === 'none' ? null : selectedEvent,
        tool_name: selectedEvent === 'write_preflight' ? toolName : null,
        query_text: queryPrompt,
      });
      setDecision(res);
      setStatusMessage(`已完成第 ${currentTurn} 轮自动召回门禁评估`);
      // Advance turn number
      setCurrentTurn((prev) => prev + 1);
      await loadStats();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '门禁评估执行失败';
      setStatusMessage(`错误: ${msg}`);
    } finally {
      setIsEvaluating(false);
    }
  };

  const handleClearSession = async () => {
    setStatusMessage(null);
    try {
      const res = await clearSessionAutoRecall(sessionId);
      if (res.cleared) {
        setStatusMessage(`已清空会话 ${sessionId} 的 5 轮滑窗记忆缓存`);
        setDecision(null);
        setCurrentTurn(1);
        await loadStats();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '清空会话滑窗失败';
      setStatusMessage(`错误: ${msg}`);
    }
  };

  return (
    <Card className={cn('border-border/80 shadow-sm', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Filter className="h-5 w-5 text-primary" />
            <CardTitle className="text-base font-semibold">
              高敏感场景经验自动召回与 5 轮滑窗去重门禁
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-primary/40 text-primary text-xs">
              Fail-Open 重排降级
            </Badge>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7 text-muted-foreground"
              onClick={loadStats}
              disabled={isLoading}
              title="刷新滑窗状态"
            >
              <RotateCcw className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')} />
            </Button>
          </div>
        </div>
        <CardDescription className="text-xs text-muted-foreground">
          基于 5 大敏感触发场景（任务启动/技能加载/子代理派发/写前防护/定时心跳）按需激活召回，闲聊完全抑制；5 轮滑窗去重杜绝注意力疲劳与 Token 浪费
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 pt-1">
        {/* 滑窗监控指标 HUD */}
        {windowStats && (
          <div className="grid grid-cols-3 gap-2 rounded-lg border border-border/60 bg-muted/30 p-2.5 text-center">
            <div>
              <div className="text-[10px] text-muted-foreground">当前监控会话</div>
              <div className="font-mono text-xs font-semibold text-foreground truncate px-1">
                {windowStats.session_id}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-muted-foreground">活跃滑窗轮次</div>
              <div className="flex items-center justify-center gap-0.5 font-mono text-sm font-semibold text-primary">
                <Clock className="h-3.5 w-3.5" />
                {windowStats.active_window_turns} / 5 轮
              </div>
            </div>
            <div>
              <div className="text-[10px] text-muted-foreground">累计去重抑制记忆</div>
              <div className="flex items-center justify-center gap-0.5 font-mono text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                <ShieldAlert className="h-3.5 w-3.5" />
                {windowStats.total_suppressed_id_count} 条
              </div>
            </div>
          </div>
        )}

        {/* 触发场景与控制表单 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="space-y-1">
            <label
              htmlFor="auto-recall-session-input"
              className="text-[11px] font-medium text-muted-foreground"
            >
              会话标识 Session ID
            </label>
            <Input
              id="auto-recall-session-input"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              className="h-8 font-mono text-xs"
            />
          </div>

          <div className="space-y-1">
            <label
              htmlFor="auto-recall-turn-input"
              className="text-[11px] font-medium text-muted-foreground"
            >
              当前会话轮次 Turn
            </label>
            <Input
              id="auto-recall-turn-input"
              type="number"
              min={1}
              value={currentTurn}
              onChange={(e) => setCurrentTurn(Number(e.target.value) || 1)}
              className="h-8 font-mono text-xs"
            />
          </div>

          <div className="space-y-1">
            <label
              htmlFor="auto-recall-tool-input"
              className="text-[11px] font-medium text-muted-foreground"
            >
              写前预检工具名
            </label>
            <Input
              id="auto-recall-tool-input"
              value={toolName}
              onChange={(e) => setToolName(e.target.value)}
              placeholder="e.g. bash, edit_file"
              className="h-8 font-mono text-xs"
            />
          </div>
        </div>

        {/* 触发场景选择器 */}
        <div className="space-y-1.5">
          <div className="text-[11px] font-medium text-muted-foreground">
            敏感生命周期触发场景
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[
              { id: 'task_start', label: 'task_start (任务启动)' },
              { id: 'skill_load', label: 'skill_load (技能加载)' },
              { id: 'subagent_start', label: 'subagent_start (子智能体)' },
              { id: 'write_preflight', label: 'write_preflight (高危写前)' },
              { id: 'cron_start', label: 'cron_start (定时心跳)' },
              { id: 'none', label: 'none (闲聊日常/完全抑制)' },
            ].map((evt) => (
              <Button
                key={evt.id}
                size="sm"
                variant={selectedEvent === evt.id ? 'default' : 'outline'}
                className="h-7 px-2 text-[10px]"
                onClick={() => setSelectedEvent(evt.id)}
              >
                {evt.label}
              </Button>
            ))}
          </div>
        </div>

        {/* 任务提示输入 */}
        <div className="space-y-1">
          <label
            htmlFor="auto-recall-prompt-input"
            className="text-[11px] font-medium text-muted-foreground"
          >
            上下文查询或意图 Prompt
          </label>
          <Input
            id="auto-recall-prompt-input"
            value={queryPrompt}
            onChange={(e) => setQueryPrompt(e.target.value)}
            className="h-8 text-xs"
          />
        </div>

        {/* 操作按钮栏 */}
        <div className="flex items-center justify-between pt-1 border-t border-border/50">
          <Button
            size="sm"
            variant="outline"
            onClick={handleClearSession}
            className="h-7 text-xs text-muted-foreground hover:text-destructive"
          >
            <Trash2 className="mr-1 h-3.5 w-3.5" />
            清空滑窗记录
          </Button>

          <Button
            size="sm"
            disabled={isEvaluating}
            onClick={handleEvaluate}
            className="h-7 text-xs"
          >
            <Play className="mr-1 h-3.5 w-3.5" />
            执行门禁评估
          </Button>
        </div>

        {statusMessage && (
          <div className="rounded bg-accent/40 px-2.5 py-1.5 text-[11px] text-muted-foreground">
            {statusMessage}
          </div>
        )}

        {/* 门禁决策轨迹视图 */}
        <AutoRecallFilterTraceView decision={decision} />
      </CardContent>
    </Card>
  );
}
