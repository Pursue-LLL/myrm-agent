import React, { useState } from 'react';
import {
  Sparkles,
  X,
  Paintbrush,
  FileText,
  LayoutGrid,
  Check,
  Wand2,
} from 'lucide-react';
import { useElementEditorStore } from './useElementEditorStore';
import { EditPromptCategory } from './elementEditorTypes';

export const InPlaceEditPopover: React.FC = () => {
  const {
    selectedElement,
    mode,
    setSelectedElement,
    applyMicroPatch,
    isApplyingPatch,
  } = useElementEditorStore();

  const [instruction, setInstruction] = useState('');
  const [category, setCategory] = useState<EditPromptCategory>('style');

  if (mode !== 'in_place_editing' || !selectedElement) {
    return null;
  }

  const { top, left, height } = selectedElement.rect;
  const popoverTop = top + height + 10;
  const popoverLeft = Math.max(10, Math.min(left, 450));

  const handleApply = () => {
    if (!instruction.trim()) {
      return;
    }
    applyMicroPatch(instruction.trim(), category);
    setInstruction('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleApply();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setSelectedElement(null);
    }
  };

  const categoryOptions: Array<{
    id: EditPromptCategory;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
  }> = [
    { id: 'style', label: '样式调整', icon: Paintbrush },
    { id: 'content', label: '文案替换', icon: FileText },
    { id: 'layout', label: '布局边距', icon: LayoutGrid },
    { id: 'custom', label: '深度定制', icon: Wand2 },
  ];

  return (
    <div
      data-testid="in-place-edit-popover"
      className="absolute z-30 w-80 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-2xl p-3.5 shadow-2xl text-slate-200 select-none animate-in fade-in zoom-in-95 duration-100"
      style={{
        top: `${popoverTop}px`,
        left: `${popoverLeft}px`,
      }}
    >
      {/* 顶部标题与关闭 */}
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-100">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
          <span>就地微调 &lt;{selectedElement.tag}&gt;</span>
        </div>
        <button
          type="button"
          onClick={() => setSelectedElement(null)}
          className="text-slate-400 hover:text-white transition-colors p-0.5 rounded"
          aria-label="关闭微调"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 修改类型切换 */}
      <div className="grid grid-cols-4 gap-1 p-0.5 bg-slate-950 rounded-lg border border-slate-800 mb-2 text-[10px]">
        {categoryOptions.map((opt) => {
          const Icon = opt.icon;
          const isSelected = category === opt.id;
          return (
            <button
              key={opt.id}
              type="button"
              onClick={() => setCategory(opt.id)}
              className={`flex items-center justify-center gap-1 py-1 rounded transition-colors ${
                isSelected
                  ? 'bg-indigo-600 text-white font-medium shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Icon className="w-2.5 h-2.5" />
              <span>{opt.label}</span>
            </button>
          );
        })}
      </div>

      {/* 提示词输入框 */}
      <div className="relative mb-2">
        <textarea
          rows={2}
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入微调提示词 (如: 改成深紫渐变，加阴影)..."
          className="w-full bg-slate-950 border border-slate-800 rounded-xl p-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors resize-none"
        />
      </div>

      {/* 底部按钮 */}
      <div className="flex items-center justify-between text-[10px] text-slate-500">
        <span>按 Enter 注入补丁</span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setSelectedElement(null)}
            className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={!instruction.trim() || isApplyingPatch}
            className="inline-flex items-center gap-1 px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition-colors disabled:opacity-50"
          >
            <Check className="w-3 h-3" />
            <span>应用补丁</span>
          </button>
        </div>
      </div>
    </div>
  );
};
