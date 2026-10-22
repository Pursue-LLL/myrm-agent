import React, { useState } from 'react';
import {
  Download,
  Bot,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  X,
  Layers,
  Key,
  ArrowRight,
} from 'lucide-react';
import { useShareableTemplateStore } from './useShareableTemplateStore';

export const FrictionlessCloneDeck: React.FC = () => {
  const {
    isCloneDeckOpen,
    previewTemplate,
    dependencyReport,
    lastCloneResult,
    closeCloneDeck,
    executeClone,
  } = useShareableTemplateStore();

  const [selectedModel, setSelectedModel] = useState<string>('');

  if (!isCloneDeckOpen || !previewTemplate) {
    return null;
  }

  const effectiveModel =
    selectedModel ||
    (dependencyReport?.modelAvailable
      ? previewTemplate.baseModel
      : dependencyReport?.recommendedFallbackModel ?? previewTemplate.baseModel);

  const handleClone = (): void => {
    executeClone(effectiveModel);
  };

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="clone-deck-title"
      className="fixed inset-0 z-50 flex items-center justify-center w-full h-full p-4 bg-black/60 backdrop-blur-sm"
    >
      <section
        role="document"
        className="w-full max-w-lg overflow-hidden border rounded-xl shadow-2xl bg-slate-900 border-slate-800 text-slate-100 animate-in fade-in zoom-in-95 duration-150"
      >
        <header className="flex items-center justify-between px-6 py-4 border-b border-slate-800/80 bg-slate-950/40">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <Download className="w-5 h-5" />
            </div>
            <div>
              <h2 id="clone-deck-title" className="text-base font-semibold leading-tight text-white">
                一键克隆智能体
              </h2>
              <p className="text-xs text-slate-400">免配置导入、模型自动对齐与沙盒隔离</p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeCloneDeck}
            className="p-1.5 transition-colors rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
            aria-label="关闭克隆甲板"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        <div className="p-6 space-y-4">
          {lastCloneResult?.success ? (
            <div className="p-5 border rounded-lg bg-emerald-950/30 border-emerald-500/30 text-center space-y-3">
              <div className="inline-flex p-3 rounded-full bg-emerald-500/20 text-emerald-400">
                <CheckCircle2 className="w-8 h-8" />
              </div>
              <h3 className="text-base font-semibold text-white">克隆成功！</h3>
              <p className="text-xs text-slate-300">
                智能体 <span className="text-emerald-400 font-medium">{lastCloneResult.agentName}</span> 已成功导入并配置就绪。
              </p>
              <div className="text-[11px] font-mono text-slate-400">
                分配 ID: {lastCloneResult.clonedAgentId} | 底模: {lastCloneResult.appliedModel}
              </div>
            </div>
          ) : (
            <>
              {/* 模板详情 */}
              <div className="p-4 border rounded-lg bg-slate-950/60 border-slate-800/80 space-y-2.5">
                <div className="flex items-start gap-3">
                  <div className="p-2.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0">
                    <Bot className="w-5 h-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-white truncate">{previewTemplate.title}</h3>
                      <span className="text-[11px] text-slate-400">{previewTemplate.authorHandle}</span>
                    </div>
                    <p className="mt-1 text-xs text-slate-300 line-clamp-2">
                      {previewTemplate.description || '无描述'}
                    </p>
                  </div>
                </div>

                {/* Prompt 摘要 */}
                <div className="p-2.5 rounded bg-slate-900 border border-slate-800 text-[11px] font-mono text-slate-400 line-clamp-2">
                  {previewTemplate.systemPrompt}
                </div>
              </div>

              {/* 模型与依赖对齐诊断报告 */}
              <div className="p-4 border rounded-lg bg-slate-950/40 border-slate-800/80 space-y-3">
                <div className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-sky-400" /> 运行环境自检与对齐
                </div>

                {/* 模型对齐状态 */}
                <div className="text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">原生推荐底模:</span>
                    <span className="font-mono text-slate-200">{previewTemplate.baseModel}</span>
                  </div>

                  {dependencyReport && !dependencyReport.modelAvailable && (
                    <div className="p-2.5 rounded bg-amber-950/30 border border-amber-500/30 text-amber-300 text-[11px] flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <div>
                        <span>本地环境未检测到底模 </span>
                        <code className="font-mono font-semibold">{previewTemplate.baseModel}</code>
                        <span>，系统已为您自动匹配最佳平替：</span>
                        <span className="font-mono font-bold text-white ml-1">
                          {dependencyReport.recommendedFallbackModel}
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                {/* 技能依赖检查 */}
                {previewTemplate.requiredSkills.length > 0 && (
                  <div className="pt-2 border-t border-slate-800/60">
                    <span className="text-[11px] text-slate-400 flex items-center gap-1 mb-1.5">
                      <Layers className="w-3 h-3" /> 技能依赖:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {previewTemplate.requiredSkills.map((skill) => {
                        const isMissing = dependencyReport?.missingSkills.includes(skill);
                        return (
                          <span
                            key={skill}
                            className={`px-2 py-0.5 text-[10px] rounded border ${
                              isMissing
                                ? 'bg-amber-950/40 text-amber-400 border-amber-600/40'
                                : 'bg-slate-800 text-sky-300 border-sky-900/50'
                            }`}
                          >
                            {skill} {isMissing ? '(待装载)' : ''}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 密钥槽位提醒 */}
                {previewTemplate.environmentKeySlots.length > 0 && (
                  <div className="pt-2 border-t border-slate-800/60">
                    <span className="text-[11px] text-slate-400 flex items-center gap-1 mb-1">
                      <Key className="w-3 h-3 text-emerald-400" /> 运行时变量插槽 (克隆后可填):
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {previewTemplate.environmentKeySlots.map((slot) => (
                        <span
                          key={slot}
                          className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-slate-900 text-slate-400 border border-slate-800"
                        >
                          {slot}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        <footer className="flex items-center justify-between px-6 py-3.5 border-t border-slate-800/80 bg-slate-950/30">
          <button
            type="button"
            onClick={closeCloneDeck}
            className="px-3.5 py-1.5 text-xs font-medium transition-colors border rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border-slate-700"
          >
            {lastCloneResult?.success ? '完成' : '取消'}
          </button>
          {!lastCloneResult?.success && (
            <button
              type="button"
              onClick={handleClone}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium transition-colors border rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-500 shadow-sm"
            >
              <span>一键克隆到本地</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </footer>
      </section>
    </dialog>
  );
};
