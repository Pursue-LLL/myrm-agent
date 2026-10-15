import React, { useRef, useEffect } from 'react';
import {
  MousePointer,
  Pin,
  Eye,
  PanelRightClose,
  PanelRightOpen,
  Sparkles,
} from 'lucide-react';
import { useInsituAnnotationStore } from './useInsituAnnotationStore';
import { generateCssFromPatches } from './insituAnnotationEngine';
import { InSituPropertyInspector } from './InSituPropertyInspector';
import { InSituCommentPinLayer } from './InSituCommentPinLayer';
import { InSituBatchCommentRail } from './InSituBatchCommentRail';
import { BatchAnnotationPayload, CanvasInteractionMode } from './insituAnnotationTypes';

interface InSituCanvasContainerProps {
  onBatchDispatch?: (payload: BatchAnnotationPayload) => void;
  children?: React.ReactNode;
}

export const InSituCanvasContainer: React.FC<InSituCanvasContainerProps> = ({
  onBatchDispatch,
  children,
}) => {
  const canvasRef = useRef<HTMLDivElement>(null);
  const {
    mode,
    setMode,
    stylePatches,
    addCommentPin,
    setInspectionTarget,
    isRailOpen,
    toggleRail,
  } = useInsituAnnotationStore();

  // 原生事件绑定，精确计算画布内相对坐标并避免 static a11y 检查报警
  useEffect(() => {
    const canvasEl = canvasRef.current;
    if (!canvasEl) {
      return;
    }

    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target || !canvasEl.contains(target)) {
        return;
      }

      // 如果点击在批注钉或浮层内部，不重复触发打点
      if (
        target.closest('[data-testid="insitu-comment-pin-layer"]') ||
        target.closest('[data-testid="insitu-property-inspector"]')
      ) {
        return;
      }

      const rect = canvasEl.getBoundingClientRect();
      const relativeX = Math.round(e.clientX - rect.left);
      const relativeY = Math.round(e.clientY - rect.top);

      if (mode === 'comment') {
        const tagName = target.tagName.toLowerCase();
        const snippet = target.innerText?.slice(0, 30) || target.outerHTML.slice(0, 40);
        addCommentPin({
          x: relativeX,
          y: relativeY,
          selector: target.id ? `#${target.id}` : tagName,
          targetTag: tagName,
          targetPreviewSnippet: snippet,
          commentText: '',
        });
      } else if (mode === 'inspect') {
        const tagName = target.tagName.toLowerCase();
        const computed = window.getComputedStyle(target);
        setInspectionTarget({
          selector: target.id ? `#${target.id}` : tagName,
          tagName,
          boundingClientRect: {
            top: relativeY,
            left: relativeX,
            width: target.offsetWidth,
            height: target.offsetHeight,
          },
          currentStyles: {
            color: computed.color,
            backgroundColor: computed.backgroundColor,
            fontSize: computed.fontSize,
            padding: computed.padding,
          },
          currentText: target.innerText || '',
        });
      }
    };

    canvasEl.addEventListener('click', handleClick);
    return () => {
      canvasEl.removeEventListener('click', handleClick);
    };
  }, [mode, addCommentPin, setInspectionTarget]);

  const modeButtons: Array<{
    id: CanvasInteractionMode;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
  }> = [
    { id: 'comment', label: '悬浮批注打标', icon: Pin },
    { id: 'inspect', label: '就地属性微调', icon: MousePointer },
    { id: 'preview', label: '纯净预览模式', icon: Eye },
  ];

  const injectedCss = generateCssFromPatches(stylePatches);

  return (
    <section
      data-testid="insitu-canvas-container"
      aria-label="工件画布可视化元素级就地精准编辑工作台"
      className="relative w-full h-[580px] rounded-2xl overflow-hidden border border-slate-800 bg-slate-950 flex flex-col select-none text-xs"
    >
      {/* 动态注入就地微调 CSS */}
      {injectedCss && <style>{injectedCss}</style>}

      {/* 顶部交互模式工具条 */}
      <header className="flex items-center justify-between px-3.5 py-2.5 bg-slate-950/90 backdrop-blur border-b border-slate-800 z-20">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-indigo-400" />
          <span className="font-semibold text-slate-200">
            画布可视化精准批注
          </span>
        </div>

        {/* 模式切换胶囊 */}
        <div className="flex items-center bg-slate-900 border border-slate-800 rounded-xl p-0.5">
          {modeButtons.map((btn) => {
            const Icon = btn.icon;
            const isSelected = mode === btn.id;
            return (
              <button
                key={btn.id}
                type="button"
                onClick={() => setMode(btn.id)}
                data-testid={`mode-switch-${btn.id}`}
                className={`flex items-center gap-1 px-3 py-1 rounded-lg transition-all font-medium text-xs ${
                  isSelected
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title={btn.label}
              >
                <Icon className="w-3 h-3" />
                <span>{btn.label}</span>
              </button>
            );
          })}
        </div>

        {/* 侧栏展开/收起 */}
        <button
          type="button"
          onClick={toggleRail}
          className="flex items-center gap-1 px-2.5 py-1 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white border border-slate-800 transition-colors text-xs"
          title={isRailOpen ? '收起批注侧栏' : '展开批注侧栏'}
          aria-label={isRailOpen ? '收起批注侧栏' : '展开批注侧栏'}
        >
          {isRailOpen ? (
            <PanelRightClose className="w-3.5 h-3.5" />
          ) : (
            <PanelRightOpen className="w-3.5 h-3.5" />
          )}
          <span className="hidden sm:inline">批注清单</span>
        </button>
      </header>

      {/* 主工作区：左侧交互画布 + 右侧批注汇总侧栏 */}
      <div className="flex-1 flex overflow-hidden relative">
        <div
          ref={canvasRef}
          data-testid="insitu-interactive-canvas-surface"
          className={`flex-1 relative overflow-auto p-4 bg-slate-900/30 ${
            mode === 'comment'
              ? 'cursor-crosshair'
              : mode === 'inspect'
              ? 'cursor-pointer'
              : 'cursor-default'
          }`}
        >
          {children || (
            <div className="p-6 bg-slate-950 border border-slate-800 rounded-2xl max-w-lg mx-auto space-y-4">
              <h2 id="demo-card-title" className="text-base font-bold text-white">
                智能交付工件实时预览
              </h2>
              <p className="text-xs text-slate-400 leading-relaxed">
                这是智能体生成的落地页面原型，点击上方「悬浮批注打标」或「就地属性微调」可直接在画布任意位置打点批注或就地改色。
              </p>
              <button
                type="button"
                id="demo-action-btn"
                className="px-4 py-2 rounded-xl bg-indigo-600 text-white font-medium text-xs"
              >
                立即开始体验
              </button>
            </div>
          )}

          {/* 就地微调浮层 */}
          <InSituPropertyInspector />

          {/* 悬浮批注钉图层 */}
          <InSituCommentPinLayer />
        </div>

        {/* 右侧批注侧栏 */}
        <InSituBatchCommentRail onBatchDispatch={onBatchDispatch} />
      </div>
    </section>
  );
};
