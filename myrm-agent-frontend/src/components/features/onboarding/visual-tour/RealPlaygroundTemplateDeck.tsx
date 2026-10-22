import React from 'react';
import { Sparkles, Play, Clock, ArrowRight, Tag } from 'lucide-react';
import { useVisualTourStore } from './useVisualTourStore';
import type { PlaygroundTemplate } from './visualTourTypes';

export interface RealPlaygroundTemplateDeckProps {
  readonly onSelectTemplate?: (template: PlaygroundTemplate) => void;
  readonly className?: string;
}

export const RealPlaygroundTemplateDeck: React.FC<RealPlaygroundTemplateDeckProps> = ({
  onSelectTemplate,
  className = '',
}) => {
  const { templates, selectTemplate, selectedTemplate } = useVisualTourStore();

  const handleApplyTemplate = (template: PlaygroundTemplate) => {
    selectTemplate(template);
    if (onSelectTemplate) {
      onSelectTemplate(template);
    }
  };

  return (
    <div className={`w-full ${className}`} data-testid="playground-template-deck">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-500/10 text-indigo-400">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <h3 className="text-xs font-semibold text-slate-200">30 秒真实场景即刻体验</h3>
        </div>
        <span className="text-[11px] text-slate-400">一键预填上下文与执行指令</span>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {templates.map((template) => {
          const isSelected = selectedTemplate?.id === template.id;

          return (
            <div
              key={template.id}
              data-testid={`playground-template-card-${template.id}`}
              className={`flex flex-col justify-between rounded-xl border p-4 transition-all duration-200 ${
                isSelected
                  ? 'border-indigo-500/80 bg-indigo-950/20 shadow-md ring-1 ring-indigo-500/30'
                  : 'border-slate-800 bg-slate-900/60 hover:border-slate-700 hover:bg-slate-900'
              }`}
            >
              <div>
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center rounded-md bg-indigo-500/10 px-2 py-0.5 text-[10px] font-medium text-indigo-400">
                    {template.category}
                  </span>
                  <span className="flex items-center gap-1 text-[10px] text-slate-400">
                    <Clock className="h-3 w-3 text-slate-500" />
                    约 {template.estimatedSeconds}s 交付
                  </span>
                </div>

                <h4 className="mt-2 text-xs font-semibold text-slate-100">{template.title}</h4>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
                  {template.description}
                </p>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  {template.tags.map((tag) => {
                    return (
                      <span
                        key={tag}
                        className="inline-flex items-center gap-0.5 rounded bg-slate-800/80 px-1.5 py-0.5 text-[9px] text-slate-300"
                      >
                        <Tag className="h-2.5 w-2.5 text-slate-400" />
                        {tag}
                      </span>
                    );
                  })}
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-800/60 flex items-center justify-between">
                <span className="text-[10px] text-slate-500 truncate max-w-[140px]">
                  点此载入沙盒执行
                </span>
                <button
                  type="button"
                  onClick={() => {
                    handleApplyTemplate(template);
                  }}
                  className="flex items-center gap-1 rounded-lg bg-indigo-600/90 px-2.5 py-1 text-xs font-medium text-white shadow-xs hover:bg-indigo-500 transition-colors"
                >
                  <Play className="h-3 w-3 fill-current" />
                  <span>载入体验</span>
                  <ArrowRight className="h-3 w-3" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
