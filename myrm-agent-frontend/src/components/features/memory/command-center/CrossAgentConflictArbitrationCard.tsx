/**
 * [INPUT]
 * - @/services/memory/crossAgent: arbitrateMemoryConflict, projectComposableContext, sealTaskHandoff, verifyTaskHandoff
 * - @/components/primitives/card: Card, CardContent, CardDescription, CardHeader, CardTitle
 * - @/components/primitives/tabs: Tabs, TabsContent, TabsList, TabsTrigger
 * - @/components/primitives/input: Input
 * - @/components/primitives/button: Button
 * - @/components/primitives/textarea: Textarea
 * - @/components/primitives/badge: Badge
 * - @/components/features/memory/command-center/ComposableContextProjectionView: ComposableContextProjectionView
 *
 * [OUTPUT]
 * - CrossAgentConflictArbitrationCard: Main command center card for cross-agent composable context & conflict arbitration.
 *
 * [POS]
 * Command center card mounted in Memory CommandCenter UnderstandSection.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Cpu,
  FileCheck2,
  GitFork,
  HelpCircle,
  KeyRound,
  Layers,
  Loader2,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
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
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/primitives/tabs';
import { Textarea } from '@/components/primitives/textarea';
import { ComposableContextProjectionView } from './ComposableContextProjectionView';
import {
  arbitrateMemoryConflict,
  projectComposableContext,
  sealTaskHandoff,
  verifyTaskHandoff,
  type ArbitrationOutcomeDTO,
  type ComposableContextResponseDTO,
  type HandoffPacketDTO,
  type HandoffVerificationResponseDTO,
} from '@/services/memory/crossAgent';

export function CrossAgentConflictArbitrationCard() {
  const [activeTab, setActiveTab] = useState<'arbitration' | 'projection' | 'handoff'>('arbitration');

  // Tab 1: Conflict Arbitration State
  const [subject, setSubject] = useState('database_backend');
  const [predicate, setPredicate] = useState('uses');
  const [agentAId, setAgentAId] = useState('coder_agent');
  const [valA, setValA] = useState('sqlite');
  const [confA, setConfA] = useState('0.9');
  const [agentBId, setAgentBId] = useState('architect_agent');
  const [valB, setValB] = useState('postgres');
  const [confB, setConfB] = useState('0.9');
  const [workspaceRoot, setWorkspaceRoot] = useState('');
  const [arbitrationResult, setArbitrationResult] = useState<ArbitrationOutcomeDTO | null>(null);
  const [arbitrationLoading, setArbitrationLoading] = useState(false);
  const [humanConfirmedWinner, setHumanConfirmedWinner] = useState<string | null>(null);

  // Tab 2: Composable Context Projection State
  const [projAgentId, setProjAgentId] = useState('subagent_worker_1');
  const [sessionId, setSessionId] = useState('session_coord_99');
  const [tokenBudget, setTokenBudget] = useState('4096');
  const [scratchpad, setScratchpad] = useState('Private note: analyzing AST parsing performance');
  const [projectionResult, setProjectionResult] = useState<ComposableContextResponseDTO | null>(null);
  const [projectionLoading, setProjectionLoading] = useState(false);

  // Tab 3: Handoff Integrity State
  const [sourceAgent, setSourceAgent] = useState('agent_planner');
  const [targetAgent, setTargetAgent] = useState('agent_executor');
  const [taskId, setTaskId] = useState('task_refactor_module');
  const [contextSnapshot, setContextSnapshot] = useState('Refactored core mixins. All unit tests passed.');
  const [sealedPacket, setSealedPacket] = useState<HandoffPacketDTO | null>(null);
  const [verificationResult, setVerificationResult] = useState<HandoffVerificationResponseDTO | null>(null);
  const [handoffLoading, setHandoffLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const handleArbitrate = async () => {
    setArbitrationLoading(true);
    setError(null);
    setHumanConfirmedWinner(null);
    try {
      const outcome = await arbitrateMemoryConflict({
        subject,
        predicate,
        assertion_a: {
          assertion_id: `ast-${agentAId}`,
          subject,
          predicate,
          object_value: valA,
          confidence: parseFloat(confA) || 0.8,
          source_agent_id: agentAId,
        },
        assertion_b: {
          assertion_id: `ast-${agentBId}`,
          subject,
          predicate,
          object_value: valB,
          confidence: parseFloat(confB) || 0.8,
          source_agent_id: agentBId,
        },
        workspace_root: workspaceRoot.trim() || null,
      });
      setArbitrationResult(outcome);
    } catch (err) {
      setError(err instanceof Error ? err.message : '仲裁探测请求失败');
    } finally {
      setArbitrationLoading(false);
    }
  };

  const handleProjectContext = async () => {
    setProjectionLoading(true);
    setError(null);
    try {
      const result = await projectComposableContext({
        agent_id: projAgentId,
        session_id: sessionId,
        global_ground_truth: ['Core repo uses Python 3.13', 'Database backend is SQLite'],
        profile_tools_memory: ['Role: Senior Full-Stack Engineer', 'Tools: pytest, ruff'],
        private_scratchpad: scratchpad,
        token_budget: parseInt(tokenBudget, 10) || 4096,
      });
      setProjectionResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '上下文投影生成失败');
    } finally {
      setProjectionLoading(false);
    }
  };

  const handleSealHandoff = async () => {
    setHandoffLoading(true);
    setError(null);
    setVerificationResult(null);
    try {
      const packet = await sealTaskHandoff({
        source_agent_id: sourceAgent,
        target_agent_id: targetAgent,
        task_id: taskId,
        context_snapshot: contextSnapshot,
        critical_assertions: [
          {
            assertion_id: 'ast-task-target',
            subject: 'task_target',
            predicate: 'is',
            object_value: 'refactor_completed',
            confidence: 1.0,
            source_agent_id: sourceAgent,
          },
        ],
        secret_salt: 'myrm-salt-coord',
      });
      setSealedPacket(packet);
    } catch (err) {
      setError(err instanceof Error ? err.message : '任务移交加签失败');
    } finally {
      setHandoffLoading(false);
    }
  };

  const handleVerifyHandoff = async () => {
    if (!sealedPacket) return;
    setHandoffLoading(true);
    setError(null);
    try {
      const res = await verifyTaskHandoff({
        packet: sealedPacket,
        secret_salt: 'myrm-salt-coord',
      });
      setVerificationResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : '移交验签请求失败');
    } finally {
      setHandoffLoading(false);
    }
  };

  return (
    <Card className="w-full border-border/80 shadow-sm">
      <CardHeader className="space-y-1 pb-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Scale className="h-5 w-5 text-primary" />
            <CardTitle className="text-base font-semibold">
              跨智能体可组合上下文隔离与分歧仲裁套件
            </CardTitle>
          </div>
          <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary text-xs">
            Item 177 • P0 资产
          </Badge>
        </div>
        <CardDescription className="text-xs text-muted-foreground">
          4层物理上下文隔离投影 (80%+ KV Cache 保护) • 3级梯队分歧确定性仲裁探针 • 跨智能体移交包防篡改验签
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <Tabs value={activeTab} onValueChange={(val: string) => setActiveTab(val as typeof activeTab)}>
          <TabsList className="grid grid-cols-3 mb-4">
            <TabsTrigger
              value="arbitration"
              onClick={() => setActiveTab('arbitration')}
              className="flex items-center gap-1.5 text-xs"
            >
              <Scale className="h-3.5 w-3.5" /> 事实分歧仲裁
            </TabsTrigger>
            <TabsTrigger
              value="projection"
              onClick={() => setActiveTab('projection')}
              className="flex items-center gap-1.5 text-xs"
            >
              <Layers className="h-3.5 w-3.5" /> 4层可组合投影
            </TabsTrigger>
            <TabsTrigger
              value="handoff"
              onClick={() => setActiveTab('handoff')}
              className="flex items-center gap-1.5 text-xs"
            >
              <FileCheck2 className="h-3.5 w-3.5" /> 任务移交验签
            </TabsTrigger>
          </TabsList>

          {/* TAB 1: 事实分歧仲裁 */}
          <TabsContent value="arbitration" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div>
                <label htmlFor="cross-agent-subject-input" className="font-medium text-foreground block mb-1">
                  争议实体/主题 (Subject)
                </label>
                <Input
                  id="cross-agent-subject-input"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="e.g. database_backend"
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div>
                <label htmlFor="cross-agent-predicate-input" className="font-medium text-foreground block mb-1">
                  关系/谓词 (Predicate)
                </label>
                <Input
                  id="cross-agent-predicate-input"
                  value={predicate}
                  onChange={(e) => setPredicate(e.target.value)}
                  placeholder="e.g. uses"
                  className="h-8 text-xs font-mono"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-3 rounded-lg border border-border/60 bg-muted/20 text-xs">
              <div className="space-y-2">
                <span className="font-semibold text-primary block">智能体 A 主张</span>
                <div>
                  <label htmlFor="cross-agent-agent-a-id" className="text-muted-foreground block mb-0.5">
                    Agent A ID
                  </label>
                  <Input
                    id="cross-agent-agent-a-id"
                    value={agentAId}
                    onChange={(e) => setAgentAId(e.target.value)}
                    className="h-7 text-xs font-mono"
                  />
                </div>
                <div>
                  <label htmlFor="cross-agent-agent-a-val" className="text-muted-foreground block mb-0.5">
                    主张值 (Value)
                  </label>
                  <Input
                    id="cross-agent-agent-a-val"
                    value={valA}
                    onChange={(e) => setValA(e.target.value)}
                    className="h-7 text-xs font-mono"
                  />
                </div>
                <div>
                  <label htmlFor="cross-agent-agent-a-conf" className="text-muted-foreground block mb-0.5">
                    置信度 (0.0 - 1.0)
                  </label>
                  <Input
                    id="cross-agent-agent-a-conf"
                    value={confA}
                    onChange={(e) => setConfA(e.target.value)}
                    className="h-7 text-xs font-mono"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <span className="font-semibold text-purple-600 dark:text-purple-400 block">智能体 B 主张</span>
                <div>
                  <label htmlFor="cross-agent-agent-b-id" className="text-muted-foreground block mb-0.5">
                    Agent B ID
                  </label>
                  <Input
                    id="cross-agent-agent-b-id"
                    value={agentBId}
                    onChange={(e) => setAgentBId(e.target.value)}
                    className="h-7 text-xs font-mono"
                  />
                </div>
                <div>
                  <label htmlFor="cross-agent-agent-b-val" className="text-muted-foreground block mb-0.5">
                    主张值 (Value)
                  </label>
                  <Input
                    id="cross-agent-agent-b-val"
                    value={valB}
                    onChange={(e) => setValB(e.target.value)}
                    className="h-7 text-xs font-mono"
                  />
                </div>
                <div>
                  <label htmlFor="cross-agent-agent-b-conf" className="text-muted-foreground block mb-0.5">
                    置信度 (0.0 - 1.0)
                  </label>
                  <Input
                    id="cross-agent-agent-b-conf"
                    value={confB}
                    onChange={(e) => setConfB(e.target.value)}
                    className="h-7 text-xs font-mono"
                  />
                </div>
              </div>
            </div>

            <div>
              <label htmlFor="cross-agent-workspace-root-input" className="font-medium text-foreground text-xs block mb-1">
                工作区物理探测根目录 (可选，空则使用默认配置)
              </label>
              <Input
                id="cross-agent-workspace-root-input"
                value={workspaceRoot}
                onChange={(e) => setWorkspaceRoot(e.target.value)}
                placeholder="/path/to/workspace"
                className="h-8 text-xs font-mono"
              />
            </div>

            <Button
              onClick={handleArbitrate}
              disabled={arbitrationLoading}
              className="w-full text-xs"
            >
              {arbitrationLoading ? (
                <>
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  正在执行3级梯队仲裁探测...
                </>
              ) : (
                <>
                  <Scale className="mr-1.5 h-3.5 w-3.5" />
                  启动多模型分歧仲裁探针
                </>
              )}
            </Button>

            {arbitrationResult && (
              <div className="rounded-lg border border-border bg-card p-3.5 space-y-3 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2">
                  <span className="font-semibold text-foreground">仲裁探针报告</span>
                  <Badge
                    variant="outline"
                    className={
                      arbitrationResult.resolved
                        ? 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'
                        : 'border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10'
                    }
                  >
                    {arbitrationResult.resolved ? '分歧已确定性裁决' : '对称僵局，待人工终审'}
                  </Badge>
                </div>

                <div className="space-y-1.5">
                  <div className="text-muted-foreground">
                    执行策略: <span className="font-mono text-foreground font-semibold">{arbitrationResult.policy_applied}</span>
                  </div>
                  <div className="text-muted-foreground">
                    采纳事实: <span className="font-mono text-foreground font-semibold">{humanConfirmedWinner || arbitrationResult.winning_assertion.object_value}</span> (来源: {arbitrationResult.winning_assertion.source_agent_id})
                  </div>
                  <div className="rounded bg-muted/30 p-2 font-mono text-[11px] text-foreground/90 whitespace-pre-wrap">
                    {arbitrationResult.audit_rationale}
                  </div>
                </div>

                {arbitrationResult.requires_human_confirmation && !humanConfirmedWinner && (
                  <div className="rounded border border-amber-500/30 bg-amber-500/10 p-2.5 space-y-2">
                    <span className="font-medium text-amber-600 dark:text-amber-400 block">
                      ⚠️ 需人工介入确认 (1-Click Confirmation):
                    </span>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setHumanConfirmedWinner(valA)}
                        className="text-xs h-7"
                      >
                        确认采纳 Agent A ({valA})
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setHumanConfirmedWinner(valB)}
                        className="text-xs h-7"
                      >
                        确认采纳 Agent B ({valB})
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </TabsContent>

          {/* TAB 2: 4层可组合上下文投影 */}
          <TabsContent value="projection" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <div>
                <label htmlFor="cross-agent-proj-agent-id" className="font-medium text-foreground block mb-1">
                  目标智能体 ID
                </label>
                <Input
                  id="cross-agent-proj-agent-id"
                  value={projAgentId}
                  onChange={(e) => setProjAgentId(e.target.value)}
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div>
                <label htmlFor="cross-agent-proj-session-id" className="font-medium text-foreground block mb-1">
                  协调会话 ID
                </label>
                <Input
                  id="cross-agent-proj-session-id"
                  value={sessionId}
                  onChange={(e) => setSessionId(e.target.value)}
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div>
                <label htmlFor="cross-agent-proj-token-budget" className="font-medium text-foreground block mb-1">
                  Token 预算上限
                </label>
                <Input
                  id="cross-agent-proj-token-budget"
                  value={tokenBudget}
                  onChange={(e) => setTokenBudget(e.target.value)}
                  className="h-8 text-xs font-mono"
                />
              </div>
            </div>

            <div>
              <label htmlFor="cross-agent-proj-scratchpad" className="font-medium text-foreground text-xs block mb-1">
                私有草稿纸内容 (Layer 1 Scratchpad，对其他 Agent 严格物理隔离)
              </label>
              <Textarea
                id="cross-agent-proj-scratchpad"
                value={scratchpad}
                onChange={(e) => setScratchpad(e.target.value)}
                rows={2}
                className="text-xs font-mono resize-none"
              />
            </div>

            <Button
              onClick={handleProjectContext}
              disabled={projectionLoading}
              className="w-full text-xs"
            >
              {projectionLoading ? (
                <>
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  正在计算4层虚拟引用投影...
                </>
              ) : (
                <>
                  <Layers className="mr-1.5 h-3.5 w-3.5" />
                  组装可组合上下文投影
                </>
              )}
            </Button>

            {projectionResult && (
              <ComposableContextProjectionView projection={projectionResult} />
            )}
          </TabsContent>

          {/* TAB 3: 移交包加签与验签 */}
          <TabsContent value="handoff" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <div>
                <label htmlFor="cross-agent-handoff-source" className="font-medium text-foreground block mb-1">
                  发送方 Agent
                </label>
                <Input
                  id="cross-agent-handoff-source"
                  value={sourceAgent}
                  onChange={(e) => setSourceAgent(e.target.value)}
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div>
                <label htmlFor="cross-agent-handoff-target" className="font-medium text-foreground block mb-1">
                  接收方 Agent
                </label>
                <Input
                  id="cross-agent-handoff-target"
                  value={targetAgent}
                  onChange={(e) => setTargetAgent(e.target.value)}
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div>
                <label htmlFor="cross-agent-handoff-task-id" className="font-medium text-foreground block mb-1">
                  移交任务 ID
                </label>
                <Input
                  id="cross-agent-handoff-task-id"
                  value={taskId}
                  onChange={(e) => setTaskId(e.target.value)}
                  className="h-8 text-xs font-mono"
                />
              </div>
            </div>

            <div>
              <label htmlFor="cross-agent-handoff-snapshot" className="font-medium text-foreground text-xs block mb-1">
                任务上下文快照 (Findings, Vetoed routes, State)
              </label>
              <Textarea
                id="cross-agent-handoff-snapshot"
                value={contextSnapshot}
                onChange={(e) => setContextSnapshot(e.target.value)}
                rows={2}
                className="text-xs font-mono resize-none"
              />
            </div>

            <div className="flex gap-2">
              <Button
                onClick={handleSealHandoff}
                disabled={handoffLoading}
                className="flex-1 text-xs"
              >
                {handoffLoading ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <KeyRound className="mr-1.5 h-3.5 w-3.5" />
                )}
                生成 SHA-256 移交封签
              </Button>
              <Button
                onClick={handleVerifyHandoff}
                disabled={handoffLoading || !sealedPacket}
                variant="outline"
                className="flex-1 text-xs"
              >
                <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
                验证移交包签名
              </Button>
            </div>

            {sealedPacket && (
              <div className="rounded-lg border border-border bg-card p-3 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-foreground">封签移交包详情</span>
                  <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary text-[10px] font-mono">
                    ID: {sealedPacket.packet_id}
                  </Badge>
                </div>
                <div className="font-mono text-[11px] text-muted-foreground break-all">
                  SHA-256 签名: <span className="text-foreground">{sealedPacket.signature_sha256}</span>
                </div>
              </div>
            )}

            {verificationResult && (
              <div
                className={`rounded-lg border p-3 text-xs flex items-center justify-between ${
                  verificationResult.is_valid
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
                    : 'border-destructive/30 bg-destructive/10 text-destructive'
                }`}
              >
                <div className="flex items-center gap-2">
                  {verificationResult.is_valid ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0" />
                  ) : (
                    <ShieldAlert className="h-4 w-4 shrink-0" />
                  )}
                  <span>
                    {verificationResult.is_valid
                      ? `验签通过：完整性完好，验证了 ${verificationResult.verified_assertions_count} 条核心断言`
                      : `验签失败：${verificationResult.rejection_reason || '移交数据被篡改'}`}
                  </span>
                </div>
                <Badge variant="outline" className="text-[10px]">
                  {verificationResult.is_valid ? 'SECURE' : 'TAMPERED'}
                </Badge>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
