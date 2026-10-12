/**
 * [INPUT]
 * @/services/memory/experienceObservability
 * ./experienceObservabilityFallbacks
 * ./ExperienceObservabilityHudBar
 * ./ExperienceDistributionDashboardView
 * ./ZeroRefactorPluginConsoleView
 *
 * [OUTPUT]
 * ExperienceObservabilityStudioCard: Master Command Center card for Item 108
 * ZeroRefactorHostLifecyclePluginAndExperienceObservabilitySuite.
 *
 * [POS]
 * Command center card exposing experience triad observability and zero-refactor host plugin:
 * 1. Active Experience Inventory & Effect Distribution Dashboard
 * 2. Originating Source Session Traceability
 * 3. Zero-Refactor Host Lifecycle Plugin Adapter (Plugin, MCP, Skill)
 * Single file < 250 lines. Strict typing, zero any.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Activity, BarChart3, Plug } from 'lucide-react';
import {
  fetchObservabilityDashboard,
  type ExperienceObservabilityMetricDTO,
  type HostPluginConfigDTO,
} from '@/services/memory/experienceObservability';
import {
  FALLBACK_DASHBOARD_RESPONSE,
  FALLBACK_HOST_PLUGIN_CONFIG,
  FALLBACK_OBSERVABILITY_METRICS,
} from './experienceObservabilityFallbacks';
import { ExperienceObservabilityHudBar } from './ExperienceObservabilityHudBar';
import { ExperienceDistributionDashboardView } from './ExperienceDistributionDashboardView';
import { ZeroRefactorPluginConsoleView } from './ZeroRefactorPluginConsoleView';

type TabKey = 'distribution_dashboard' | 'plugin_console';

export const ExperienceObservabilityStudioCard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabKey>('distribution_dashboard');
  const [metrics, setMetrics] = useState<ExperienceObservabilityMetricDTO[]>(
    FALLBACK_OBSERVABILITY_METRICS,
  );
  const [pluginConfig, setPluginConfig] = useState<HostPluginConfigDTO>(
    FALLBACK_HOST_PLUGIN_CONFIG,
  );
  const [totalRecalls, setTotalRecalls] = useState<number>(401);
  const [totalInjections, setTotalInjections] = useState<number>(270);
  const [overallSuccessRate, setOverallSuccessRate] = useState<number>(0.95);
  const [isLoading, setIsLoading] = useState(false);

  const loadDashboard = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await fetchObservabilityDashboard();
      if (res && res.metrics) {
        setMetrics(res.metrics);
        setPluginConfig(res.plugin_config);
        setTotalRecalls(res.total_recalls);
        setTotalInjections(res.total_injections);
        setOverallSuccessRate(res.overall_success_rate);
      }
    } catch {
      // Graceful fallback
      setMetrics(FALLBACK_DASHBOARD_RESPONSE.metrics);
      setPluginConfig(FALLBACK_DASHBOARD_RESPONSE.plugin_config);
      setTotalRecalls(FALLBACK_DASHBOARD_RESPONSE.total_recalls);
      setTotalInjections(FALLBACK_DASHBOARD_RESPONSE.total_injections);
      setOverallSuccessRate(FALLBACK_DASHBOARD_RESPONSE.overall_success_rate);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const handleMetricUpdated = (updated: ExperienceObservabilityMetricDTO) => {
    setMetrics((prev) => {
      const next = prev.map((m) =>
        m.entry_id === updated.entry_id ? updated : m,
      );
      const avg =
        next.length > 0
          ? next.reduce((sum, item) => sum + item.success_rate, 0) /
            next.length
          : 1.0;
      setOverallSuccessRate(Math.round(avg * 1000) / 1000);
      return next;
    });
  };

  const handleConfigUpdated = (updated: HostPluginConfigDTO) => {
    setPluginConfig(updated);
  };

  return (
    <div className="p-4 sm:p-5 bg-card rounded-xl border border-border/70 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm sm:text-base font-semibold text-foreground flex items-center gap-2">
              零改造宿主插件与经验可观测看板工作台
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-mono font-medium">
                P1 Item 108
              </span>
            </h3>
            <p className="text-xs text-muted-foreground">
              对标 OpenViking Plugin/MCP/Skill 三路零改造接入 ·
              经验列表、Session溯源与效果分布三件套全景可视
            </p>
          </div>
        </div>
      </div>

      {/* 4-Metric HUD Status Bar */}
      <ExperienceObservabilityHudBar
        totalTracked={metrics.length}
        totalInjections={totalInjections}
        overallSuccessRate={overallSuccessRate}
        activeChannel={pluginConfig.active_channel}
        isPluginEnabled={pluginConfig.enabled}
        onRefresh={loadDashboard}
        isRefreshing={isLoading}
      />

      {/* Tab Navigation */}
      <div className="flex flex-wrap gap-2 border-b border-border/50 pb-2">
        <button
          type="button"
          onClick={() => setActiveTab('distribution_dashboard')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
            activeTab === 'distribution_dashboard'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground'
          }`}
        >
          <BarChart3 className="w-3.5 h-3.5" />
          经验效果分布与会话溯源
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('plugin_console')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
            activeTab === 'plugin_console'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground'
          }`}
        >
          <Plug className="w-3.5 h-3.5" />
          零改造宿主生命周期插件
        </button>
      </div>

      {/* Tab Panels */}
      {activeTab === 'distribution_dashboard' && (
        <ExperienceDistributionDashboardView
          metrics={metrics}
          onMetricUpdated={handleMetricUpdated}
        />
      )}

      {activeTab === 'plugin_console' && (
        <ZeroRefactorPluginConsoleView
          initialConfig={pluginConfig}
          onConfigUpdated={handleConfigUpdated}
        />
      )}
    </div>
  );
};
