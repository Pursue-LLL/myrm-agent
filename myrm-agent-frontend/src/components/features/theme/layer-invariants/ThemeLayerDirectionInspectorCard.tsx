import React, { useEffect } from 'react';
import {
  Sun,
  Moon,
  CheckCircle2,
  AlertTriangle,
  History,
  Wand2,
  Layers,
  Sparkles,
} from 'lucide-react';
import { useThemeLayerInvariantStore } from './useThemeLayerInvariantStore';
import { PrebakedBaselineDiffModal } from './PrebakedBaselineDiffModal';

export interface ThemeLayerDirectionInspectorCardProps {
  className?: string;
  initialLightCanvas?: string;
  initialLightCard?: string;
  initialDarkCanvas?: string;
  initialDarkCard?: string;
}

export const ThemeLayerDirectionInspectorCard: React.FC<
  ThemeLayerDirectionInspectorCardProps
> = ({
  className = '',
  initialLightCanvas = '#ffffff',
  initialLightCard = '#ffffff',
  initialDarkCanvas = '#09090b',
  initialDarkCard = '#18181b',
}) => {
  const {
    currentReport,
    selectedBaseline,
    evaluateCurrentTheme,
    toggleBaselineModal,
    applyQuickThemeFix,
  } = useThemeLayerInvariantStore();

  useEffect(() => {
    evaluateCurrentTheme(
      initialLightCanvas,
      initialLightCard,
      initialDarkCanvas,
      initialDarkCard
    );
  }, [
    evaluateCurrentTheme,
    initialLightCanvas,
    initialLightCard,
    initialDarkCanvas,
    initialDarkCard,
  ]);

  if (!currentReport) {
    return null;
  }

  const { lightEvaluation, darkEvaluation, allPassed, baselineComparison } =
    currentReport;

  return (
    <div
      data-testid="theme-layer-direction-inspector-card"
      className={`p-6 max-w-4xl mx-auto rounded-3xl bg-zinc-900/95 border border-zinc-800 shadow-2xl space-y-5 font-sans text-zinc-100 ${className}`}
    >
      {/* 1. 顶部标题 */}
      <header className="flex items-center justify-between pb-3 border-b border-zinc-800">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-2xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
              <span>双主题层级方向不变量与渲染色深度诊断</span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                Layer Direction Invariant
              </span>
            </h2>
            <p className="text-xs text-zinc-400">
              彻底杜绝“为让浅色卡片可见而调暗卡面”导致的发灰凹陷与反直觉视觉回归
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {allPassed ? (
            <span className="flex items-center gap-1 text-xs font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-2.5 py-1 rounded-xl">
              <CheckCircle2 className="w-3.5 h-3.5" />
              双主题方向合格
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs font-mono text-rose-400 bg-rose-500/10 border border-rose-500/30 px-2.5 py-1 rounded-xl animate-pulse">
              <AlertTriangle className="w-3.5 h-3.5" />
              检测到层级反转缺陷
            </span>
          )}
        </div>
      </header>

      {/* 2. 双主题同帧并列诊断区 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 浅色主题诊断卡 */}
        <div
          data-testid="light-mode-card"
          className="p-4 rounded-2xl bg-zinc-950/80 border border-zinc-800 space-y-3"
        >
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 font-bold text-xs text-zinc-200">
              <Sun className="w-4 h-4 text-amber-400" />
              浅色模式 (Light Mode)
            </span>
            <span
              className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${
                lightEvaluation.isInvariantSatisfied
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                  : 'bg-rose-500/10 text-rose-300 border-rose-500/30'
              }`}
            >
              {lightEvaluation.isInvariantSatisfied ? '方向合规' : '违规发灰'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div className="p-2.5 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1">
              <span className="text-[10px] text-zinc-500">页面画布底色</span>
              <div className="flex items-center gap-2">
                <span
                  className="w-4 h-4 rounded border border-zinc-700 shrink-0"
                  style={{ backgroundColor: lightEvaluation.canvasHex }}
                />
                <span className="font-bold">{lightEvaluation.canvasHex}</span>
              </div>
              <span className="text-[10px] text-zinc-400">
                明度 L: {lightEvaluation.canvasLightness}
              </span>
            </div>

            <div className="p-2.5 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1">
              <span className="text-[10px] text-zinc-500">抬升卡面颜色</span>
              <div className="flex items-center gap-2">
                <span
                  className="w-4 h-4 rounded border border-zinc-700 shrink-0"
                  style={{ backgroundColor: lightEvaluation.cardHex }}
                />
                <span className="font-bold">{lightEvaluation.cardHex}</span>
              </div>
              <span className="text-[10px] text-zinc-400">
                明度 L: {lightEvaluation.cardLightness}
              </span>
            </div>
          </div>

          <div className="text-[11px] font-mono text-zinc-400 pt-1 border-t border-zinc-850 flex items-center justify-between">
            <span>明度差 ΔL: {lightEvaluation.deltaLightness}</span>
            <span className="text-zinc-500">契约: L_card ≥ L_canvas</span>
          </div>

          {!lightEvaluation.isInvariantSatisfied && (
            <div className="p-2 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs space-y-1.5">
              <p>{lightEvaluation.violationReason}</p>
              <button
                type="button"
                onClick={() => {
                  applyQuickThemeFix('light');
                }}
                className="w-full py-1 px-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center justify-center gap-1 shadow transition-colors"
              >
                <Wand2 className="w-3 h-3" />
                <span>一键矫正为无损浅色 (#ffffff)</span>
              </button>
            </div>
          )}
        </div>

        {/* 深色主题诊断卡 */}
        <div
          data-testid="dark-mode-card"
          className="p-4 rounded-2xl bg-zinc-950/80 border border-zinc-800 space-y-3"
        >
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 font-bold text-xs text-zinc-200">
              <Moon className="w-4 h-4 text-indigo-400" />
              深色模式 (Dark Mode)
            </span>
            <span
              className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${
                darkEvaluation.isInvariantSatisfied
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                  : 'bg-rose-500/10 text-rose-300 border-rose-500/30'
              }`}
            >
              {darkEvaluation.isInvariantSatisfied ? '方向合规' : '抬升失效'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div className="p-2.5 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1">
              <span className="text-[10px] text-zinc-500">页面画布底色</span>
              <div className="flex items-center gap-2">
                <span
                  className="w-4 h-4 rounded border border-zinc-700 shrink-0"
                  style={{ backgroundColor: darkEvaluation.canvasHex }}
                />
                <span className="font-bold">{darkEvaluation.canvasHex}</span>
              </div>
              <span className="text-[10px] text-zinc-400">
                明度 L: {darkEvaluation.canvasLightness}
              </span>
            </div>

            <div className="p-2.5 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1">
              <span className="text-[10px] text-zinc-500">抬升卡面颜色</span>
              <div className="flex items-center gap-2">
                <span
                  className="w-4 h-4 rounded border border-zinc-700 shrink-0"
                  style={{ backgroundColor: darkEvaluation.cardHex }}
                />
                <span className="font-bold">{darkEvaluation.cardHex}</span>
              </div>
              <span className="text-[10px] text-zinc-400">
                明度 L: {darkEvaluation.cardLightness}
              </span>
            </div>
          </div>

          <div className="text-[11px] font-mono text-zinc-400 pt-1 border-t border-zinc-850 flex items-center justify-between">
            <span>明度差 ΔL: +{darkEvaluation.deltaLightness}</span>
            <span className="text-zinc-500">契约: L_card &gt; L_canvas</span>
          </div>

          {!darkEvaluation.isInvariantSatisfied && (
            <div className="p-2 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs space-y-1.5">
              <p>{darkEvaluation.violationReason}</p>
              <button
                type="button"
                onClick={() => {
                  applyQuickThemeFix('dark');
                }}
                className="w-full py-1 px-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center justify-center gap-1 shadow transition-colors"
              >
                <Wand2 className="w-3 h-3" />
                <span>一键矫正为无损深色 (#18181b)</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 3. 底部预烘基线比对快捷入口 */}
      <footer className="pt-2 border-t border-zinc-800 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 text-zinc-400 font-mono text-[11px]">
          <History className="w-3.5 h-3.5 text-indigo-400" />
          <span>比对基线: {selectedBaseline?.baselineVersion || '默认清洁版'}</span>
          {baselineComparison?.hasRegression && (
            <span className="text-amber-400 font-bold">
              (⚠️ 检测到历史版本回归)
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => {
            toggleBaselineModal(true);
          }}
          className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-indigo-300 hover:text-white font-semibold text-xs transition-colors"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>查看预烘基线对比报表</span>
        </button>
      </footer>

      {/* 4. 模态弹窗挂载 */}
      <PrebakedBaselineDiffModal />
    </div>
  );
};
