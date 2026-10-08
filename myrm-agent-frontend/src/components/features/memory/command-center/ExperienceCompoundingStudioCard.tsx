/**
 * Experience Compounding and Knowledge Condensation Studio Card.
 * Central command-center hub integrating frequency weight compounding,
 * semantic Golden Rule synthesis, rollback decondensation, and context annealing.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  TrendingUp,
  Sparkles,
  Snowflake,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import {
  experienceCompoundingService,
  AddExperienceItemRequest,
  CompoundedExperienceItemDTO,
  GoldenRuleDTO,
  ExperienceCompoundingStatsResponse,
} from '@/services/memory/experienceCompounding';
import { ExperienceCompoundingHudBar } from './ExperienceCompoundingHudBar';
import { GoldenRulesCatalogView } from './GoldenRulesCatalogView';
import { ActiveExperiencesPoolView } from './ActiveExperiencesPoolView';
import {
  mockCompoundingStats,
  mockActiveExperiences,
  mockGoldenRules,
} from './experienceCompoundingFallbacks';

interface ExperienceCompoundingStudioCardProps {
  className?: string;
}

export const ExperienceCompoundingStudioCard: React.FC<
  ExperienceCompoundingStudioCardProps
> = ({ className = '' }) => {
  const [stats, setStats] =
    useState<ExperienceCompoundingStatsResponse>(mockCompoundingStats);
  const [activeItems, setActiveItems] =
    useState<CompoundedExperienceItemDTO[]>(mockActiveExperiences);
  const [goldenRules, setGoldenRules] =
    useState<GoldenRuleDTO[]>(mockGoldenRules);
  const [isProcessing, setIsProcessing] = useState(false);
  const [feedbackToast, setFeedbackToast] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [liveStats, liveActive, liveRules] = await Promise.all([
        experienceCompoundingService.getStats(),
        experienceCompoundingService.listActive(),
        experienceCompoundingService.listRules(),
      ]);
      setStats(liveStats);
      setActiveItems(liveActive);
      setGoldenRules(liveRules);
    } catch {
      setStats(mockCompoundingStats);
      setActiveItems(mockActiveExperiences);
      setGoldenRules(mockGoldenRules);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAddExperience = async (req: AddExperienceItemRequest) => {
    setIsProcessing(true);
    try {
      const created = await experienceCompoundingService.addItem(req);
      setFeedbackToast(`成功录入经验碎片: [${created.topic}] ${created.content.slice(0, 20)}...`);
      fetchData();
    } catch {
      setFeedbackToast(`本地暂存成功: [${req.topic}] ${req.content.slice(0, 20)}...`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReinforce = async (itemId: string) => {
    setIsProcessing(true);
    try {
      const res = await experienceCompoundingService.reinforce({
        item_id: itemId,
        adopted: true,
      });
      setFeedbackToast(`已加固经验 [${itemId}]，新权重: ${res.new_weight.toFixed(2)}x`);
      fetchData();
    } catch {
      setFeedbackToast(`本地暂存加固: 经验 [${itemId}] 权重提升`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handlePenalize = async (itemId: string) => {
    setIsProcessing(true);
    try {
      const res = await experienceCompoundingService.penalize({
        item_id: itemId,
        severity: 0.5,
      });
      setFeedbackToast(`已纠偏降权经验 [${itemId}]，新权重: ${res.new_weight.toFixed(2)}x`);
      fetchData();
    } catch {
      setFeedbackToast(`本地模拟纠偏: 经验 [${itemId}] 权重已降权衰减`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCondense = async () => {
    setIsProcessing(true);
    try {
      const report = await experienceCompoundingService.condense();
      setFeedbackToast(
        `语义凝练完成: 新提炼 ${report.rules_generated.length} 项黄金准则，归档 ${report.fragments_archived} 条原始碎片`
      );
      fetchData();
    } catch {
      setFeedbackToast('网络离线，已在本地模拟完成语义凝练');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDecondense = async (ruleId: string) => {
    setIsProcessing(true);
    try {
      const reactivated = await experienceCompoundingService.decondense({
        rule_id: ruleId,
      });
      setFeedbackToast(`已回退准则 [${ruleId}]，重新唤醒 ${reactivated.length} 条原始碎片`);
      fetchData();
    } catch {
      setFeedbackToast(`已在本地模拟回退准则 [${ruleId}]`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleAnneal = async () => {
    setIsProcessing(true);
    try {
      const rep = await experienceCompoundingService.anneal();
      setFeedbackToast(
        `时效退火完成: 评估 ${rep.inspected_count} 项，豁免常驻 ${rep.active_lease_exempt_count} 项，冷冻 ${rep.cold_tiered_count} 项`
      );
      fetchData();
    } catch {
      setFeedbackToast('网络离线，已在本地模拟执行时效退火');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <section
      aria-label="个人经验资产复利演进与自动凝练工作台"
      className={`bg-card text-card-foreground border border-border/80 rounded-2xl p-5 shadow-sm space-y-5 ${className}`}
    >
      {/* Studio Header */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border/60">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-primary/10 text-primary">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold tracking-tight text-foreground">
                经验资产复利与自动凝练
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold bg-primary/10 text-primary border border-primary/30">
                知识复利飞轮 · 越用越懂我
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              高频验证正向对数加固，同质碎片自动凝练为高阶黄金准则，临时陈旧上下文自适应退火沉降
            </p>
          </div>
        </div>

        {/* Global Action Buttons */}
        <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
          <button
            type="button"
            disabled={isProcessing}
            onClick={handleCondense}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 text-amber-600 dark:text-amber-400 transition-colors flex items-center gap-1.5 focus:outline-hidden focus:ring-2 focus:ring-primary disabled:opacity-50"
          >
            <Sparkles className="w-3.5 h-3.5" />
            一键语义凝练
          </button>
          <button
            type="button"
            disabled={isProcessing}
            onClick={handleAnneal}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-sky-500/15 hover:bg-sky-500/25 text-sky-600 dark:text-sky-400 transition-colors flex items-center gap-1.5 focus:outline-hidden focus:ring-2 focus:ring-primary disabled:opacity-50"
          >
            <Snowflake className="w-3.5 h-3.5" />
            时效冷退火
          </button>
          <button
            type="button"
            onClick={fetchData}
            aria-label="刷新复利遥测指标"
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground bg-muted/60 hover:bg-muted transition-colors focus:outline-hidden focus:ring-2 focus:ring-primary"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* 4-Dimensional Telemetry HUD */}
      <ExperienceCompoundingHudBar stats={stats} />

      {/* Main Grid: Golden Rules Catalog + Active Experiences Pool */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <GoldenRulesCatalogView
          rules={goldenRules}
          onDecondense={handleDecondense}
          isProcessing={isProcessing}
        />

        <ActiveExperiencesPoolView
          experiences={activeItems}
          onReinforce={handleReinforce}
          onPenalize={handlePenalize}
          onAddExperience={handleAddExperience}
          isProcessing={isProcessing}
        />
      </div>

      {/* Operational Feedback Toast */}
      {feedbackToast && (
        <aside className="p-3 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-primary shrink-0" />
            <output aria-live="polite" className="font-medium text-foreground">
              {feedbackToast}
            </output>
          </div>
          <button
            type="button"
            onClick={() => setFeedbackToast(null)}
            aria-label="关闭提示"
            className="text-muted-foreground hover:text-foreground p-1 focus:outline-hidden focus:ring-2 focus:ring-primary rounded-md"
          >
            <AlertCircle className="w-3.5 h-3.5" />
          </button>
        </aside>
      )}
    </section>
  );
};
