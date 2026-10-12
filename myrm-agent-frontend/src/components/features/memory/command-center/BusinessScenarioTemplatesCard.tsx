/**
 * [INPUT]
 * @/services/memory/businessTemplates
 * ./businessTemplateFallbacks
 * ./BusinessTemplateHudBar
 * ./BusinessAnalysisReviewTemplateView
 * ./RetailExchangeChecklistView
 * ./EscalationGateEvaluatorView
 *
 * [OUTPUT]
 * BusinessScenarioTemplatesCard: Master Command Center card for Item 107
 * BusinessScenarioExperienceTemplatesAndEscalationChecklistSuite.
 *
 * [POS]
 * Command center card exposing operational templates:
 * 1. Business Analysis Review 3-Method Template
 * 2. Retail Exchange 5-Stage Checklist
 * 3. Human Escalation Boundary Gate Evaluator
 * Single file < 300 lines. Strict typing, zero any.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Briefcase,
  FileSpreadsheet,
  ShoppingBag,
  ShieldAlert,
} from 'lucide-react';
import {
  fetchBusinessTemplates,
  type BusinessExperienceTemplateDTO,
} from '@/services/memory/businessTemplates';
import {
  FALLBACK_BUSINESS_ANALYSIS_TEMPLATE,
  FALLBACK_RETAIL_EXCHANGE_TEMPLATE,
  FALLBACK_ESCALATION_GATE_TEMPLATE,
  FALLBACK_TEMPLATES_LIST,
} from './businessTemplateFallbacks';
import { BusinessTemplateHudBar } from './BusinessTemplateHudBar';
import { BusinessAnalysisReviewTemplateView } from './BusinessAnalysisReviewTemplateView';
import { RetailExchangeChecklistView } from './RetailExchangeChecklistView';
import { EscalationGateEvaluatorView } from './EscalationGateEvaluatorView';

type TabKey = 'business_analysis' | 'retail_exchange' | 'escalation_gate';

export const BusinessScenarioTemplatesCard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabKey>('business_analysis');
  const [templates, setTemplates] = useState<BusinessExperienceTemplateDTO[]>(
    FALLBACK_TEMPLATES_LIST,
  );
  const [isLoading, setIsLoading] = useState(false);

  const loadTemplates = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await fetchBusinessTemplates();
      if (res && res.templates && res.templates.length > 0) {
        setTemplates(res.templates);
      }
    } catch {
      // Graceful fallback to pre-seeded industrial defaults
      setTemplates(FALLBACK_TEMPLATES_LIST);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTemplates();
  }, [loadTemplates]);

  const handleTemplateUpdated = (updated: BusinessExperienceTemplateDTO) => {
    setTemplates((prev) =>
      prev.map((t) => (t.template_id === updated.template_id ? updated : t)),
    );
  };

  const businessAnalysisTemplate =
    templates.find((t) => t.template_id === 'BA-REV-01') ||
    FALLBACK_BUSINESS_ANALYSIS_TEMPLATE;

  const retailExchangeTemplate =
    templates.find((t) => t.template_id === 'RET-EXC-01') ||
    FALLBACK_RETAIL_EXCHANGE_TEMPLATE;

  const escalationGateTemplate =
    templates.find((t) => t.template_id === 'ESC-GATE-01') ||
    FALLBACK_ESCALATION_GATE_TEMPLATE;

  return (
    <div className="p-4 sm:p-5 bg-card rounded-xl border border-border/70 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <Briefcase className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm sm:text-base font-semibold text-foreground flex items-center gap-2">
              业务场景经验模板与转人工门禁工作台
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-mono font-medium">
                P0 Item 107
              </span>
            </h3>
            <p className="text-xs text-muted-foreground">
              对标企业经营分析PPT复盘与τ²-bench售后换货真实场景 ·
              复用排障方法而非历史旧数据
            </p>
          </div>
        </div>
      </div>

      {/* 4-Metric HUD Status Bar */}
      <BusinessTemplateHudBar
        totalTemplates={templates.length}
        analysisStepsCount={businessAnalysisTemplate.checklist_steps.length}
        retailStepsCount={retailExchangeTemplate.checklist_steps.length}
        activeEscalationTriggers={escalationGateTemplate.checklist_steps.length}
        onRefresh={loadTemplates}
        isRefreshing={isLoading}
      />

      {/* Tab Navigation */}
      <div className="flex flex-wrap gap-2 border-b border-border/50 pb-2">
        <button
          type="button"
          onClick={() => setActiveTab('business_analysis')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
            activeTab === 'business_analysis'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground'
          }`}
        >
          <FileSpreadsheet className="w-3.5 h-3.5" />
          经营分析复盘三方法
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('retail_exchange')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
            activeTab === 'retail_exchange'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground'
          }`}
        >
          <ShoppingBag className="w-3.5 h-3.5" />
          换货先问必查全链路
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('escalation_gate')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
            activeTab === 'escalation_gate'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground'
          }`}
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          例外转人工决策门禁
        </button>
      </div>

      {/* Tab Panels */}
      {activeTab === 'business_analysis' && (
        <BusinessAnalysisReviewTemplateView
          template={businessAnalysisTemplate}
          onTemplateUpdated={handleTemplateUpdated}
        />
      )}

      {activeTab === 'retail_exchange' && (
        <RetailExchangeChecklistView template={retailExchangeTemplate} />
      )}

      {activeTab === 'escalation_gate' && <EscalationGateEvaluatorView />}
    </div>
  );
};
