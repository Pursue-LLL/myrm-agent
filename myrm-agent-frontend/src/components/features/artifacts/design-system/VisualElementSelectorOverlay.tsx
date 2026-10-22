import React from 'react';
import { Target, X, Check, MousePointerClick } from 'lucide-react';
import { useVisualArtifactStudioStore } from './useVisualArtifactStudioStore';
import type { SelectedElementMeta } from './designSpecTypes';

interface VisualElementSelectorOverlayProps {
  canvasWidth?: number;
  canvasHeight?: number;
}

export const VisualElementSelectorOverlay: React.FC<VisualElementSelectorOverlayProps> = ({
  canvasWidth = 720,
  canvasHeight = 440,
}) => {
  const {
    isInspectMode,
    hoveredElement,
    selectedElement,
    toggleInspectMode,
    setHoveredElement,
    selectElement,
  } = useVisualArtifactStudioStore();

  if (!isInspectMode) {
    return null;
  }

  // 模拟画布内的可审查关键 DOM 节点热区
  const inspectableHotspots: SelectedElementMeta[] = [
    {
      selectorPath: '.hero-container > h1.title',
      tagName: 'h1',
      elementId: 'main-title',
      className: 'title font-bold text-3xl',
      textContent: '打造下一代企业级协同智能体',
      boundingBox: { x: 40, y: 30, width: 420, height: 48 },
      codeSnippet: '<h1 className="title font-bold text-3xl">打造下一代企业级协同智能体</h1>',
      generatedPromptSuggestion: '修改主标题文字或调整字体磅重',
    },
    {
      selectorPath: '.hero-container > button.cta-button',
      tagName: 'button',
      elementId: 'cta-primary',
      className: 'cta-button rounded-lg bg-indigo-600',
      textContent: '立即免费体验',
      boundingBox: { x: 40, y: 100, width: 140, height: 40 },
      codeSnippet: '<button className="cta-button rounded-lg bg-indigo-600">立即免费体验</button>',
      generatedPromptSuggestion: '将按钮背景色对齐至当前设计规范的主题色',
    },
    {
      selectorPath: '.feature-grid > .feature-card:nth-child(1)',
      tagName: 'div',
      className: 'feature-card border border-slate-700 p-4',
      textContent: '多智能体 DAG 流水线编排',
      boundingBox: { x: 40, y: 170, width: 200, height: 160 },
      codeSnippet: '<div className="feature-card border p-4"><h3>多智能体 DAG</h3></div>',
      generatedPromptSuggestion: '微调特性卡片的圆角与内边距',
    },
    {
      selectorPath: '.feature-grid > .feature-card:nth-child(2)',
      tagName: 'div',
      className: 'feature-card border border-slate-700 p-4',
      textContent: '实时内存诊断与崩溃自愈',
      boundingBox: { x: 260, y: 170, width: 200, height: 160 },
      codeSnippet: '<div className="feature-card border p-4"><h3>实时内存诊断</h3></div>',
      generatedPromptSuggestion: '调整第二张卡片的高亮投影效果',
    },
  ];

  const activeBox = selectedElement?.boundingBox ?? hoveredElement?.boundingBox;

  return (
    <section
      aria-label="所见即所得元素审查框选蒙层"
      className="absolute inset-0 z-30 overflow-hidden cursor-crosshair bg-slate-950/20 backdrop-blur-[0.5px]"
      style={{ width: `${canvasWidth}px`, height: `${canvasHeight}px` }}
    >
      {/* 顶部退出审查条 */}
      <div className="absolute top-2 right-2 z-40 flex items-center gap-2 rounded-full border border-indigo-500/40 bg-slate-900/95 px-3 py-1 text-xs text-indigo-300 shadow-lg backdrop-blur-md">
        <Target className="h-3.5 w-3.5 text-indigo-400 animate-pulse" />
        <span className="font-semibold">元素审查模式开启 (悬停并点击框选)</span>
        <button
          type="button"
          onClick={() => {
            toggleInspectMode(false);
          }}
          aria-label="退出审查模式"
          className="ml-1 rounded-full p-0.5 text-slate-400 hover:bg-slate-800 hover:text-white"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* 虚拟热区交互层 */}
      {inspectableHotspots.map((item) => {
        const isHovered = hoveredElement?.selectorPath === item.selectorPath;
        const isSelected = selectedElement?.selectorPath === item.selectorPath;

        return (
          <button
            key={item.selectorPath}
            type="button"
            onMouseEnter={() => {
              setHoveredElement(item);
            }}
            onMouseLeave={() => {
              if (hoveredElement?.selectorPath === item.selectorPath) {
                setHoveredElement(null);
              }
            }}
            onClick={() => {
              selectElement(item);
            }}
            aria-label={`审查元素: ${item.selectorPath}`}
            style={{
              position: 'absolute',
              left: `${item.boundingBox.x}px`,
              top: `${item.boundingBox.y}px`,
              width: `${item.boundingBox.width}px`,
              height: `${item.boundingBox.height}px`,
            }}
            className={`transition-all rounded ${
              isSelected
                ? 'ring-2 ring-emerald-400 bg-emerald-500/10'
                : isHovered
                ? 'ring-2 ring-indigo-400 bg-indigo-500/10'
                : 'hover:bg-indigo-500/5'
            }`}
          />
        );
      })}

      {/* 动态高亮盒模型与尺寸选择器药丸 */}
      {activeBox && (
        <div
          data-testid="inspect-highlight-box"
          style={{
            position: 'absolute',
            left: `${activeBox.x}px`,
            top: `${activeBox.y}px`,
            width: `${activeBox.width}px`,
            height: `${activeBox.height}px`,
            pointerEvents: 'none',
          }}
          className={`border-2 transition-all ${
            selectedElement ? 'border-emerald-400 shadow-md shadow-emerald-500/20' : 'border-indigo-400'
          }`}
        >
          <div
            className={`absolute -top-6 left-0 flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-[10px] text-white shadow-md ${
              selectedElement ? 'bg-emerald-600' : 'bg-indigo-600'
            }`}
          >
            {selectedElement ? (
              <Check className="h-2.5 w-2.5" />
            ) : (
              <MousePointerClick className="h-2.5 w-2.5" />
            )}
            <span>
              {(selectedElement ?? hoveredElement)?.tagName} • {activeBox.width}×{activeBox.height}px
            </span>
          </div>
        </div>
      )}
    </section>
  );
};
