import React from 'react';
import {
  Palette,
  Type,
  Maximize2,
  Square,
  X,
} from 'lucide-react';
import { useWysiwygEditorStore } from './useWysiwygEditorStore';
import { FontSizeOption } from './wysiwygEditorTypes';
import { mapFontSizeToCss } from './wysiwygEditorEngine';

export interface FloatingStyleToolbarProps {
  className?: string;
}

const PRESET_COLORS = [
  '#ffffff',
  '#6366f1',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#18181b',
];

const PRESET_BG_COLORS = [
  'transparent',
  '#18181b',
  '#312e81',
  '#064e3b',
  '#78350f',
];

const PRESET_PADDINGS = ['4px', '8px', '12px', '16px'];
const PRESET_RADII = ['0px', '6px', '12px', '9999px'];

export const FloatingStyleToolbar: React.FC<FloatingStyleToolbarProps> = ({
  className = '',
}) => {
  const { selectedElement, updateSelectedStyle, selectElement } =
    useWysiwygEditorStore();

  if (!selectedElement) {
    return null;
  }

  const handleColorChange = (color: string) => {
    updateSelectedStyle({ color });
  };

  const handleBgColorChange = (backgroundColor: string) => {
    updateSelectedStyle({ backgroundColor });
  };

  const handleFontSizeChange = (size: FontSizeOption) => {
    updateSelectedStyle({ fontSize: mapFontSizeToCss(size) });
  };

  const handlePaddingChange = (padding: string) => {
    updateSelectedStyle({ padding });
  };

  const handleRadiusChange = (borderRadius: string) => {
    updateSelectedStyle({ borderRadius });
  };

  return (
    <div
      data-testid="floating-style-toolbar"
      aria-label="行内样式微调工具条"
      className={`absolute top-3 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 p-2 rounded-2xl bg-zinc-900/98 backdrop-blur-xl border border-zinc-750 shadow-2xl font-sans text-xs text-zinc-200 animate-fade-in ${className}`}
    >
      {/* 1. 目标选择器徽章 */}
      <span className="font-mono text-[10px] px-2 py-0.5 rounded-lg bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 max-w-[120px] truncate">
        {selectedElement.selector}
      </span>

      {/* 2. 文字颜色 */}
      <div className="flex items-center gap-1 pl-1 border-l border-zinc-800">
        <Palette className="w-3.5 h-3.5 text-zinc-400" />
        <div className="flex items-center gap-1">
          {PRESET_COLORS.map((c) => (
            <button
              key={`fg-${c}`}
              type="button"
              onClick={() => {
                handleColorChange(c);
              }}
              aria-label={`文字颜色 ${c}`}
              className="w-4 h-4 rounded-full border border-zinc-600 hover:scale-110 transition-transform"
              style={{ backgroundColor: c }}
            />
          ))}
        </div>
      </div>

      {/* 3. 背景色 */}
      <div className="flex items-center gap-1 pl-1 border-l border-zinc-800">
        <Square className="w-3.5 h-3.5 text-zinc-400" />
        <div className="flex items-center gap-1">
          {PRESET_BG_COLORS.map((bg) => (
            <button
              key={`bg-${bg}`}
              type="button"
              onClick={() => {
                handleBgColorChange(bg);
              }}
              aria-label={`背景颜色 ${bg}`}
              className="w-4 h-4 rounded-full border border-zinc-600 hover:scale-110 transition-transform"
              style={{ backgroundColor: bg }}
            />
          ))}
        </div>
      </div>

      {/* 4. 字号大小 */}
      <div className="flex items-center gap-1 pl-1 border-l border-zinc-800">
        <Type className="w-3.5 h-3.5 text-zinc-400" />
        {(['sm', 'base', 'lg', 'xl'] as FontSizeOption[]).map((size) => (
          <button
            key={size}
            type="button"
            onClick={() => {
              handleFontSizeChange(size);
            }}
            className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
          >
            {size.toUpperCase()}
          </button>
        ))}
      </div>

      {/* 5. 内边距与圆角 */}
      <div className="flex items-center gap-1 pl-1 border-l border-zinc-800">
        <Maximize2 className="w-3.5 h-3.5 text-zinc-400" />
        <div className="flex items-center gap-1 font-mono text-[10px]">
          {PRESET_PADDINGS.map((p) => (
            <button
              key={`p-${p}`}
              type="button"
              onClick={() => {
                handlePaddingChange(p);
              }}
              className="px-1 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200"
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* 6. 取消选中 */}
      <button
        type="button"
        onClick={() => {
          selectElement(null);
        }}
        aria-label="关闭样式面板"
        className="p-1 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors ml-1"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};
