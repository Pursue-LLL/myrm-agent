import React from 'react';
import {
  X,
  History,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  ShieldCheck,
} from 'lucide-react';
import { useThemeLayerInvariantStore } from './useThemeLayerInvariantStore';
import { PrebakedThemeBaseline } from './themeLayerInvariantTypes';

export interface PrebakedBaselineDiffModalProps {
  className?: string;
}

export const PrebakedBaselineDiffModal: React.FC<
  PrebakedBaselineDiffModalProps
> = ({ className = '' }) => {
  const {
    isBaselineModalOpen,
    currentReport,
    selectedBaseline,
    prebakedBaselines,
    toggleBaselineModal,
    selectBaseline,
  } = useThemeLayerInvariantStore();

  if (!isBaselineModalOpen || !currentReport) {
    return null;
  }

  const handleClose = () => {
    toggleBaselineModal(false);
  };

  const handleSelectBaseline = (baseline: PrebakedThemeBaseline) => {
    selectBaseline(baseline);
  };

  const comparison = currentReport.baselineComparison;

  return (
    <div
      data-testid="prebaked-baseline-diff-modal"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in font-sans text-zinc-100"
    >
      <div
        className={`relative w-full max-w-xl rounded-3xl border border-zinc-800 bg-zinc-900 shadow-2xl p-6 space-y-4 max-h-[90vh] flex flex-col ${className}`}
      >
        {/* 1. 头部 */}
        <header className="flex items-center justify-between pb-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <History className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-zinc-100">
                预烘主题基线回归审查与对比
              </h3>
              <p className="text-[11px] text-zinc-400">
                对标 dsh-genui 跨版本层级方向回归门禁，对齐历史已知发布快照
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleClose}
            aria-label="关闭基线对比弹窗"
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* 2. 基线版本切换标签组 */}
        <div className="space-y-1.5">
          <span className="text-[11px] font-mono text-zinc-400">
            选择对比的历史预烘基线版本:
          </span>
          <div className="flex items-center gap-2">
            {prebakedBaselines.map((base) => {
              const isSelected =
                selectedBaseline?.baselineVersion === base.baselineVersion;
              return (
                <button
                  key={base.baselineVersion}
                  type="button"
                  onClick={() => {
                    handleSelectBaseline(base);
                  }}
                  className={`flex-1 p-2 rounded-xl border text-xs font-mono transition-all text-left ${
                    isSelected
                      ? 'bg-indigo-600/20 border-indigo-500 text-indigo-200'
                      : 'bg-zinc-950 border-zinc-800 text-zinc-400 hover:border-zinc-700'
                  }`}
                >
                  <div className="font-bold">{base.baselineVersion}</div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">
                    {base.lightMode.isCorrect ? '双模式合规' : '浅色发灰缺陷版'}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* 3. 对比分析报告 */}
        <div className="flex-1 overflow-y-auto space-y-3 pr-1 text-xs font-mono">
          {comparison?.hasRegression ? (
            <div className="p-3 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-300 space-y-2">
              <div className="flex items-center gap-1.5 font-bold text-rose-400">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>警报：相比所选基线检测到层级方向反转回归！</span>
              </div>
              <ul className="list-disc list-inside space-y-1 text-[11px] text-rose-200/90 pl-1">
                {comparison.details.map((d, i) => (
                  <li key={`d-${i}`}>{d}</li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="p-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 space-y-1">
              <div className="flex items-center gap-1.5 font-bold text-emerald-400">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>与所选历史基线保持高度一致，无层级方向回归缺陷</span>
              </div>
              <p className="text-[11px] text-emerald-200/80">
                浅色卡面未被错误调暗，深色卡面保持视觉抬升，符合 OKLCH / CSS 变量渲染不变量契约。
              </p>
            </div>
          )}

          {/* 明细对照卡片 */}
          <div className="p-3 rounded-2xl bg-zinc-950 border border-zinc-800 space-y-2 text-[11px]">
            <span className="font-semibold text-zinc-300 flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
              当前版本双主题实测状态:
            </span>
            <div className="grid grid-cols-2 gap-2 text-zinc-400">
              <div className="p-2 rounded-xl bg-zinc-900 border border-zinc-850 space-y-0.5">
                <div className="text-zinc-300 font-bold">浅色实测</div>
                <div>画布: {currentReport.lightEvaluation.canvasHex}</div>
                <div>卡面: {currentReport.lightEvaluation.cardHex}</div>
                <div
                  className={
                    currentReport.lightEvaluation.isInvariantSatisfied
                      ? 'text-emerald-400'
                      : 'text-rose-400'
                  }
                >
                  ΔL: {currentReport.lightEvaluation.deltaLightness}
                </div>
              </div>

              <div className="p-2 rounded-xl bg-zinc-900 border border-zinc-850 space-y-0.5">
                <div className="text-zinc-300 font-bold">深色实测</div>
                <div>画布: {currentReport.darkEvaluation.canvasHex}</div>
                <div>卡面: {currentReport.darkEvaluation.cardHex}</div>
                <div
                  className={
                    currentReport.darkEvaluation.isInvariantSatisfied
                      ? 'text-emerald-400'
                      : 'text-rose-400'
                  }
                >
                  ΔL: +{currentReport.darkEvaluation.deltaLightness}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 4. 底部操作 */}
        <footer className="pt-2 flex items-center justify-end gap-2 border-t border-zinc-800">
          <button
            type="button"
            onClick={handleClose}
            className="flex items-center gap-1 px-4 py-2 text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-xl transition-colors"
          >
            <span>完成审查并返回</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </footer>
      </div>
    </div>
  );
};
