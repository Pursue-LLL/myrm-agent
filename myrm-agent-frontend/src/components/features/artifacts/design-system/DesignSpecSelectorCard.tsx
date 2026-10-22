import React, { useState } from 'react';
import { Palette, CheckCircle2, FileText, ChevronDown, ChevronUp } from 'lucide-react';
import { useVisualArtifactStudioStore } from './useVisualArtifactStudioStore';
import { PRESET_DESIGN_SPECS } from './designSpecParser';
import type { DesignSystemSpec } from './designSpecTypes';

export const DesignSpecSelectorCard: React.FC = () => {
  const { activeSpec, setActiveSpec } = useVisualArtifactStudioStore();
  const [showMarkdownSource, setShowMarkdownSource] = useState(false);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/90 p-4 text-xs text-slate-200">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <Palette className="h-4 w-4 text-indigo-400" />
          <h3 className="font-semibold text-white">DESIGN.md 工业设计系统规范</h3>
        </div>
        <button
          type="button"
          onClick={() => {
            setShowMarkdownSource(!showMarkdownSource);
          }}
          className="inline-flex items-center gap-1 rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700 transition-colors"
        >
          <FileText className="h-3 w-3 text-indigo-400" />
          <span>{showMarkdownSource ? '收起规范源码' : '查看 DESIGN.md'}</span>
          {showMarkdownSource ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )}
        </button>
      </div>

      {/* 预置规范挑选栅格 */}
      <div className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        {PRESET_DESIGN_SPECS.map((spec: DesignSystemSpec) => {
          const isSelected = activeSpec.specId === spec.specId;
          const { colors, geometry } = spec.tokens;

          return (
            <button
              key={spec.specId}
              type="button"
              onClick={() => {
                setActiveSpec(spec);
              }}
              className={`flex flex-col items-start rounded-lg border p-3 text-left transition-all ${
                isSelected
                  ? 'border-indigo-500 bg-indigo-600/10 shadow-sm ring-1 ring-indigo-500/50'
                  : 'border-slate-800 bg-slate-800/40 hover:border-slate-700 hover:bg-slate-800/80'
              }`}
            >
              <div className="flex w-full items-center justify-between">
                <span className="font-semibold text-slate-100">{spec.name}</span>
                {isSelected && (
                  <CheckCircle2 className="h-3.5 w-3.5 text-indigo-400" />
                )}
              </div>

              <p className="mt-1 text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                {spec.description}
              </p>

              {/* 调色盘与圆角微缩预览 */}
              <div className="mt-2.5 flex items-center gap-1.5">
                <div
                  title="Primary Color"
                  className="h-3.5 w-3.5 rounded border border-white/20"
                  style={{ backgroundColor: colors.primary }}
                />
                <div
                  title="Accent Color"
                  className="h-3.5 w-3.5 rounded border border-white/20"
                  style={{ backgroundColor: colors.accent }}
                />
                <div
                  title="Surface Color"
                  className="h-3.5 w-3.5 rounded border border-white/20"
                  style={{ backgroundColor: colors.surface }}
                />
                <span className="ml-1 text-[10px] text-slate-400 font-mono">
                  R: {geometry.borderRadius}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* 可展开的 Markdown 源码预览 */}
      {showMarkdownSource && (
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-[11px] text-slate-300">
          <div className="text-slate-400 text-[10px] mb-1 font-semibold uppercase tracking-wider">
            当前规范原稿 ({activeSpec.name})
          </div>
          <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap leading-relaxed text-indigo-200/90 scrollbar-thin">
            {activeSpec.rawMarkdown}
          </pre>
        </div>
      )}
    </div>
  );
};
