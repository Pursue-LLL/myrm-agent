import React from 'react';
import { Tag, Code2 } from 'lucide-react';
import { useElementEditorStore } from './useElementEditorStore';

export const ElementInspectorOverlay: React.FC = () => {
  const { mode, hoveredElement, selectedElement } = useElementEditorStore();

  if (mode === 'preview') {
    return null;
  }

  const activeElement = selectedElement || hoveredElement;
  if (!activeElement) {
    return null;
  }

  const { top, left, width, height } = activeElement.rect;
  const isSelected = Boolean(selectedElement);

  return (
    <div
      data-testid="element-inspector-overlay"
      className="absolute pointer-events-none transition-all duration-75 z-20"
      style={{
        top: `${top}px`,
        left: `${left}px`,
        width: `${width}px`,
        height: `${height}px`,
      }}
    >
      {/* 高亮外框 */}
      <div
        className={`w-full h-full rounded border-2 transition-colors ${
          isSelected
            ? 'border-indigo-500 bg-indigo-500/10 shadow-lg'
            : 'border-sky-400 border-dashed bg-sky-400/10'
        }`}
      />

      {/* 悬停/选中元数据标签 Badge */}
      <div
        className={`absolute -top-6 left-0 px-2 py-0.5 rounded text-[10px] font-mono font-bold flex items-center gap-1.5 shadow-md whitespace-nowrap ${
          isSelected
            ? 'bg-indigo-600 text-white'
            : 'bg-sky-500 text-slate-900'
        }`}
      >
        <Tag className="w-3 h-3" />
        <span>&lt;{activeElement.tag}&gt;</span>
        <span className="opacity-80">
          {Math.round(width)}×{Math.round(height)}
        </span>
        {activeElement.sourceLine && (
          <span className="opacity-75 inline-flex items-center gap-0.5">
            <Code2 className="w-2.5 h-2.5" />
            <span>L{activeElement.sourceLine}</span>
          </span>
        )}
      </div>
    </div>
  );
};
