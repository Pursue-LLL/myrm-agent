/**
 * [INPUT]
 * - @/services/memory/fourLayerPromotion: listActiveCapabilityMethods, verifyRulesCompliance, rollbackConsolidationBatch
 * - @/services/memory/fourLayerPromotion: CapabilityMethodSchema, RulesComplianceItemSchema
 * - @/components/primitives: Card, Button, Badge, Input
 *
 * [OUTPUT]
 * - FourLayerPromotionAuditCard: React container rendering 4-layer memory hierarchy,
 *   promoted capability methods, evidence anchors, compliance contract checker, and atomic rollback.
 *
 * [POS]
 * Personal Brain Command Center governance card enforcing Hermes-grade four-layer promotion
 * and E->M->B anti-poisoning audit. Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  GitBranch,
  Layers,
  Loader2,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Wrench,
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
  type CapabilityMethodSchema,
  listActiveCapabilityMethods,
  rollbackConsolidationBatch,
  type RulesComplianceItemSchema,
  verifyRulesCompliance,
} from '@/services/memory/fourLayerPromotion';

interface FourLayerPromotionAuditCardProps {
  className?: string;
}

function getChannelBadge(channel: string): { label: string; className: string } {
  switch (channel) {
    case 'tool_failure_evidence':
      return { label: '工具失败断言 (FAILURE)', className: 'bg-rose-600 text-white' };
    case 'repeated_across_sessions':
      return { label: '跨会话重复 (REPEATED)', className: 'bg-blue-600 text-white' };
    case 'explicit_user_instruction':
      return { label: '用户显式指令 (DIRECTIVE)', className: 'bg-emerald-600 text-white' };
    default:
      return { label: channel, className: 'bg-secondary text-secondary-foreground' };
  }
}

export function FourLayerPromotionAuditCard({ className }: FourLayerPromotionAuditCardProps) {
  const [methods, setMethods] = useState<CapabilityMethodSchema[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [rollbackBatchId, setRollbackBatchId] = useState('');
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [testResponseText, setTestResponseText] = useState('');
  const [isCheckingCompliance, setIsCheckingCompliance] = useState(false);
  const [complianceResults, setComplianceResults] = useState<RulesComplianceItemSchema[] | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const fetchMethods = useCallback(async (clearStatus = true) => {
    setIsLoading(true);
    if (clearStatus) {
      setStatusMessage(null);
    }
    try {
      const data = await listActiveCapabilityMethods();
      setMethods(data);
    } catch {
      setStatusMessage('加载四层记忆方法卡失败，请检查网络或后端服务');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchMethods();
  }, [fetchMethods]);

  const handleRollback = async () => {
    if (!rollbackBatchId.trim()) return;
    setIsRollingBack(true);
    setStatusMessage(null);
    try {
      const res = await rollbackConsolidationBatch({ batch_id: rollbackBatchId.trim() });
      if (res.success) {
        setStatusMessage(`原子回滚成功，撤销 ${res.reverted_method_ids.length} 个方法卡`);
        setRollbackBatchId('');
        void fetchMethods(false);
      } else {
        setStatusMessage('回滚失败，批次可能已回滚或不存在');
      }
    } catch {
      setStatusMessage('回滚操作异常，请检查后端状态');
    } finally {
      setIsRollingBack(false);
    }
  };

  const handleVerifyCompliance = async () => {
    if (!testResponseText.trim()) return;
    setIsCheckingCompliance(true);
    try {
      const res = await verifyRulesCompliance({ response_text: testResponseText.trim() });
      setComplianceResults(res.items);
    } catch {
      setStatusMessage('规则遵守契约核验失败');
    } finally {
      setIsCheckingCompliance(false);
    }
  };

  return (
    <Card className={cn('w-full border border-border shadow-sm', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" />
            <div>
              <CardTitle className="text-base font-semibold">
                四层记忆晋升与防静默污染审计 (Four-Layer Promotion Audit)
              </CardTitle>
              <CardDescription className="text-xs">
                Raw → Consolidated → Semantic → CapabilityMethod 两步压缩，代码级三通道断言晋升，防 E➔M➔B 静默污染
              </CardDescription>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void fetchMethods()}
            disabled={isLoading}
            className="h-8 gap-1 px-2.5 text-xs"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')} />
            刷新
          </Button>
        </div>
        {statusMessage && (
          <div className="mt-2 rounded-md bg-secondary/50 px-2.5 py-1.5 text-xs text-muted-foreground">
            {statusMessage}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-4 pt-1">
        {/* Four-Layer Architecture Overview */}
        <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <div className="rounded-md border border-border/70 bg-accent/20 p-2">
            <div className="font-semibold text-foreground">1. Working</div>
            <div className="text-[11px] text-muted-foreground">会话活跃内存</div>
          </div>
          <div className="rounded-md border border-border/70 bg-accent/20 p-2">
            <div className="font-semibold text-foreground">2. Raw Episodic</div>
            <div className="text-[11px] text-muted-foreground">单会话事件流水</div>
          </div>
          <div className="rounded-md border border-border/70 bg-accent/20 p-2">
            <div className="font-semibold text-foreground">3. Consolidated</div>
            <div className="text-[11px] text-muted-foreground">Map-Reduce 候选提炼</div>
          </div>
          <div className="rounded-md border border-border/70 bg-primary/10 p-2">
            <div className="font-semibold text-primary">4. Method Card</div>
            <div className="text-[11px] text-primary/80">三通道硬断言晋升</div>
          </div>
        </div>

        {/* Active Promoted Capability Methods */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <Wrench className="h-4 w-4 text-primary" />
              当前生效的能力方法卡 (Active Capability Methods: {methods.length})
            </span>
          </div>

          {methods.length === 0 && !isLoading && (
            <div className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
              暂无已晋升的能力方法卡。工具真实失败或跨会话重复沉淀后将自动通过代码门禁晋升入库。
            </div>
          )}

          <div className="max-h-60 space-y-2 overflow-y-auto pr-1">
            {methods.map((method) => {
              const badge = getChannelBadge(method.promotion_channel);
              return (
                <div
                  key={method.method_id}
                  className="rounded-lg border border-border/80 bg-background/50 p-3 text-xs space-y-1.5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-1.5">
                    <span className="font-semibold text-foreground">{method.title}</span>
                    <Badge className={cn('text-[10px] px-1.5 py-0', badge.className)}>
                      {badge.label}
                    </Badge>
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    <span className="font-medium text-foreground">适用场景: </span>
                    {method.applies_when}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    <span className="font-medium text-foreground">核心步骤: </span>
                    {method.method_steps.join(' ➔ ')}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 pt-0.5 text-[10px] text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <GitBranch className="h-3 w-3" />
                      证据事件: {method.supported_event_ids.join(', ') || '无'}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <ShieldCheck className="h-3 w-3 text-emerald-600" />
                      准则: {method.validation_criteria}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Structured Rules Compliance Verification */}
        <div className="rounded-lg border border-dashed border-border bg-muted/20 p-3 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
            <ShieldAlert className="h-3.5 w-3.5 text-primary" />
            <span>结构化契约遵守核验 (Rules Compliance Contract Checker)</span>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              className="h-8 text-xs font-mono"
              placeholder="输入待核验回复（例如：'兵马俑与回民街同日安排' 或 '已预先检查400行限制'）"
              value={testResponseText}
              onChange={(e) => setTestResponseText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void handleVerifyCompliance();
                }
              }}
            />
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void handleVerifyCompliance()}
              disabled={isCheckingCompliance || !testResponseText.trim()}
              className="h-8 shrink-0 text-xs gap-1"
            >
              {isCheckingCompliance ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <ShieldCheck className="h-3.5 w-3.5" />
              )}
              核验契约
            </Button>
          </div>

          {complianceResults && (
            <div className="space-y-1.5 pt-1">
              {complianceResults.map((item) => (
                <div
                  key={item.rule_id}
                  className={cn(
                    'flex items-start gap-2 rounded-md p-2 text-xs',
                    item.compliant
                      ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                      : 'bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300',
                  )}
                >
                  {item.compliant ? (
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
                  ) : (
                    <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-600 dark:text-rose-400" />
                  )}
                  <div className="space-y-0.5">
                    <div className="font-medium">
                      {item.compliant ? '契约遵守通过' : '违反规则契约'}: {item.statement}
                    </div>
                    <div className="text-[11px] opacity-90">{item.rationale}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* E->M->B Anti-Poisoning Atomic Rollback */}
        <div className="flex flex-col gap-2 rounded-lg border border-border bg-background/50 p-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-0.5">
            <div className="text-xs font-semibold text-foreground">
              E➔M➔B 污染一键回滚 (Anti-Poisoning Rollback)
            </div>
            <div className="text-[11px] text-muted-foreground">
              当发现外部不可信暴露污染时，输入整理批次号执行原子撤销
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Input
              className="h-8 w-44 text-xs font-mono"
              placeholder="批次号 (batch-xxxx)"
              value={rollbackBatchId}
              onChange={(e) => setRollbackBatchId(e.target.value)}
            />
            <Button
              variant="destructive"
              size="sm"
              onClick={() => void handleRollback()}
              disabled={isRollingBack || !rollbackBatchId.trim()}
              className="h-8 gap-1 text-xs shrink-0"
            >
              {isRollingBack ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RotateCcw className="h-3.5 w-3.5" />
              )}
              原子回滚
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
export default FourLayerPromotionAuditCard;
