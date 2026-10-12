'use client';

/**
 * [INPUT]
 * @/services/memory/jobCompounding::JobDescriptionSpecDTO, CompoundingMaturityReportDTO, CompoundedRuleDTO
 * ./JobDescriptionBuilderView::JobDescriptionBuilderView
 * ./CompoundingMaturityView::CompoundingMaturityView
 *
 * [OUTPUT]
 * JobCompoundingCard: Command Center dashboard card for Domain-Specific Agent Job Description and Preference Compounding (Item 90 P0).
 *
 * [POS]
 * Implementation for Topic 01 Item 90 (xAI Grok Bot Bluebook-inspired 4-pillar job definition,
 * preference compounding, and maturity ladders).
 * Strict typing applied: No `any` types allowed.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/primitives/card';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  Briefcase,
  TrendingUp,
  Award,
  RefreshCw,
  Sparkles,
  AlertCircle,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import {
  getJobDescription,
  saveJobDescription,
  listCompoundedRules,
  recordCompoundedRule,
  evaluateMaturity,
  checkApprovalBoundary,
  type JobDescriptionSpecDTO,
  type SaveJobDescriptionRequestDTO,
  type CompoundedRuleDTO,
  type RecordRuleRequestDTO,
  type CompoundingMaturityReportDTO,
  type CheckApprovalResponseDTO,
} from '@/services/memory/jobCompounding';
import { JobDescriptionBuilderView } from './JobDescriptionBuilderView';
import { CompoundingMaturityView } from './CompoundingMaturityView';

type TabMode = 'pillars' | 'maturity';

const PRESET_TALENT_SCOUT: SaveJobDescriptionRequestDTO = {
  agent_id: 'agent_talent_scout_01',
  job_title: 'Talent Scout (人才搜寻员)',
  target_scope: '持续寻找高潜技术架构师简历，长期积累筛选偏好形成复利',
  tools_and_sources: ['web_search', 'resume_parser', 'table_analytics'],
  work_style: 'rigorous',
  autonomous_actions: ['scan_resumes', 'summarize_profile', 'tag_candidate'],
  requires_approval_actions: ['send_interview_invite', 'reject_candidate', 'contact_headhunter'],
};

const PRESET_BUG_REPRO: SaveJobDescriptionRequestDTO = {
  agent_id: 'agent_bug_repro_01',
  job_title: 'Bug Reproduction (漏洞复现员)',
  target_scope: '每次检查上报漏洞，自动化沙箱复现并积累排查思路与测试用例',
  tools_and_sources: ['test_runner', 'sandbox_exec', 'git_diff'],
  work_style: 'rigorous',
  autonomous_actions: ['checkout_code', 'run_tests', 'collect_logs'],
  requires_approval_actions: ['merge_hotfix', 'deploy_staging', 'restart_cluster'],
};

export function JobCompoundingCard(): React.JSX.Element {
  const [activeTab, setActiveTab] = useState<TabMode>('pillars');
  const [currentAgentId, setCurrentAgentId] = useState<string>('agent_talent_scout_01');
  const [spec, setSpec] = useState<JobDescriptionSpecDTO | null>(null);
  const [maturity, setMaturity] = useState<CompoundingMaturityReportDTO | null>(null);
  const [rules, setRules] = useState<CompoundedRuleDTO[]>([]);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const loadData = useCallback(async (agentId: string) => {
    try {
      const [specData, rulesData, maturityData] = await Promise.all([
        getJobDescription(agentId).catch(() => null),
        listCompoundedRules(agentId).catch(() => []),
        evaluateMaturity(agentId).catch(() => null),
      ]);
      setSpec(specData);
      setRules(rulesData);
      setMaturity(maturityData);
    } catch {
      // Degrade gracefully if offline
    }
  }, []);

  useEffect(() => {
    void loadData(currentAgentId);
  }, [currentAgentId, loadData]);

  const handleSaveSpec = async (request: SaveJobDescriptionRequestDTO) => {
    setIsSaving(true);
    try {
      const saved = await saveJobDescription(request);
      setSpec(saved);
      setCurrentAgentId(saved.agent_id);
      setStatusMessage(`已保存岗位四要素说明书: ${saved.job_title}`);
      await loadData(saved.agent_id);
    } catch {
      setStatusMessage('保存岗位说明书失败');
    } finally {
      setIsSaving(false);
    }
  };

  const handleRecordRule = async (request: RecordRuleRequestDTO) => {
    try {
      const recorded = await recordCompoundedRule(request);
      setRules((prev) => [recorded, ...prev]);
      setStatusMessage(`已沉淀新领域规则: ${recorded.statement}`);
      await loadData(request.agent_id);
    } catch {
      setStatusMessage('沉淀规则失败');
    }
  };

  const handleCheckApproval = async (actionName: string): Promise<CheckApprovalResponseDTO> => {
    return checkApprovalBoundary({
      agent_id: currentAgentId,
      action_name: actionName,
    });
  };

  const applyPreset = async (preset: SaveJobDescriptionRequestDTO) => {
    setCurrentAgentId(preset.agent_id);
    await handleSaveSpec(preset);
  };

  return (
    <Card className="border-border/80 shadow-sm" data-testid="job-compounding-card">
      <CardHeader className="pb-3 border-b border-border/50">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2">
            <Briefcase className="h-5 w-5 text-primary" />
            <CardTitle className="text-sm font-semibold tracking-tight">
              业务岗位说明书与经验复利沉淀套件 (Grok Bot 蓝皮书最佳实践)
            </CardTitle>
            <Badge variant="outline" className="text-[10px] text-primary border-primary/30">
              Item 90 P0
            </Badge>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="outline"
              onClick={() => void applyPreset(PRESET_TALENT_SCOUT)}
              className="h-7 text-xs gap-1"
              data-testid="preset-talent-scout-btn"
            >
              <Sparkles className="h-3 w-3 text-amber-500" />
              人才搜寻员
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void applyPreset(PRESET_BUG_REPRO)}
              className="h-7 text-xs gap-1"
              data-testid="preset-bug-repro-btn"
            >
              <Zap className="h-3 w-3 text-blue-500" />
              漏洞复现员
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void loadData(currentAgentId)}
              className="h-7 w-7 p-0"
              aria-label="刷新复利状态"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* HUD Metrics Banner */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 text-xs" data-testid="job-compounding-hud">
          <div className="rounded-md border border-border/70 p-2 bg-card">
            <div className="text-[10px] text-muted-foreground flex items-center gap-1">
              <Briefcase className="h-3 w-3 text-primary" />
              <span>领域岗位角色</span>
            </div>
            <div className="text-sm font-bold text-foreground truncate" data-testid="hud-job-title">
              {spec?.job_title ?? 'Talent Scout'}
            </div>
          </div>
          <div className="rounded-md border border-border/70 p-2 bg-card">
            <div className="text-[10px] text-muted-foreground flex items-center gap-1">
              <Award className="h-3 w-3 text-amber-500" />
              <span>复利成熟度等级</span>
            </div>
            <div className="text-base font-bold text-amber-600 dark:text-amber-400 capitalize" data-testid="hud-tier">
              {maturity?.tier ?? 'Rookie'}
            </div>
          </div>
          <div className="rounded-md border border-border/70 p-2 bg-card">
            <div className="text-[10px] text-muted-foreground flex items-center gap-1">
              <TrendingUp className="h-3 w-3 text-green-500" />
              <span>已沉淀领域规则</span>
            </div>
            <div className="text-base font-bold text-green-600 dark:text-green-400" data-testid="hud-rules-count">
              {rules.length} 条
            </div>
          </div>
          <div className="rounded-md border border-border/70 p-2 bg-card">
            <div className="text-[10px] text-muted-foreground flex items-center gap-1">
              <ShieldCheck className="h-3 w-3 text-blue-500" />
              <span>审批保护动作</span>
            </div>
            <div className="text-base font-bold text-foreground" data-testid="hud-approval-count">
              {spec?.approval_boundary.requires_approval_actions.length ?? 3} 项
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-3 space-y-3">
        {statusMessage && (
          <div className="flex items-center gap-1.5 text-xs text-primary bg-primary/10 border border-primary/20 rounded p-2">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{statusMessage}</span>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="flex items-center gap-1 border-b border-border/60 pb-1">
          <Button
            size="sm"
            variant={activeTab === 'pillars' ? 'default' : 'ghost'}
            className="h-7 text-xs"
            onClick={() => setActiveTab('pillars')}
            data-testid="tab-pillars"
          >
            立项四要素向导 (Job Pillars)
          </Button>
          <Button
            size="sm"
            variant={activeTab === 'maturity' ? 'default' : 'ghost'}
            className="h-7 text-xs"
            onClick={() => setActiveTab('maturity')}
            data-testid="tab-maturity"
          >
            经验复利看板与审批门禁 (Maturity & Rules)
          </Button>
        </div>

        {/* Tab 1: 4 Pillars Builder */}
        {activeTab === 'pillars' && (
          <JobDescriptionBuilderView
            currentSpec={spec}
            onSaveSpec={handleSaveSpec}
            isSaving={isSaving}
          />
        )}

        {/* Tab 2: Compounding Maturity & Rules */}
        {activeTab === 'maturity' && (
          <CompoundingMaturityView
            maturity={maturity}
            rules={rules}
            onRecordRule={handleRecordRule}
            onCheckApproval={handleCheckApproval}
          />
        )}
      </CardContent>
    </Card>
  );
}
