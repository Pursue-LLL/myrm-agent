/**
 * [INPUT]
 * @/services/memory/failureSessionRetrieval (Client functions and DTOs)
 * ./FailureRetrievalHudBar
 * ./FailureResolutionSearchView
 * ./HistoricalResolutionsCatalogView
 * ./failureSessionRetrievalFallbacks
 *
 * [OUTPUT]
 * FailureSessionRetrievalStudioCard: Main command-center panel for Item 109.
 *
 * [POS]
 * Command-center card for Failure-Triggered Historical Session Retrieval Suite.
 * Strict typing applied: No `any` types allowed. Accessible markup. Single file < 380 lines.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldAlert,
  Search,
  BookOpen,
  Sliders,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import {
  queryFailureResolutions,
  fetchHistoricalResolutions,
  fetchFailureTriggerConfig,
  updateFailureTriggerConfig,
  type FailureRetrievalResultDTO,
  type FailureTriggerConfigDTO,
  type HistoricalResolutionEntryDTO,
  type SearchFailureRequest,
} from '@/services/memory/failureSessionRetrieval';
import { FailureRetrievalHudBar } from './FailureRetrievalHudBar';
import { FailureResolutionSearchView } from './FailureResolutionSearchView';
import { HistoricalResolutionsCatalogView } from './HistoricalResolutionsCatalogView';
import {
  FALLBACK_RESOLUTIONS_CATALOG,
  FALLBACK_SAMPLE_RESULT,
  FALLBACK_CONFIG,
} from './failureSessionRetrievalFallbacks';

type ActiveTab = 'search' | 'catalog' | 'config';

export const FailureSessionRetrievalStudioCard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('search');
  const [resolutions, setResolutions] = useState<HistoricalResolutionEntryDTO[]>(
    FALLBACK_RESOLUTIONS_CATALOG,
  );
  const [searchResult, setSearchResult] = useState<FailureRetrievalResultDTO | null>(
    FALLBACK_SAMPLE_RESULT,
  );
  const [config, setConfig] = useState<FailureTriggerConfigDTO>(FALLBACK_CONFIG);
  const [loading, setLoading] = useState<boolean>(false);
  const [searching, setSearching] = useState<boolean>(false);
  const [savingConfig, setSavingConfig] = useState<boolean>(false);
  const [bannerMessage, setBannerMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [fetchedResolutions, fetchedConfig] = await Promise.all([
        fetchHistoricalResolutions(),
        fetchFailureTriggerConfig(),
      ]);
      if (fetchedResolutions && fetchedResolutions.length > 0) {
        setResolutions(fetchedResolutions);
      }
      if (fetchedConfig) {
        setConfig(fetchedConfig);
      }
    } catch {
      // 网络或接口离线时平滑降级至工业基线回退数据
      setResolutions(FALLBACK_RESOLUTIONS_CATALOG);
      setConfig(FALLBACK_CONFIG);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSearch = async (req: SearchFailureRequest) => {
    setSearching(true);
    setBannerMessage(null);
    try {
      const res = await queryFailureResolutions(req);
      setSearchResult(res);
    } catch {
      // 离线查询兜底
      setSearchResult(FALLBACK_SAMPLE_RESULT);
      setBannerMessage('已切换为离线基线解法模拟结果');
    } finally {
      setSearching(false);
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingConfig(true);
    try {
      const updated = await updateFailureTriggerConfig(config);
      setConfig(updated);
      setBannerMessage('拦截器参数已成功保存');
      setTimeout(() => setBannerMessage(null), 3000);
    } catch {
      setBannerMessage('配置保存失败，已保留当前本地设定');
      setTimeout(() => setBannerMessage(null), 3000);
    } finally {
      setSavingConfig(false);
    }
  };

  const successCount = resolutions.filter(
    (r) => r.outcome_type === 'successful_resolution',
  ).length;
  const cautionaryCount = resolutions.filter(
    (r) => r.outcome_type === 'cautionary_failure',
  ).length;

  return (
    <div
      aria-label="失败触发历史会话检索控制台"
      className="rounded-xl border border-border bg-card p-5 space-y-4 shadow-sm"
    >
      {/* 头部标题区 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-foreground tracking-tight">
                历史会话报错检索与自愈中枢
              </h2>
              <span className="px-2 py-0.5 text-[11px] font-medium rounded-full bg-primary/10 text-primary border border-primary/20">
                Item 109 · P0
              </span>
              <span className="px-2 py-0.5 text-[11px] font-medium rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                对标 AgentGit · 零提示自愈
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              工具执行报错时自动提取去噪指纹、检索历史会话同类解法与避坑警示、免提示直读恢复
            </p>
          </div>
        </div>

        {/* 顶部 Tab 切换 */}
        <nav
          aria-label="中枢视图选项卡"
          className="flex items-center gap-1 bg-muted p-1 rounded-lg text-xs"
        >
          <button
            type="button"
            aria-label="切换至报错检索直读"
            onClick={() => setActiveTab('search')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'search'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Search className="w-3.5 h-3.5" />
            <span>报错检索直读</span>
          </button>
          <button
            type="button"
            aria-label="切换至历史解法库"
            onClick={() => setActiveTab('catalog')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'catalog'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            <span>历史解法库 ({resolutions.length})</span>
          </button>
          <button
            type="button"
            aria-label="切换至拦截器配置"
            onClick={() => setActiveTab('config')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'config'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sliders className="w-3.5 h-3.5" />
            <span>拦截器配置</span>
          </button>
        </nav>
      </div>

      {/* 4 维 HUD 遥测监控条 */}
      <FailureRetrievalHudBar
        totalEntries={resolutions.length}
        successCount={successCount}
        cautionaryCount={cautionaryCount}
        autoTriggerActive={config.auto_trigger_on_error}
        refreshing={loading}
        onRefresh={loadData}
        onToggleConfig={() => setActiveTab('config')}
      />

      {/* 状态通知条 */}
      {bannerMessage && (
        <div className="flex items-center gap-2 p-2.5 rounded-md bg-primary/10 border border-primary/20 text-xs text-primary">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>{bannerMessage}</span>
        </div>
      )}

      {/* 核心主视图分发 */}
      {activeTab === 'search' && (
        <FailureResolutionSearchView
          onSearch={handleSearch}
          searchResult={searchResult}
          searching={searching}
        />
      )}

      {activeTab === 'catalog' && (
        <HistoricalResolutionsCatalogView resolutions={resolutions} />
      )}

      {activeTab === 'config' && (
        <form onSubmit={handleSaveConfig} className="p-4 bg-muted/30 rounded-lg border border-border space-y-4">
          <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Sliders className="w-3.5 h-3.5 text-primary" />
            <span>自动化失败拦截自愈参数设置</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label
                htmlFor="config-max-matches-input"
                className="text-xs font-medium text-foreground block"
              >
                最大返回历史会话数 (Top-N)
              </label>
              <input
                id="config-max-matches-input"
                type="number"
                min={1}
                max={10}
                value={config.max_matches}
                onChange={(e) =>
                  setConfig((prev) => ({
                    ...prev,
                    max_matches: parseInt(e.target.value, 10) || 3,
                  }))
                }
                className="w-full px-2.5 py-1.5 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <span className="text-[11px] text-muted-foreground block">
                控制每次工具报错时检索出的最相关历史解决案例上限
              </span>
            </div>

            <div className="space-y-1">
              <label
                htmlFor="config-similarity-threshold-input"
                className="text-xs font-medium text-foreground block"
              >
                相似度截断阈值 (0.0 - 1.0)
              </label>
              <input
                id="config-similarity-threshold-input"
                type="number"
                step="0.05"
                min={0}
                max={1}
                value={config.min_similarity_threshold}
                onChange={(e) =>
                  setConfig((prev) => ({
                    ...prev,
                    min_similarity_threshold: parseFloat(e.target.value) || 0.6,
                  }))
                }
                className="w-full px-2.5 py-1.5 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <span className="text-[11px] text-muted-foreground block">
                低于该相似度的历史会话将被过滤，避免误导
              </span>
            </div>
          </div>

          <div className="space-y-2 pt-2 border-t border-border/50">
            <div className="flex items-center gap-2">
              <input
                id="config-auto-trigger-checkbox"
                type="checkbox"
                checked={config.auto_trigger_on_error}
                onChange={(e) =>
                  setConfig((prev) => ({
                    ...prev,
                    auto_trigger_on_error: e.target.checked,
                  }))
                }
                className="rounded border-input text-primary focus:ring-primary"
              />
              <label
                htmlFor="config-auto-trigger-checkbox"
                className="text-xs font-medium text-foreground cursor-pointer"
              >
                启用零提示自动拦截自愈 (免提问直接注入历史解法)
              </label>
            </div>

            <div className="flex items-center gap-2">
              <input
                id="config-include-cautionary-checkbox"
                type="checkbox"
                checked={config.include_cautionary_failures}
                onChange={(e) =>
                  setConfig((prev) => ({
                    ...prev,
                    include_cautionary_failures: e.target.checked,
                  }))
                }
                className="rounded border-input text-primary focus:ring-primary"
              />
              <label
                htmlFor="config-include-cautionary-checkbox"
                className="text-xs font-medium text-foreground cursor-pointer"
              >
                包含踩坑死胡同警示 (返回历史失败尝试防范无意义重试)
              </label>
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={savingConfig}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{savingConfig ? '保存中...' : '保存拦截参数'}</span>
            </button>
          </div>
        </form>
      )}
    </div>
  );
};
