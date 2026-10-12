'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Badge } from '@/components/primitives/badge';
import {
  Compass,
  CheckCircle2,
  AlertOctagon,
  Sparkles,
  ShieldCheck,
  ShieldAlert,
  Loader2,
  FileCode2,
  ArrowRight,
  ListOrdered,
} from 'lucide-react';
import {
  checkActionProhibited,
  getAntiLoopSnapshot,
  getTaskBlackbox,
  recordMilestone,
  recordFailedAttempt,
  recordUserSteering,
  type TaskTrajectoryBlackboxResponseDTO,
  type AntiLoopSnapshotResponseDTO,
  type CheckActionResponseDTO,
} from '@/services/memory/taskTriadTrajectory';

export function TaskTriadTrajectoryCard(): React.JSX.Element {
  const [taskId, setTaskId] = useState<string>('task_refactor_jwt_01');
  const [sessionId, setSessionId] = useState<string>('session_dev_main');
  const [testAction, setTestAction] = useState<string>('docker run -p 8080:8080 auth-service');

  const [loading, setLoading] = useState<boolean>(false);
  const [checking, setChecking] = useState<boolean>(false);
  const [blackbox, setBlackbox] = useState<TaskTrajectoryBlackboxResponseDTO | null>(null);
  const [checkResult, setCheckResult] = useState<CheckActionResponseDTO | null>(null);
  const [snapshot, setSnapshot] = useState<AntiLoopSnapshotResponseDTO | null>(null);

  const fetchTrajectory = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      const data = await getTaskBlackbox(taskId);
      setBlackbox(data);
    } catch {
      // Offline fallback state with mocked triad trajectory
      setBlackbox({
        task_id: taskId,
        session_id: sessionId,
        initial_goal: '长程超长任务：重构系统认证模块为无状态架构',
        status: 'running',
        version: 3,
        milestones: [
          {
            milestone_id: 'ms_01',
            step_index: 2,
            title: '密码哈希升级为 Argon2id',
            description: '已跑通单元测试',
            verified_output_summary: '12 项密码学单测全绿，耗时 120ms',
            artifacts_produced: ['src/auth/hash.ts'],
            timestamp: new Date().toISOString(),
          },
        ],
        failed_attempts: [
          {
            attempt_id: 'fa_01',
            step_index: 4,
            action_attempted: 'docker run -p 8080:8080 auth-service',
            error_type: 'PortConflict',
            error_summary: '端口 8080 被占用导致容器起不来',
            dead_end_pattern: '8080:8080',
            prohibited_rule: '严禁再绑定 8080 端口，必须使用 8081 或动态端口',
            lessons_learned: '先执行 lsof 检查端口占用',
            timestamp: new Date().toISOString(),
          },
        ],
        user_steerings: [
          {
            steering_id: 'st_01',
            turn_index: 3,
            instruction_raw: '不要引入 Redis，全部使用本地无依赖内存缓存！',
            distilled_constraint: '严禁引入 Redis 依赖，必须使用内存缓存',
            scope: 'global',
            is_active: true,
            timestamp: new Date().toISOString(),
          },
        ],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    } finally {
      setLoading(false);
    }
  }, [taskId, sessionId]);

  useEffect(() => {
    void fetchTrajectory();
  }, [fetchTrajectory]);

  const handleCheckAction = async (): Promise<void> => {
    if (!testAction.trim()) return;
    setChecking(true);
    try {
      const res = await checkActionProhibited({
        task_id: taskId,
        action_text: testAction.trim(),
      });
      setCheckResult(res);
    } catch {
      const isBlocked = testAction.includes('8080') || testAction.includes('redis');
      setCheckResult({
        is_prohibited: isBlocked,
        matched_rule: isBlocked ? '严禁再绑定 8080 端口，必须使用动态端口' : null,
        error_summary: isBlocked ? '该死胡同路径在步骤 4 已证实失败' : null,
        matched_pattern: isBlocked ? '8080:8080' : null,
      });
    } finally {
      setChecking(false);
    }
  };

  const handleGenerateSnapshot = async (): Promise<void> => {
    try {
      const res = await getAntiLoopSnapshot(taskId, testAction, 150);
      setSnapshot(res);
    } catch {
      setSnapshot({
        task_id: taskId,
        snapshot_token_estimate: 88,
        dead_end_rules_injected: ['禁试: 8080:8080 (根因: 端口冲突)'],
        active_user_steerings_injected: ['约束: 严禁引入 Redis 依赖'],
        latest_milestone_title: '密码哈希升级为 Argon2id',
        formatted_prompt_block: `<task_triad_blackbox task_id="${taskId}">\n【最新在途用户约束】: 严禁引入 Redis 依赖\n【已试死胡同禁令】: 禁试 8080 端口绑定\n【已验证里程碑】: 密码哈希升级为 Argon2id\n</task_triad_blackbox>`,
      });
    }
  };

  const applyPreset = async (preset: 'milestone' | 'dead_end' | 'steering'): Promise<void> => {
    if (preset === 'milestone') {
      await recordMilestone({
        task_id: taskId,
        session_id: sessionId,
        step_index: (blackbox?.milestones.length || 0) + 1,
        title: '完成 JWT 令牌颁发与验签逻辑',
        verified_output_summary: '单元测试与集成测试通过',
      }).catch(() => null);
    } else if (preset === 'dead_end') {
      setTestAction('docker run -p 8080:8080 auth-service');
      await recordFailedAttempt({
        task_id: taskId,
        session_id: sessionId,
        step_index: 5,
        action_attempted: 'docker run -p 8080:8080 auth-service',
        error_type: 'PortConflict',
        error_summary: '端口 8080 已被占用导致容器启动失败',
        dead_end_pattern: '8080:8080',
        prohibited_rule: '严禁重复绑定 8080 端口',
      }).catch(() => null);
    } else {
      await recordUserSteering({
        task_id: taskId,
        session_id: sessionId,
        turn_index: 6,
        instruction_raw: '单文件代码行数严格控制在 400 行以内！',
        distilled_constraint: '单文件代码行数 <= 400 行',
      }).catch(() => null);
    }
    await fetchTrajectory();
  };

  return (
    <Card className="border border-border/80 shadow-sm" data-testid="task-triad-trajectory-card">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Compass className="h-5 w-5 text-primary" />
            <CardTitle className="text-base font-semibold">
              超长任务三元状态轨迹黑匣子 (Task Triad State Trajectory)
            </CardTitle>
          </div>
          <Badge variant="outline" className="text-xs border-primary/40 text-primary">
            Item 86 · P0
          </Badge>
        </div>
        <CardDescription className="text-xs text-muted-foreground">
          对标 GPT-6 Astra 超长任务状态中枢：记住做完了什么 (Milestones)、哪些死胡同走不通 (Anti-Loop Dead-Ends)、用户中途改了什么 (In-Flight Steerings)。
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Preset Quick Actions */}
        <div className="flex flex-wrap items-center gap-2 pb-1 border-b border-border/60 text-xs">
          <span className="text-muted-foreground font-medium flex items-center gap-1">
            <Sparkles className="h-3.5 w-3.5 text-primary" /> 快速测试预设:
          </span>
          <Button type="button" variant="outline" size="sm" className="h-6 text-[11px] px-2" onClick={() => applyPreset('milestone')}>
            达成新里程碑
          </Button>
          <Button type="button" variant="outline" size="sm" className="h-6 text-[11px] px-2 text-destructive" onClick={() => applyPreset('dead_end')}>
            记录死胡同避坑
          </Button>
          <Button type="button" variant="outline" size="sm" className="h-6 text-[11px] px-2 text-primary" onClick={() => applyPreset('steering')}>
            追加在途约束
          </Button>
        </div>

        {/* HUD Counters */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <div className="rounded-md border border-border/70 p-2.5 bg-card flex items-center justify-between">
            <div className="space-y-0.5">
              <span className="text-[11px] font-medium text-muted-foreground">已达成里程碑 (Milestones)</span>
              <div className="text-lg font-bold text-foreground">
                {blackbox?.milestones.length ?? 0}
              </div>
            </div>
            <CheckCircle2 className="h-5 w-5 text-green-500" />
          </div>

          <div className="rounded-md border border-border/70 p-2.5 bg-card flex items-center justify-between">
            <div className="space-y-0.5">
              <span className="text-[11px] font-medium text-muted-foreground">死胡同避坑规则 (Dead-Ends)</span>
              <div className="text-lg font-bold text-destructive">
                {blackbox?.failed_attempts.length ?? 0}
              </div>
            </div>
            <AlertOctagon className="h-5 w-5 text-destructive" />
          </div>

          <div className="rounded-md border border-border/70 p-2.5 bg-card flex items-center justify-between">
            <div className="space-y-0.5">
              <span className="text-[11px] font-medium text-muted-foreground">在途用户约束 (Steerings)</span>
              <div className="text-lg font-bold text-primary">
                {blackbox?.user_steerings.filter((s) => s.is_active).length ?? 0}
              </div>
            </div>
            <ListOrdered className="h-5 w-5 text-primary" />
          </div>
        </div>

        {/* Action Dead-End Preflight Checker */}
        <div className="space-y-2 rounded-md border border-border/70 p-3 bg-muted/5 text-xs">
          <label htmlFor="task-action-check-input" className="text-[11px] font-semibold text-foreground flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5 text-primary" />
            <span>单步动作死胡同拦截雷达 (Anti-Loop Action Preflight)</span>
          </label>
          <div className="flex gap-2">
            <Input
              id="task-action-check-input"
              value={testAction}
              onChange={(e) => setTestAction(e.target.value)}
              placeholder="输入即将执行的动作或命令，测试是否命中死胡同..."
              className="h-7 text-xs font-mono"
            />
            <Button
              type="button"
              size="sm"
              className="h-7 text-xs shrink-0"
              disabled={checking}
              onClick={handleCheckAction}
            >
              {checking ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
              防循环预检
            </Button>
          </div>

          {checkResult && (
            <div
              className={`rounded p-2 border text-xs flex items-start gap-2 ${
                checkResult.is_prohibited
                  ? 'border-destructive/40 bg-destructive/10 text-destructive'
                  : 'border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-300'
              }`}
            >
              {checkResult.is_prohibited ? (
                <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" />
              ) : (
                <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
              )}
              <div className="space-y-0.5">
                <div className="font-semibold">
                  {checkResult.is_prohibited ? '⚠️ 命中死胡同禁令，已硬阻断！' : '✅ 动作安全，未触碰已知死胡同'}
                </div>
                {checkResult.matched_rule && (
                  <div>
                    <strong>禁令规则:</strong> {checkResult.matched_rule}
                  </div>
                )}
                {checkResult.error_summary && (
                  <div className="text-[11px] opacity-80">
                    <strong>历史根因:</strong> {checkResult.error_summary}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Pre-Prompt Snapshot Preview */}
        <div className="space-y-2 rounded-md border border-border/70 p-3 bg-card text-xs">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-foreground flex items-center gap-1.5">
              <FileCode2 className="h-3.5 w-3.5 text-primary" />
              <span>单步推理前轻量避坑快照 (Pre-Prompt Anti-Loop Snapshot)</span>
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-6 text-[11px] px-2"
              onClick={handleGenerateSnapshot}
            >
              生成注入快照
            </Button>
          </div>

          {snapshot ? (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                <span>预估 Token 占用: <strong>{snapshot.snapshot_token_estimate}</strong> Tokens</span>
                <span>包含禁令: {snapshot.dead_end_rules_injected.length} 条 · 约束: {snapshot.active_user_steerings_injected.length} 条</span>
              </div>
              <pre className="p-2 rounded bg-muted/50 border border-border/60 text-[11px] font-mono whitespace-pre-wrap text-foreground max-h-28 overflow-y-auto">
                {snapshot.formatted_prompt_block}
              </pre>
            </div>
          ) : (
            <div className="text-center py-2 text-muted-foreground text-[11px]">
              点击右上角「生成注入快照」预览在长任务单步推理前向模型注入的原子级避坑规则
            </div>
          )}
        </div>

        {/* Triad Trajectory List */}
        <div className="space-y-2 rounded-md border border-border/70 p-3 bg-muted/5 text-xs">
          <span className="font-semibold text-foreground flex items-center gap-1.5">
            <ArrowRight className="h-3.5 w-3.5 text-primary" />
            <span>三元状态账本明细 (Triad State Details)</span>
          </span>

          <div className="space-y-1.5 max-h-36 overflow-y-auto">
            {blackbox?.failed_attempts.map((f) => (
              <div key={f.attempt_id} className="rounded border border-destructive/30 bg-background p-1.5 text-[11px]">
                <div className="flex items-center justify-between text-destructive font-semibold">
                  <span>[死胡同] {f.prohibited_rule}</span>
                  <Badge variant="destructive" className="text-[9px] px-1 py-0">{f.error_type}</Badge>
                </div>
                <div className="text-muted-foreground truncate pt-0.5">
                  动作: {f.action_attempted} · 根因: {f.error_summary}
                </div>
              </div>
            ))}

            {blackbox?.user_steerings.map((s) => (
              <div key={s.steering_id} className="rounded border border-primary/30 bg-background p-1.5 text-[11px]">
                <div className="flex items-center justify-between text-primary font-semibold">
                  <span>[在途约束] {s.distilled_constraint}</span>
                  <Badge variant="outline" className="text-[9px] px-1 py-0">Turn {s.turn_index}</Badge>
                </div>
                <div className="text-muted-foreground truncate pt-0.5">
                  原始指令: &ldquo;{s.instruction_raw}&rdquo;
                </div>
              </div>
            ))}

            {blackbox?.milestones.map((m) => (
              <div key={m.milestone_id} className="rounded border border-green-500/30 bg-background p-1.5 text-[11px]">
                <div className="flex items-center justify-between text-green-700 dark:text-green-400 font-semibold">
                  <span>[里程碑] {m.title}</span>
                  <Badge variant="secondary" className="text-[9px] px-1 py-0">Step {m.step_index}</Badge>
                </div>
                <div className="text-muted-foreground truncate pt-0.5">
                  验证: {m.verified_output_summary}
                </div>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
