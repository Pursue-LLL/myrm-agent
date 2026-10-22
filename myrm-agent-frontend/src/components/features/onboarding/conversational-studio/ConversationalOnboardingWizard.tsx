'use client';

import React from 'react';
import {
  Bot,
  Send,
  Sparkles,
  Zap,
  CheckCircle2,
  ArrowRight,
  RotateCcw,
  Sliders,
  Shield,
  Layers,
} from 'lucide-react';
import { useConversationalOnboardingStore } from './useConversationalOnboardingStore';

export const ConversationalOnboardingWizard: React.FC = () => {
  const {
    messages,
    activeRecipeDraft,
    step,
    customInputText,
    setCustomInputText,
    selectPresetIntent,
    submitUserInput,
    toggleSkillSelection,
    updateRecipeDraft,
    applyRecipeAndComplete,
    resetOnboarding,
    isCompleted,
  } = useConversationalOnboardingStore();

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      submitUserInput(customInputText);
    }
  };

  if (isCompleted) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center text-slate-100 bg-slate-900/60 rounded-2xl border border-slate-700/80 shadow-2xl max-w-xl mx-auto">
        <div className="w-16 h-16 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 mb-4">
          <CheckCircle2 className="w-8 h-8" />
        </div>
        <h2 className="text-xl font-bold text-slate-100">
          恭喜！智能伙伴已成功就绪
        </h2>
        <p className="text-sm text-slate-400 mt-2 max-w-md">
          「{activeRecipeDraft?.suggestedName || '智能体'}」已完成专属技能挂载与参数调优，全程零命令行、零多余操作。
        </p>
        <div className="flex gap-3 mt-6">
          <button
            type="button"
            onClick={resetOnboarding}
            className="px-4 py-2 rounded-lg border border-slate-700 bg-slate-800 text-slate-300 text-xs font-medium hover:bg-slate-700 transition-colors flex items-center gap-1.5"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            重新配置
          </button>
          <button
            type="button"
            onClick={() => {
              // 模拟触发完成事件
              window.dispatchEvent(new CustomEvent('myrm:onboarding-finished'));
            }}
            className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors flex items-center gap-1.5 shadow-lg shadow-blue-500/20"
          >
            立即开启第一场对话
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col lg:flex-row h-[620px] w-full max-w-5xl rounded-2xl border border-slate-800 bg-slate-900/90 shadow-2xl backdrop-blur-md overflow-hidden text-slate-200">
      {/* Left Chat Pane */}
      <div className="flex-1 flex flex-col border-b lg:border-b-0 lg:border-r border-slate-800 bg-slate-950/40">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800/80 bg-slate-900/60">
          <div className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-blue-400" />
            <span className="font-semibold text-xs text-slate-200">
              对话式向导 · 边聊边配
            </span>
          </div>
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-300 border border-blue-500/20">
            Zero-CLI 极客脱敏
          </span>
        </div>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col ${
                msg.sender === 'user' ? 'items-end' : 'items-start'
              }`}
            >
              <div
                className={`max-w-[85%] rounded-xl p-3 text-xs leading-relaxed ${
                  msg.sender === 'user'
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-slate-800/80 border border-slate-700/60 text-slate-200'
                }`}
              >
                {msg.text}
              </div>

              {/* Interactive Options Cards */}
              {msg.interactiveOptions && step === 'intent_selection' && (
                <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-[95%]">
                  {msg.interactiveOptions.map((opt) => (
                    <button
                      key={opt.presetKey}
                      type="button"
                      onClick={() => { selectPresetIntent(opt.presetKey); }}
                      className="text-left p-2.5 rounded-lg border border-slate-800 bg-slate-900/70 hover:border-blue-500/60 hover:bg-blue-500/10 transition-all text-xs group"
                    >
                      <div className="font-semibold text-slate-200 group-hover:text-blue-300 flex items-center justify-between">
                        {opt.label}
                        <ArrowRight className="w-3 h-3 text-slate-500 group-hover:text-blue-400 transition-transform group-hover:translate-x-0.5" />
                      </div>
                      <div className="text-[11px] text-slate-400 mt-1 line-clamp-1">
                        {opt.description}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Input Bar */}
        <div className="p-3 border-t border-slate-800 bg-slate-900/40">
          <div className="flex items-center gap-2">
            <input
              type="text"
              aria-label="告诉我们您的工作需求"
              placeholder="或者用一句话描述：例如'写周报和分析竞品'..."
              value={customInputText}
              onChange={(e) => { setCustomInputText(e.target.value); }}
              onKeyDown={handleKeyDown}
              className="flex-1 text-xs px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
            />
            <button
              type="button"
              aria-label="发送需求"
              onClick={() => { submitUserInput(customInputText); }}
              className="p-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Right Recipe Preview Pane */}
      <div className="w-full lg:w-96 flex flex-col bg-slate-900/30 p-5 overflow-y-auto">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center gap-1.5 font-semibold text-xs text-slate-200">
            <Sparkles className="w-4 h-4 text-amber-400" />
            实时生成配方草案
          </div>
          {activeRecipeDraft && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-700/50">
              省 Token ~{activeRecipeDraft.estimatedTokenSavingPct}%
            </span>
          )}
        </div>

        {activeRecipeDraft ? (
          <div className="mt-4 space-y-4 text-xs flex-1 flex flex-col justify-between">
            <div className="space-y-3.5">
              <div>
                <label htmlFor="recipe-suggested-name" className="block text-slate-400 text-[11px] mb-1">伙伴名称</label>
                <input
                  id="recipe-suggested-name"
                  type="text"
                  value={activeRecipeDraft.suggestedName}
                  onChange={(e) => {
                    updateRecipeDraft({ suggestedName: e.target.value });
                  }}
                  className="w-full text-xs px-2.5 py-1.5 rounded bg-slate-800 border border-slate-700 text-slate-200 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <span className="block text-slate-400 text-[11px] mb-1">专业定位 (Role)</span>
                <div className="text-xs text-slate-200 font-medium px-2.5 py-1.5 rounded bg-slate-800/40 border border-slate-800">
                  {activeRecipeDraft.roleTitle}
                </div>
              </div>

              <div>
                <span className="block text-slate-400 text-[11px] mb-1">推荐算力档位</span>
                <div className="flex gap-2">
                  {(['turbo', 'pro'] as const).map((tier) => (
                    <button
                      key={tier}
                      type="button"
                      onClick={() => { updateRecipeDraft({ recommendedModelTier: tier }); }}
                      className={`flex-1 py-1 px-2 rounded border text-xs font-medium transition-colors ${
                        activeRecipeDraft.recommendedModelTier === tier
                          ? 'border-blue-500 bg-blue-500/20 text-blue-200'
                          : 'border-slate-800 bg-slate-800/40 text-slate-400 hover:border-slate-700'
                      }`}
                    >
                      {tier === 'turbo' ? 'Turbo (极速响应)' : 'Pro (深度推理)'}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <span className="block text-slate-400 text-[11px] mb-1">已推导挂载技能</span>
                <div className="space-y-1.5">
                  {activeRecipeDraft.recommendedSkills.map((skill) => (
                    <label
                      key={skill.id}
                      className={`flex items-center justify-between p-2 rounded-lg border text-xs cursor-pointer transition-colors ${
                        skill.selected
                          ? 'border-blue-500/40 bg-blue-500/10 text-slate-200'
                          : 'border-slate-800 bg-slate-800/30 text-slate-500'
                      }`}
                    >
                      <div>
                        <div className="font-medium text-xs">{skill.name}</div>
                        <div className="text-[10px] text-slate-400">{skill.category}</div>
                      </div>
                      <input
                        type="checkbox"
                        checked={skill.selected}
                        onChange={() => { toggleSkillSelection(skill.id); }}
                        className="rounded border-slate-700 text-blue-600 focus:ring-0"
                      />
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <button
              type="button"
              onClick={applyRecipeAndComplete}
              className="w-full mt-4 py-2.5 px-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs transition-colors flex items-center justify-center gap-1.5 shadow-lg shadow-blue-500/20"
            >
              <CheckCircle2 className="w-4 h-4" />
              一键确认并激活伙伴
            </button>
          </div>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-6 text-slate-500 text-xs">
            <Sliders className="w-8 h-8 mb-2 text-slate-600" />
            请先在左侧选择意图或输入您的需求，系统将秒级生成最佳配方。
          </div>
        )}
      </div>
    </div>
  );
};
