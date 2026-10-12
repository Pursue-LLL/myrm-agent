'use client';

/**
 * [INPUT]
 * @/services/memory/jobCompounding::CompoundingMaturityReportDTO, CompoundedRuleDTO, CheckApprovalResponseDTO
 *
 * [OUTPUT]
 * CompoundingMaturityView: Subcomponent displaying maturity growth tiers, rule ledgers, and approval checks.
 *
 * [POS]
 * Subcomponent for Item 90 (Domain-Specific Agent Job Description and Preference Compounding Suite).
 * Strict typing applied: No `any` types allowed.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Award, ShieldAlert, CheckCircle2, TrendingUp, Plus, ShieldCheck } from 'lucide-react';
import type {
  CompoundingMaturityReportDTO,
  CompoundedRuleDTO,
  RecordRuleRequestDTO,
  CheckApprovalResponseDTO,
} from '@/services/memory/jobCompounding';

interface CompoundingMaturityViewProps {
  maturity: CompoundingMaturityReportDTO | null;
  rules: CompoundedRuleDTO[];
  onRecordRule: (rule: RecordRuleRequestDTO) => Promise<void>;
  onCheckApproval: (actionName: string) => Promise<CheckApprovalResponseDTO>;
}

export function CompoundingMaturityView({
  maturity,
  rules,
  onRecordRule,
  onCheckApproval,
}: CompoundingMaturityViewProps): React.JSX.Element {
  const [newStatement, setNewStatement] = useState<string>('');
  const [newRuleType, setNewRuleType] = useState<string>('positive_preference');
  const [actionToCheck, setActionToCheck] = useState<string>('');
  const [approvalResult, setApprovalResult] = useState<CheckApprovalResponseDTO | null>(null);
  const [isChecking, setIsChecking] = useState<boolean>(false);

  const handleAddRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newStatement.trim()) return;

    await onRecordRule({
      agent_id: maturity?.agent_id ?? 'agent_talent_scout_01',
      rule_type: newRuleType,
      statement: newStatement.trim(),
      trigger_condition: 'on_domain_task_execution',
      evidence_source: 'human_feedback_alignment',
    });
    setNewStatement('');
  };

  const handleVerifyApproval = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!actionToCheck.trim()) return;
    setIsChecking(true);
    try {
      const res = await onCheckApproval(actionToCheck.trim());
      setApprovalResult(res);
    } finally {
      setIsChecking(false);
    }
  };

  const score = maturity?.maturity_score ?? 15.0;
  const tier = maturity?.tier ?? 'rookie';

  return (
    <div className="space-y-3" data-testid="compounding-maturity-view">
      {/* Maturity Progress Ladder Banner */}
      <div className="rounded-md border border-border/70 p-3 bg-card space-y-2">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-xs">
          <div className="flex items-center gap-1.5 font-semibold text-foreground">
            <Award className="h-4 w-4 text-amber-500" />
            <span>岗位经验复利成熟度评估</span>
            <Badge variant="secondary" className="text-[10px] uppercase font-bold" data-testid="maturity-tier-badge">
              {tier}
            </Badge>
          </div>
          <div className="text-[11px] text-muted-foreground flex items-center gap-2">
            <span>成熟度得分:</span>
            <span className="font-bold text-primary text-sm" data-testid="maturity-score-text">
              {score.toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="w-full bg-muted/60 rounded-full h-2 overflow-hidden">
          <div
            className="bg-primary h-2 rounded-full transition-all duration-500"
            style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
            data-testid="maturity-progress-bar"
          />
        </div>

        {/* 4 Tier Milestones */}
        <div className="grid grid-cols-4 text-[10px] text-center text-muted-foreground pt-0.5">
          <div className={tier === 'rookie' ? 'text-primary font-bold' : ''}>Rookie (0-25%)</div>
          <div className={tier === 'practitioner' ? 'text-primary font-bold' : ''}>Practitioner (26-60%)</div>
          <div className={tier === 'specialist' ? 'text-primary font-bold' : ''}>Specialist (61-85%)</div>
          <div className={tier === 'partner' ? 'text-primary font-bold' : ''}>Partner (86-100%)</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Rules Ledger and New Rule Formulation */}
        <div className="rounded-md border border-border/70 p-2.5 bg-card space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold text-foreground">
            <span className="flex items-center gap-1">
              <TrendingUp className="h-3.5 w-3.5 text-green-500" />
              <span>已沉淀领域规则 ({rules.length})</span>
            </span>
            <span className="text-[10px] text-muted-foreground">物理写入 MEMORY.md</span>
          </div>

          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {rules.length > 0 ? (
              rules.map((r) => (
                <div
                  key={r.rule_id}
                  className="rounded border border-border/50 p-2 bg-background text-xs space-y-1"
                  data-testid={`rule-item-${r.rule_id}`}
                >
                  <div className="flex items-center justify-between gap-1">
                    <span className="font-medium text-foreground truncate">{r.statement}</span>
                    <Badge variant="outline" className="text-[9px] py-0 px-1 shrink-0">
                      {r.rule_type === 'positive_preference'
                        ? '正向偏好'
                        : r.rule_type === 'negative_constraint'
                        ? '禁忌负例'
                        : '排查经验'}
                    </Badge>
                  </div>
                  <div className="text-[10px] text-muted-foreground flex justify-between">
                    <span>触发: {r.trigger_condition}</span>
                    <span>命中: {r.hit_count} 次</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-4 text-muted-foreground text-xs">
                暂未沉淀领域规则，可通过下方表单或任务反馈累积
              </div>
            )}
          </div>

          <form onSubmit={handleAddRule} className="flex gap-1.5 pt-1" data-testid="add-rule-form">
            <select
              aria-label="规则类型"
              value={newRuleType}
              onChange={(e) => setNewRuleType(e.target.value)}
              className="rounded border border-input bg-background px-2 py-1 text-xs shrink-0"
              data-testid="rule-type-select"
            >
              <option value="positive_preference">正向偏好</option>
              <option value="negative_constraint">禁忌负例</option>
              <option value="inspection_lesson">排查教训</option>
            </select>
            <input
              type="text"
              placeholder="沉淀一条领域经验规则..."
              value={newStatement}
              onChange={(e) => setNewStatement(e.target.value)}
              className="flex-1 rounded border border-input bg-background px-2 py-1 text-xs"
              data-testid="rule-statement-input"
            />
            <Button type="submit" size="sm" className="h-7 text-xs px-2 gap-1 shrink-0" data-testid="submit-rule-btn">
              <Plus className="h-3 w-3" />
              沉淀
            </Button>
          </form>
        </div>

        {/* Approval Boundary Simulator */}
        <div className="rounded-md border border-border/70 p-2.5 bg-card flex flex-col justify-between space-y-2">
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <span>审批边界试运行模拟器 (Gate Simulator)</span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              输入即将执行的动作或工具调用，即时测试第四要素审批边界裁决结果。
            </p>

            <form onSubmit={handleVerifyApproval} className="flex gap-1.5 pt-1" data-testid="check-approval-form">
              <input
                type="text"
                placeholder="例如: send_interview_invite 或 scan_resumes"
                value={actionToCheck}
                onChange={(e) => setActionToCheck(e.target.value)}
                className="flex-1 rounded border border-input bg-background px-2.5 py-1 text-xs"
                data-testid="action-check-input"
              />
              <Button type="submit" size="sm" variant="secondary" disabled={isChecking} className="h-7 text-xs" data-testid="check-approval-btn">
                {isChecking ? '校验中...' : '校验边界'}
              </Button>
            </form>
          </div>

          {approvalResult && (
            <div
              className={`rounded border p-2 text-xs space-y-0.5 ${
                approvalResult.needs_approval
                  ? 'border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-200'
                  : 'border-green-500/40 bg-green-500/10 text-green-900 dark:text-green-200'
              }`}
              data-testid="approval-result-card"
            >
              <div className="flex items-center gap-1 font-semibold">
                {approvalResult.needs_approval ? (
                  <>
                    <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
                    <span>【阻断】需人工董事长审批</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                    <span>【放行】属于自主执行边界</span>
                  </>
                )}
              </div>
              <div className="text-[11px] opacity-90">{approvalResult.reason}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
