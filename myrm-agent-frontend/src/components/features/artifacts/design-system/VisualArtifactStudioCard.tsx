import React, { useState } from 'react';
import {
  Palette,
  Target,
  Share2,
  Copy,
  Check,
  Send,
  Trash2,
  Sliders,
  Sparkles,
} from 'lucide-react';
import { useVisualArtifactStudioStore } from './useVisualArtifactStudioStore';
import { VisualElementSelectorOverlay } from './VisualElementSelectorOverlay';
import { DesignSpecSelectorCard } from './DesignSpecSelectorCard';
import { PublicShareModal } from './PublicShareModal';

export const VisualArtifactStudioCard: React.FC = () => {
  const {
    activeSpec,
    isInspectMode,
    selectedElement,
    promptBackfillText,
    toggleInspectMode,
    clearSelection,
    setPromptBackfillText,
    openShareModal,
  } = useVisualArtifactStudioStore();

  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const [showSpecDrawer, setShowSpecDrawer] = useState(false);

  const handleCopyPrompt = async () => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(promptBackfillText);
      }
      setCopiedPrompt(true);
      setTimeout(() => {
        setCopiedPrompt(false);
      }, 2000);
    } catch {
      // 容错
    }
  };

  const { colors, geometry, typography } = activeSpec.tokens;

  return (
    <div className="w-full max-w-5xl mx-auto rounded-2xl border border-slate-800 bg-slate-900/95 text-slate-100 shadow-2xl overflow-hidden backdrop-blur-xl">
      {/* 顶部主控条 */}
      <header className="flex flex-col gap-3 border-b border-slate-800 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
            <Palette className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-tight">
                工件设计系统与可视化审查工作台
              </h2>
              <span className="rounded-full bg-indigo-500/10 px-2 py-0.5 text-[10px] font-semibold text-indigo-400 border border-indigo-500/20">
                {activeSpec.name}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              DESIGN.md 规范约束 • 画布元素框选微调 • 零配置公网分享
            </p>
          </div>
        </div>

        {/* 顶部操作工具组 */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setShowSpecDrawer(!showSpecDrawer);
            }}
            aria-expanded={showSpecDrawer}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 transition-colors"
          >
            <Sliders className="h-3.5 w-3.5 text-indigo-400" />
            <span>规范配置</span>
          </button>

          <button
            type="button"
            onClick={() => {
              toggleInspectMode();
            }}
            aria-pressed={isInspectMode}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
              isInspectMode
                ? 'border-indigo-400 bg-indigo-600 text-white shadow-md shadow-indigo-950'
                : 'border-slate-700 bg-slate-800/90 text-slate-300 hover:bg-slate-800'
            }`}
          >
            <Target
              className={`h-3.5 w-3.5 ${
                isInspectMode ? 'animate-spin text-white' : 'text-indigo-400'
              }`}
            />
            <span>{isInspectMode ? '正在审查中...' : '框选元素修改'}</span>
          </button>

          <button
            type="button"
            onClick={openShareModal}
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-md hover:bg-emerald-500 active:scale-95 transition-all focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <Share2 className="h-3.5 w-3.5" />
            <span>一键公网发布</span>
          </button>
        </div>
      </header>

      {/* 规范抽屉（可折叠） */}
      {showSpecDrawer && (
        <div className="border-b border-slate-800 p-4 bg-slate-950/60 animate-in fade-in">
          <DesignSpecSelectorCard />
        </div>
      )}

      {/* 画布视口区域与元素审查蒙层 */}
      <div className="relative p-6 bg-slate-950 flex flex-col items-center justify-center overflow-x-auto">
        <div
          data-testid="artifact-preview-canvas"
          style={{
            backgroundColor: colors.background,
            color: colors.textPrimary,
            fontFamily: typography.fontFamilySans,
            borderRadius: geometry.borderRadius,
            boxShadow: geometry.shadowLevel,
          }}
          className="relative w-full max-w-2xl min-h-[400px] border border-slate-800 p-8 transition-all overflow-hidden"
        >
          {/* 画布内的组件示例内容 */}
          <div className="hero-container space-y-4">
            <div className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium border"
              style={{
                backgroundColor: `${colors.primary}15`,
                color: colors.primary,
                borderColor: `${colors.primary}30`,
              }}
            >
              <Sparkles className="h-3 w-3" />
              <span>DESIGN.md 驱动的纯净高质感排版</span>
            </div>

            <h1 className="title font-bold text-2xl sm:text-3xl tracking-tight leading-tight"
              style={{ color: colors.textPrimary }}
            >
              打造下一代企业级协同智能体
            </h1>

            <p className="text-sm max-w-md"
              style={{ color: colors.textMuted, lineHeight: typography.bodyLeading }}
            >
              通过工业级设计规范约束色彩、网格与视差层级，告别模糊自然语言调不动的低质页面。
            </p>

            <div>
              <button
                type="button"
                className="cta-button inline-flex items-center gap-2 px-5 py-2.5 text-xs font-semibold text-white transition-all shadow-md active:scale-95"
                style={{
                  backgroundColor: colors.primary,
                  borderRadius: geometry.borderRadius,
                }}
              >
                <span>立即免费体验</span>
              </button>
            </div>
          </div>

          {/* 特性栅格示例 */}
          <div className="feature-grid mt-8 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div
              className="feature-card p-4 border transition-all"
              style={{
                backgroundColor: colors.surface,
                borderColor: colors.border,
                borderRadius: geometry.borderRadius,
              }}
            >
              <h3 className="font-semibold text-sm mb-1" style={{ color: colors.textPrimary }}>
                多智能体 DAG 流水线编排
              </h3>
              <p className="text-xs" style={{ color: colors.textMuted }}>
                全双工协同事件图谱与实时/历史双向游标回溯防丢失。
              </p>
            </div>

            <div
              className="feature-card p-4 border transition-all"
              style={{
                backgroundColor: colors.surface,
                borderColor: colors.border,
                borderRadius: geometry.borderRadius,
              }}
            >
              <h3 className="font-semibold text-sm mb-1" style={{ color: colors.textPrimary }}>
                实时内存诊断与崩溃自愈
              </h3>
              <p className="text-xs" style={{ color: colors.textMuted }}>
                受限 2 KiB stderr 环形缓冲与人话级排障一键修复。
              </p>
            </div>
          </div>

          {/* 审查蒙层覆盖在视口上方 */}
          <VisualElementSelectorOverlay canvasWidth={672} canvasHeight={380} />
        </div>
      </div>

      {/* 底部元素框选精准回填区 */}
      {selectedElement && (
        <section
          aria-label="所见即所得框选微调回填面板"
          className="border-t border-slate-800 bg-slate-900/90 p-5 space-y-3"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="rounded bg-emerald-500/20 px-2 py-0.5 font-mono text-[11px] font-semibold text-emerald-300 border border-emerald-500/30">
                已锁定: {selectedElement.selectorPath}
              </span>
              <span className="text-xs text-slate-400">
                尺寸: {selectedElement.boundingBox.width}×{selectedElement.boundingBox.height}px
              </span>
            </div>

            <button
              type="button"
              onClick={clearSelection}
              className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-rose-400 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span>清空选中</span>
            </button>
          </div>

          <div>
            <label
              htmlFor="prompt-backfill-textarea"
              className="block text-xs font-semibold text-slate-300 mb-1"
            >
              自动生成的精准微调建议 Prompt:
            </label>
            <div className="relative">
              <textarea
                id="prompt-backfill-textarea"
                value={promptBackfillText}
                onChange={(e) => {
                  setPromptBackfillText(e.target.value);
                }}
                rows={3}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-xs text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono leading-relaxed"
              />
              <div className="absolute bottom-3 right-3 flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleCopyPrompt}
                  className="inline-flex items-center gap-1 rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700 transition-colors"
                >
                  {copiedPrompt ? (
                    <Check className="h-3 w-3 text-emerald-400" />
                  ) : (
                    <Copy className="h-3 w-3" />
                  )}
                  <span>{copiedPrompt ? '已复制' : '复制 Prompt'}</span>
                </button>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 rounded bg-indigo-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-indigo-500 shadow-sm transition-all"
                >
                  <Send className="h-3 w-3" />
                  <span>直接回填并让 Agent 执行</span>
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 零配置一键公网发布弹窗 */}
      <PublicShareModal />
    </div>
  );
};
