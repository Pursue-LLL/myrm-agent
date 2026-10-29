/**
 * useArtifactSandboxStore.ts
 * 通用办公工件沙盒运行、富文本多模板美化排版与金融沙盘因果推演状态管理
 */

import { create } from 'zustand';
import type {
  ArtifactSandboxMode,
  FinancialSandplayMetrics,
  FinancialShockScenario,
  InteractiveArtifactItem,
  NewsletterTheme,
  RichCopyResult,
} from './artifactSandboxTypes';
import { calculateFinancialSandplay } from './artifactSandboxEngine';

export interface ArtifactSandboxStoreState {
  activeArtifact: InteractiveArtifactItem | null;
  sandboxMode: ArtifactSandboxMode;
  activeTheme: NewsletterTheme;
  isFullscreen: boolean;
  isRendering: boolean;
  lastCopyResult: RichCopyResult | null;
  baseFinancialMetrics: FinancialSandplayMetrics;
  activeShock: FinancialShockScenario | null;
  computedFinancialMetrics: FinancialSandplayMetrics;

  // Actions
  setActiveArtifact: (item: InteractiveArtifactItem | null) => void;
  setSandboxMode: (mode: ArtifactSandboxMode) => void;
  setActiveTheme: (theme: NewsletterTheme) => void;
  toggleFullscreen: (fullscreen?: boolean) => void;
  setBaseFinancialMetrics: (
    metrics: Partial<FinancialSandplayMetrics>
  ) => void;
  applyShockScenario: (scenario: FinancialShockScenario | null) => void;
  setLastCopyResult: (result: RichCopyResult | null) => void;
  resetAll: () => void;
}

const defaultBaseFinancialMetrics: FinancialSandplayMetrics = {
  upstreamRawMaterialCost: 100,
  midstreamProcessingCapacity: 85,
  downstreamEndUserDemand: 120,
  projectedProfitMargin: 13.15,
  systemicRiskIndex: 41.25,
};

export const useArtifactSandboxStore = create<ArtifactSandboxStoreState>(
  (set, get) => ({
    activeArtifact: {
      id: 'default-doc-artifact',
      title: '季度研报与产业链推演草稿',
      mode: 'rich_newsletter',
      rawContent: `<h1>2026 产业因果推演与全要素生产率研报</h1>
<p>在全球高科技制造业与算力网络重构的大背景下，供应链上游材料与下游需求的协同至关重要。</p>
<blockquote>科技是第一生产力，因果推演是决策的关键护城河。</blockquote>
<pre><code>const metrics = { yieldRate: 0.985, latencyMs: 12 };</code></pre>
<table>
  <tr><th>指标</th><th>基准值</th><th>预测值</th></tr>
  <tr><td>产能利用率</td><td>85%</td><td>92%</td></tr>
</table>`,
      theme: 'mint_breeze',
      updatedAt: Date.now(),
    },
    sandboxMode: 'rich_newsletter',
    activeTheme: 'mint_breeze',
    isFullscreen: false,
    isRendering: false,
    lastCopyResult: null,
    baseFinancialMetrics: defaultBaseFinancialMetrics,
    activeShock: null,
    computedFinancialMetrics: calculateFinancialSandplay(
      defaultBaseFinancialMetrics
    ),

    setActiveArtifact: (item: InteractiveArtifactItem | null): void => {
      set({
        activeArtifact: item,
        sandboxMode: item?.mode ?? 'rich_newsletter',
        activeTheme: item?.theme ?? 'mint_breeze',
      });
    },

    setSandboxMode: (mode: ArtifactSandboxMode): void => {
      set({ sandboxMode: mode });
    },

    setActiveTheme: (theme: NewsletterTheme): void => {
      set({ activeTheme: theme });
    },

    toggleFullscreen: (fullscreen?: boolean): void => {
      set((state) => ({
        isFullscreen:
          fullscreen !== undefined ? fullscreen : !state.isFullscreen,
      }));
    },

    setBaseFinancialMetrics: (
      partial: Partial<FinancialSandplayMetrics>
    ): void => {
      set((state) => {
        const nextBase = { ...state.baseFinancialMetrics, ...partial };
        return {
          baseFinancialMetrics: nextBase,
          computedFinancialMetrics: calculateFinancialSandplay(
            nextBase,
            state.activeShock ?? undefined
          ),
        };
      });
    },

    applyShockScenario: (scenario: FinancialShockScenario | null): void => {
      set((state) => ({
        activeShock: scenario,
        computedFinancialMetrics: calculateFinancialSandplay(
          state.baseFinancialMetrics,
          scenario ?? undefined
        ),
      }));
    },

    setLastCopyResult: (result: RichCopyResult | null): void => {
      set({ lastCopyResult: result });
    },

    resetAll: (): void => {
      set({
        activeArtifact: null,
        sandboxMode: 'rich_newsletter',
        activeTheme: 'mint_breeze',
        isFullscreen: false,
        isRendering: false,
        lastCopyResult: null,
        baseFinancialMetrics: defaultBaseFinancialMetrics,
        activeShock: null,
        computedFinancialMetrics: calculateFinancialSandplay(
          defaultBaseFinancialMetrics
        ),
      });
    },
  })
);
