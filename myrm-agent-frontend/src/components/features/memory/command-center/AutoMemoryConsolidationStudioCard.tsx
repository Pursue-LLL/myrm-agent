/**
 * [INPUT]
 * @/services/memory::getAutoConsolidationConfig, updateAutoConsolidationConfig, evaluateAutoConsolidationGating, consolidateSessionAutoMemory
 * ./AutoMemoryGatingHudBar::AutoMemoryGatingHudBar
 * ./SixDimensionalArtifactViewer::SixDimensionalArtifactViewer
 * ./GatingRulesConfigView::GatingRulesConfigView
 * ./autoMemoryConsolidationFallbacks::FALLBACK_AUTO_CONSOLIDATION_CONFIG, FALLBACK_GATING_REPORT_ADMITTED, FALLBACK_SIX_DIMENSIONAL_ARTIFACT, SAMPLE_CONVERSATION_PRESETS
 * lucide-react::Brain, Sparkles, Sliders, RefreshCw, Play, CheckCircle2
 *
 * [OUTPUT]
 * AutoMemoryConsolidationStudioCard: Main command center card for Item 123.
 *
 * [POS]
 * Studio card component mounted into MemoryCommandCenterPanels.
 * Strict typing: No `any`. Single file < 350 lines.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Brain, Sparkles, Sliders, RefreshCw, Play, CheckCircle2 } from 'lucide-react';
import {
  getAutoConsolidationConfig,
  updateAutoConsolidationConfig,
  evaluateAutoConsolidationGating,
  consolidateSessionAutoMemory,
  type AutoMemoryGatingConfigDTO,
  type OverallGatingReportDTO,
  type SixDimensionalMemoryArtifactDTO,
} from '@/services/memory';
import { AutoMemoryGatingHudBar } from './AutoMemoryGatingHudBar';
import { SixDimensionalArtifactViewer } from './SixDimensionalArtifactViewer';
import { GatingRulesConfigView } from './GatingRulesConfigView';
import {
  FALLBACK_AUTO_CONSOLIDATION_CONFIG,
  FALLBACK_GATING_REPORT_ADMITTED,
  FALLBACK_SIX_DIMENSIONAL_ARTIFACT,
  SAMPLE_CONVERSATION_PRESETS,
} from './autoMemoryConsolidationFallbacks';

export const AutoMemoryConsolidationStudioCard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'monitor' | 'config'>('monitor');
  const [config, setConfig] = useState<AutoMemoryGatingConfigDTO>(FALLBACK_AUTO_CONSOLIDATION_CONFIG);
  const [report, setReport] = useState<OverallGatingReportDTO>(FALLBACK_GATING_REPORT_ADMITTED);
  const [artifact, setArtifact] = useState<SixDimensionalMemoryArtifactDTO | null>(
    FALLBACK_SIX_DIMENSIONAL_ARTIFACT,
  );
  const [selectedPresetIndex, setSelectedPresetIndex] = useState(0);
  const [forceBypass, setForceBypass] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [statusFeedback, setStatusFeedback] = useState<string | null>(null);

  // 初始化加载服务器配置
  const fetchConfig = useCallback(async () => {
    try {
      const data = await getAutoConsolidationConfig();
      setConfig(data);
    } catch {
      setConfig(FALLBACK_AUTO_CONSOLIDATION_CONFIG);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleSaveConfig = async (newConfig: AutoMemoryGatingConfigDTO) => {
    try {
      const saved = await updateAutoConsolidationConfig(newConfig);
      setConfig(saved);
      setStatusFeedback('门禁阈值配置已持久化更新');
    } catch {
      setConfig(newConfig);
      setStatusFeedback('本地已应用阈值配置');
    }
    setTimeout(() => setStatusFeedback(null), 3000);
  };

  const handleEvaluateGating = async () => {
    setIsLoading(true);
    setStatusFeedback(null);
    const preset = SAMPLE_CONVERSATION_PRESETS[selectedPresetIndex];
    try {
      const res = await evaluateAutoConsolidationGating({
        session_id: `sess-ui-${Date.now().toString().slice(-4)}`,
        messages: preset.messages,
        remaining_tokens: preset.remainingTokens,
        last_active_timestamp: Date.now() / 1000 - preset.idleSeconds,
        current_timestamp: Date.now() / 1000,
        require_idle: true,
      });
      setReport(res.report);
      setStatusFeedback('门禁评估完成');
    } catch {
      // 降级使用本地推导
      const isShort = preset.messages.length < config.min_turn_count;
      const isBudgetLow = preset.remainingTokens < config.min_remaining_budget_tokens;
      const shouldAdmit = !isShort && !isBudgetLow;

      setReport({
        session_id: `sess-ui-${Date.now().toString().slice(-4)}`,
        should_consolidate: shouldAdmit,
        turn_decision: {
          passed: !isShort,
          turn_count: preset.messages.length,
          info_density: isShort ? 0.15 : 0.65,
          reason: isShort
            ? `Conversation too brief: ${preset.messages.length} turns < ${config.min_turn_count}`
            : 'Turn count and info gain validated',
        },
        budget_decision: {
          passed: !isBudgetLow,
          remaining_tokens: preset.remainingTokens,
          estimated_cost_tokens: 650,
          cost_ratio: 650 / Math.max(1, preset.remainingTokens),
          reason: isBudgetLow ? 'Token budget below safety floor' : 'Budget approved',
        },
        idle_state: {
          session_id: `sess-ui-${Date.now().toString().slice(-4)}`,
          idle_seconds: preset.idleSeconds,
          idle_threshold_seconds: config.idle_timeout_seconds,
          is_idle_triggered: preset.idleSeconds >= config.idle_timeout_seconds,
          reason: 'Idle evaluation computed',
        },
        final_rationale: shouldAdmit ? '准入放行' : '门禁拦截挂起',
      });
      setStatusFeedback('已执行本地门禁规则审计');
    } finally {
      setIsLoading(false);
      setTimeout(() => setStatusFeedback(null), 2500);
    }
  };

  const handleConsolidate = async () => {
    setIsLoading(true);
    setStatusFeedback(null);
    const preset = SAMPLE_CONVERSATION_PRESETS[selectedPresetIndex];
    try {
      const res = await consolidateSessionAutoMemory({
        session_id: `sess-ui-${Date.now().toString().slice(-4)}`,
        messages: preset.messages,
        remaining_tokens: preset.remainingTokens,
        working_directory: '/Users/yululiu/projects/AI/open-perplexity',
        tool_call_records: preset.toolCalls,
        last_active_timestamp: Date.now() / 1000 - preset.idleSeconds,
        current_timestamp: Date.now() / 1000,
        force_bypass_gating: forceBypass,
        require_idle: true,
      });
      setReport(res.report);
      setArtifact(res.artifact || null);
      setStatusFeedback(res.artifact ? '六维记忆切片归档成功！' : '门禁拦截，跳过记忆生成');
    } catch {
      // 本地降级
      setArtifact(FALLBACK_SIX_DIMENSIONAL_ARTIFACT);
      setStatusFeedback('已本地生成结构化六维切片仿真样本');
    } finally {
      setIsLoading(false);
      setTimeout(() => setStatusFeedback(null), 2500);
    }
  };

  return (
    <section
      aria-label="闲置自适应与双门禁记忆沉淀控制台"
      className="p-5 rounded-xl border border-border/60 bg-card shadow-sm space-y-4"
    >
      {/* 标题栏 */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-border/40">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-purple-500/10 text-purple-600 dark:text-purple-400">
              <Brain className="w-4 h-4" />
            </div>
            <h2 className="text-base font-semibold text-foreground">
              闲置自适应与双门禁会话记忆沉淀引擎
            </h2>
            <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-secondary text-secondary-foreground">
              Item 123 · P1
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            对标 CodeX 双门禁：对话太短不记，额度告急不记；闲置自适应唤醒并沉淀六维工程资产切片。
          </p>
        </div>

        {/* Tab 切换 */}
        <div className="flex items-center gap-1.5 bg-secondary/40 p-1 rounded-lg border border-border/30">
          <button
            type="button"
            onClick={() => setActiveTab('monitor')}
            aria-label="切换至门禁监视与切片视图"
            className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'monitor'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-purple-500" />
            全景看板与沉淀
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('config')}
            aria-label="切换至双门禁规则调优面板"
            className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'config'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sliders className="w-3.5 h-3.5 text-blue-500" />
            门禁阈值调优
          </button>
        </div>
      </div>

      {/* 4 维 HUD 实时仪表条 */}
      <AutoMemoryGatingHudBar report={report} />

      {/* Tab 内容区 */}
      {activeTab === 'monitor' ? (
        <div className="space-y-4">
          {/* 控制条：场景切换与操作 */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-secondary/15 border border-border/30 text-xs">
            <div className="flex items-center gap-2">
              <label htmlFor="session-preset-select" className="font-medium text-foreground">
                测试对话场景：
              </label>
              <select
                id="session-preset-select"
                value={selectedPresetIndex}
                onChange={(e) => setSelectedPresetIndex(Number(e.target.value))}
                aria-label="选择测试会话场景"
                className="px-2.5 py-1 rounded border border-border/60 bg-background text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {SAMPLE_CONVERSATION_PRESETS.map((preset, idx) => (
                  <option key={idx} value={idx}>
                    {preset.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <input
                  id="force-bypass-gating"
                  type="checkbox"
                  checked={forceBypass}
                  onChange={(e) => setForceBypass(e.target.checked)}
                  aria-label="强制绕过门禁"
                  className="w-3.5 h-3.5 rounded border-border focus:ring-2 focus:ring-primary"
                />
                <label htmlFor="force-bypass-gating" className="text-muted-foreground cursor-pointer">
                  强制绕过门禁
                </label>
              </div>

              <button
                type="button"
                onClick={handleEvaluateGating}
                disabled={isLoading}
                aria-label="评估会话门禁准入"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-secondary hover:bg-secondary/80 text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
                审计准入
              </button>

              <button
                type="button"
                onClick={handleConsolidate}
                disabled={isLoading}
                aria-label="执行会话记忆沉淀"
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded bg-primary text-primary-foreground font-semibold hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50 shadow-sm"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                执行记忆沉淀
              </button>
            </div>
          </div>

          {/* 状态操作反馈提示 */}
          {statusFeedback && (
            <div className="flex items-center gap-2 p-2.5 rounded bg-primary/10 border border-primary/20 text-xs text-primary font-medium animate-in fade-in">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{statusFeedback}</span>
            </div>
          )}

          {/* 六维结构化切片全景看板 */}
          <SixDimensionalArtifactViewer artifact={artifact} />
        </div>
      ) : (
        <GatingRulesConfigView
          config={config}
          onSaveConfig={handleSaveConfig}
          disabled={isLoading}
        />
      )}
    </section>
  );
};
