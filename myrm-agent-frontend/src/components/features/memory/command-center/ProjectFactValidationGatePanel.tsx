'use client';

import React from 'react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { ShieldCheck, Sparkles } from 'lucide-react';
import type { LivingFactDTO, ValidationAuditResponseDTO } from '@/services/projects/projectState';

interface ProjectFactValidationGatePanelProps {
  facts: LivingFactDTO[];
  auditFactId: string;
  setAuditFactId: (id: string) => void;
  auditPassed: boolean;
  setAuditPassed: (passed: boolean) => void;
  auditResult: ValidationAuditResponseDTO | null;
  onRunAudit: () => Promise<void>;
}

export function ProjectFactValidationGatePanel({
  facts,
  auditFactId,
  setAuditFactId,
  auditPassed,
  setAuditPassed,
  auditResult,
  onRunAudit,
}: ProjectFactValidationGatePanelProps): React.JSX.Element {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-border/80 p-3 space-y-2.5 bg-card text-xs">
        <div className="font-semibold text-foreground flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5 text-primary" />
          <span>基于确定性验证的经验准入网关 (Validation Promotion Gateway)</span>
        </div>
        <div className="space-y-1">
          <label htmlFor="audit-fact-select" className="text-[11px] text-muted-foreground font-medium">
            待审计事实项 (Select Fact):
          </label>
          <select
            id="audit-fact-select"
            value={auditFactId}
            onChange={(e) => setAuditFactId(e.target.value)}
            className="h-7 w-full rounded-md border border-input bg-background px-2 text-xs"
          >
            {facts.map((f) => (
              <option key={f.fact_id} value={f.fact_id}>
                [{f.fact_type}] {f.title} ({f.promotion_stage})
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-4 pt-1">
          <span className="text-[11px] text-muted-foreground font-medium">验证结果:</span>
          <label htmlFor="audit-passed-radio" className="flex items-center gap-1 cursor-pointer">
            <input
              id="audit-passed-radio"
              type="radio"
              name="audit_verdict"
              checked={auditPassed}
              onChange={() => setAuditPassed(true)}
            />
            <span className="text-green-600 font-medium">测试通过 (Passed)</span>
          </label>
          <label htmlFor="audit-failed-radio" className="flex items-center gap-1 cursor-pointer">
            <input
              id="audit-failed-radio"
              type="radio"
              name="audit_verdict"
              checked={!auditPassed}
              onChange={() => setAuditPassed(false)}
            />
            <span className="text-destructive font-medium">测试回归/失败 (Failed)</span>
          </label>
        </div>
        <Button type="button" size="sm" className="h-7 text-xs w-full" onClick={onRunAudit}>
          执行验证审计并触发晋升飞轮
        </Button>
      </div>

      {auditResult ? (
        <div className="rounded border border-primary/40 bg-muted/20 p-2.5 text-xs space-y-1">
          <div className="font-semibold text-foreground flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            <span>审计结论: {auditResult.message}</span>
          </div>
          <div className="text-[11px] text-muted-foreground">
            阶段演进:{' '}
            <Badge variant="outline" className="text-[10px]">
              {auditResult.previous_stage}
            </Badge>{' '}
            ➔{' '}
            <Badge variant="default" className="text-[10px]">
              {auditResult.current_stage}
            </Badge>
          </div>
        </div>
      ) : null}
    </div>
  );
}
