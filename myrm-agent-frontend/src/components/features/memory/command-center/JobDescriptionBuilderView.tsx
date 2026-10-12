'use client';

/**
 * [INPUT]
 * @/services/memory/jobCompounding::JobDescriptionSpecDTO, SaveJobDescriptionRequestDTO
 *
 * [OUTPUT]
 * JobDescriptionBuilderView: Subcomponent for configuring the 4 pillars of domain-specific agent job description.
 *
 * [POS]
 * Subcomponent for Item 90 (Domain-Specific Agent Job Description and Preference Compounding Suite).
 * Strict typing applied: No `any` types allowed.
 */

import React, { useState, useEffect } from 'react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Briefcase, Wrench, ShieldCheck, Check, Save } from 'lucide-react';
import type { JobDescriptionSpecDTO, SaveJobDescriptionRequestDTO } from '@/services/memory/jobCompounding';

interface JobDescriptionBuilderViewProps {
  currentSpec: JobDescriptionSpecDTO | null;
  onSaveSpec: (request: SaveJobDescriptionRequestDTO) => Promise<void>;
  isSaving: boolean;
}

export function JobDescriptionBuilderView({
  currentSpec,
  onSaveSpec,
  isSaving,
}: JobDescriptionBuilderViewProps): React.JSX.Element {
  const [jobTitle, setJobTitle] = useState<string>('');
  const [targetScope, setTargetScope] = useState<string>('');
  const [toolsInput, setToolsInput] = useState<string>('');
  const [workStyle, setWorkStyle] = useState<string>('rigorous');
  const [autonomousInput, setAutonomousInput] = useState<string>('');
  const [requiresApprovalInput, setRequiresApprovalInput] = useState<string>('');

  useEffect(() => {
    if (currentSpec) {
      setJobTitle(currentSpec.job_title);
      setTargetScope(currentSpec.target_scope);
      setToolsInput(currentSpec.tools_and_sources.join(', '));
      setWorkStyle(currentSpec.work_style);
      setAutonomousInput(currentSpec.approval_boundary.autonomous_actions.join(', '));
      setRequiresApprovalInput(currentSpec.approval_boundary.requires_approval_actions.join(', '));
    }
  }, [currentSpec]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!jobTitle.trim() || !targetScope.trim()) return;

    const payload: SaveJobDescriptionRequestDTO = {
      agent_id: currentSpec?.agent_id ?? 'agent_talent_scout_01',
      job_title: jobTitle.trim(),
      target_scope: targetScope.trim(),
      tools_and_sources: toolsInput
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      work_style: workStyle.trim(),
      autonomous_actions: autonomousInput
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      requires_approval_actions: requiresApprovalInput
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    };

    await onSaveSpec(payload);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-md border border-border/70 p-3 bg-card"
      data-testid="job-description-builder-form"
    >
      <div className="flex items-center justify-between border-b border-border/50 pb-2">
        <div className="flex items-center gap-1.5">
          <Briefcase className="h-4 w-4 text-primary" />
          <span className="text-xs font-semibold text-foreground">
            智能体立项四要素向导 (Job Description Pillars)
          </span>
        </div>
        <Badge variant="outline" className="text-[10px] text-primary border-primary/30">
          Grok Bot 蓝皮书最佳实践
        </Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Pillar 1: Job Title & Target Scope */}
        <div className="space-y-2">
          <div className="space-y-1">
            <label htmlFor="job-title-input" className="text-[10px] font-medium text-foreground">
              要素一：领域岗位名称 (Job Title):
            </label>
            <input
              id="job-title-input"
              type="text"
              placeholder="例如: Talent Scout (人才搜寻员)"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              className="w-full rounded border border-input bg-background px-2.5 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              data-testid="job-title-input"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="target-scope-input" className="text-[10px] font-medium text-foreground">
              目标与职责范围 (Target Scope):
            </label>
            <textarea
              id="target-scope-input"
              rows={2}
              placeholder="持续寻找高潜技术架构师简历，长期积累筛选偏好形成复利..."
              value={targetScope}
              onChange={(e) => setTargetScope(e.target.value)}
              className="w-full rounded border border-input bg-background p-2 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              data-testid="target-scope-input"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="work-style-input" className="text-[10px] font-medium text-foreground">
              要素三：工作风格与调性 (Work Style):
            </label>
            <select
              id="work-style-input"
              value={workStyle}
              onChange={(e) => setWorkStyle(e.target.value)}
              className="w-full rounded border border-input bg-background px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              data-testid="work-style-select"
            >
              <option value="rigorous">严谨求精 (Rigorous & Cautious)</option>
              <option value="agile">敏捷高效 (Agile & Rapid)</option>
              <option value="creative">开放创新 (Creative & Explorative)</option>
            </select>
          </div>
        </div>

        {/* Pillar 2 & 4: Tools & Approval Boundary */}
        <div className="space-y-2">
          <div className="space-y-1">
            <label htmlFor="tools-input" className="text-[10px] font-medium text-foreground flex items-center gap-1">
              <Wrench className="h-3 w-3 text-blue-500" />
              <span>要素二：绑定工具与数据源 (逗号分隔):</span>
            </label>
            <input
              id="tools-input"
              type="text"
              placeholder="web_search, resume_parser, table_analytics"
              value={toolsInput}
              onChange={(e) => setToolsInput(e.target.value)}
              className="w-full rounded border border-input bg-background px-2.5 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              data-testid="tools-input"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="autonomous-input" className="text-[10px] font-medium text-foreground flex items-center gap-1">
              <Check className="h-3 w-3 text-green-500" />
              <span>要素四：自主执行动作 (无需问询):</span>
            </label>
            <input
              id="autonomous-input"
              type="text"
              placeholder="scan_resumes, summarize_profile, tag_candidate"
              value={autonomousInput}
              onChange={(e) => setAutonomousInput(e.target.value)}
              className="w-full rounded border border-input bg-background px-2.5 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              data-testid="autonomous-input"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="approval-input" className="text-[10px] font-medium text-foreground flex items-center gap-1">
              <ShieldCheck className="h-3 w-3 text-amber-500" />
              <span>要素四：需人工审批动作 (高危阻断):</span>
            </label>
            <input
              id="approval-input"
              type="text"
              placeholder="send_interview_invite, reject_candidate, contact_headhunter"
              value={requiresApprovalInput}
              onChange={(e) => setRequiresApprovalInput(e.target.value)}
              className="w-full rounded border border-input bg-background px-2.5 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              data-testid="approval-input"
            />
          </div>
        </div>
      </div>

      <div className="flex justify-end pt-1">
        <Button
          type="submit"
          size="sm"
          disabled={isSaving || !jobTitle.trim() || !targetScope.trim()}
          className="gap-1.5 h-7 text-xs"
          data-testid="save-job-description-btn"
        >
          <Save className="h-3.5 w-3.5" />
          {isSaving ? '正在保存立项说明书...' : '更新岗位四要素说明书'}
        </Button>
      </div>
    </form>
  );
}
