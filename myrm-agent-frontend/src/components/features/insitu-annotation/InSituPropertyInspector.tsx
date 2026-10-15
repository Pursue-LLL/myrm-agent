import React, { useState, useEffect } from 'react';
import { Sliders, X, Check, Paintbrush, Type, Square } from 'lucide-react';
import { useInsituAnnotationStore } from './useInsituAnnotationStore';

export const InSituPropertyInspector: React.FC = () => {
  const { inspectionTarget, setInspectionTarget, upsertStylePatch } = useInsituAnnotationStore();

  const [text, setText] = useState('');
  const [color, setColor] = useState('#ffffff');
  const [bgColor, setBgColor] = useState('transparent');
  const [fontSize, setFontSize] = useState('14px');
  const [padding, setPadding] = useState('8px');

  useEffect(() => {
    if (inspectionTarget) {
      setText(inspectionTarget.currentText || '');
      setColor(inspectionTarget.currentStyles.color || '#ffffff');
      setBgColor(inspectionTarget.currentStyles.backgroundColor || 'transparent');
      setFontSize(inspectionTarget.currentStyles.fontSize || '14px');
      setPadding(inspectionTarget.currentStyles.padding || '8px');
    }
  }, [inspectionTarget]);

  if (!inspectionTarget) {
    return null;
  }

  const handleApply = () => {
    upsertStylePatch({
      selector: inspectionTarget.selector,
      tagName: inspectionTarget.tagName,
      textContent: text,
      color,
      backgroundColor: bgColor,
      fontSize,
      padding,
    });
    setInspectionTarget(null);
  };

  return (
    <div
      data-testid="insitu-property-inspector"
      aria-label="就地属性微调浮层"
      className="absolute top-4 left-4 z-40 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-2xl p-4 shadow-2xl w-80 text-xs text-slate-200 select-none animate-in fade-in duration-150"
    >
      {/* 顶栏 */}
      <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-800">
        <div className="flex items-center gap-1.5 font-bold text-slate-200">
          <Sliders className="w-3.5 h-3.5 text-indigo-400" />
          <span>就地属性微调</span>
          <span className="px-1.5 py-0.2 rounded font-mono text-[10px] bg-indigo-950 text-indigo-300 border border-indigo-800">
            {inspectionTarget.tagName}
          </span>
        </div>

        <button
          type="button"
          onClick={() => setInspectionTarget(null)}
          className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          title="关闭微调"
          aria-label="关闭"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="space-y-3 font-mono text-[11px]">
        {/* 文字内容 */}
        <div>
          <label htmlFor="insitu-text-input" className="flex items-center gap-1 text-slate-400 mb-1">
            <Type className="w-3 h-3 text-slate-500" />
            <span>文本内容:</span>
          </label>
          <input
            id="insitu-text-input"
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-slate-200 focus:outline-none focus:border-indigo-500"
          />
        </div>

        {/* 颜色与背景色 */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label htmlFor="insitu-color-input" className="flex items-center gap-1 text-slate-400 mb-1">
              <Paintbrush className="w-3 h-3 text-slate-500" />
              <span>文字颜色:</span>
            </label>
            <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 rounded-lg px-2 py-1">
              <input
                id="insitu-color-input"
                type="color"
                value={color.startsWith('#') ? color : '#ffffff'}
                onChange={(e) => setColor(e.target.value)}
                className="w-4 h-4 rounded border-none cursor-pointer bg-transparent"
              />
              <span className="text-[10px] text-slate-300">{color}</span>
            </div>
          </div>

          <div>
            <label htmlFor="insitu-bgcolor-input" className="flex items-center gap-1 text-slate-400 mb-1">
              <Square className="w-3 h-3 text-slate-500" />
              <span>背景颜色:</span>
            </label>
            <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 rounded-lg px-2 py-1">
              <input
                id="insitu-bgcolor-input"
                type="color"
                value={bgColor.startsWith('#') ? bgColor : '#1e1b4b'}
                onChange={(e) => setBgColor(e.target.value)}
                className="w-4 h-4 rounded border-none cursor-pointer bg-transparent"
              />
              <span className="text-[10px] text-slate-300 truncate">{bgColor}</span>
            </div>
          </div>
        </div>

        {/* 字号与内边距选择 */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <span className="text-slate-400 block mb-1">字号:</span>
            <select
              value={fontSize}
              onChange={(e) => setFontSize(e.target.value)}
              className="w-full px-2 py-1 bg-slate-950 border border-slate-800 rounded-lg text-slate-300 focus:outline-none"
            >
              <option value="12px">12px</option>
              <option value="14px">14px</option>
              <option value="16px">16px</option>
              <option value="18px">18px</option>
              <option value="24px">24px</option>
            </select>
          </div>

          <div>
            <span className="text-slate-400 block mb-1">内边距:</span>
            <select
              value={padding}
              onChange={(e) => setPadding(e.target.value)}
              className="w-full px-2 py-1 bg-slate-950 border border-slate-800 rounded-lg text-slate-300 focus:outline-none"
            >
              <option value="4px">4px</option>
              <option value="8px">8px</option>
              <option value="12px">12px</option>
              <option value="16px">16px</option>
              <option value="24px">24px</option>
            </select>
          </div>
        </div>
      </div>

      {/* 底部按钮 */}
      <div className="flex items-center justify-end gap-2 pt-3 mt-3 border-t border-slate-800">
        <button
          type="button"
          onClick={() => setInspectionTarget(null)}
          className="px-3 py-1 rounded-lg text-slate-400 hover:text-white transition-colors"
        >
          取消
        </button>
        <button
          type="button"
          onClick={handleApply}
          className="flex items-center gap-1 px-3.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow-xs transition-colors"
        >
          <Check className="w-3.5 h-3.5" />
          <span>应用补丁</span>
        </button>
      </div>
    </div>
  );
};
