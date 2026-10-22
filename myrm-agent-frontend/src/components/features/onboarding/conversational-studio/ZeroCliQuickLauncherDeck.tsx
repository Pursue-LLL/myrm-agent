'use client';

import React from 'react';
import {
  ShieldCheck,
  Zap,
  Bot,
  Activity,
  Layers,
  Sparkles,
  ArrowRight,
  CheckCircle2,
} from 'lucide-react';
import { useConversationalOnboardingStore } from './useConversationalOnboardingStore';

interface ZeroCliQuickLauncherDeckProps {
  onLaunchWizard?: () => void;
  onOpenStudio?: () => void;
}

export const ZeroCliQuickLauncherDeck: React.FC<ZeroCliQuickLauncherDeckProps> = ({
  onLaunchWizard,
  onOpenStudio,
}) => {
  const launcherServices = useConversationalOnboardingStore((s) => s.launcherServices);
  const resetOnboarding = useConversationalOnboardingStore((s) => s.resetOnboarding);

  const handleLaunch = () => {
    resetOnboarding();
    if (onLaunchWizard) {
      onLaunchWizard();
    }
  };

  return (
    <div className="w-full max-w-4xl rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-2xl backdrop-blur-md text-slate-200">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-blue-400">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold text-sm text-slate-100 flex items-center gap-2">
              零终端纯图形化工作台
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-500/30">
                100% GUI-First
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              免除任何黑框命令行配置，环境、沙箱与模型开箱即用
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={handleLaunch}
          className="self-start sm:self-auto px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors flex items-center gap-1.5 shadow-md shadow-blue-500/20"
        >
          <Sparkles className="w-3.5 h-3.5 text-amber-300" />
          启动对话式配置向导
        </button>
      </div>

      {/* Services Health Grid */}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
        {launcherServices.map((svc) => (
          <div
            key={svc.id}
            className="p-3.5 rounded-xl border border-slate-800/80 bg-slate-950/40 text-xs flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-blue-400" />
                  {svc.name}
                </span>
                <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                  <CheckCircle2 className="w-3 h-3" />
                  就绪
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-1">{svc.details}</p>
            </div>
            <div className="mt-3 pt-2 border-t border-slate-800/60 flex justify-between text-[10px] text-slate-500 font-mono">
              <span>状态探针</span>
              <span className="text-slate-400">{svc.latencyMs}ms 响应</span>
            </div>
          </div>
        ))}
      </div>

      {/* Quick Launch Action Cards */}
      <div className="mt-4 pt-4 border-t border-slate-800 grid grid-cols-1 sm:grid-cols-2 gap-3">
        <button
          type="button"
          onClick={handleLaunch}
          className="text-left p-3.5 rounded-xl border border-slate-800 bg-slate-800/40 hover:border-slate-700 hover:bg-slate-800/70 transition-all text-xs group"
        >
          <div className="flex items-center justify-between text-slate-200 font-medium">
            <span className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-sky-400" />
              “边聊边配”快速入职
            </span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-sky-400 transition-transform group-hover:translate-x-0.5" />
          </div>
          <p className="text-[11px] text-slate-400 mt-1">
            自然语言对答自动推导 Agent Profile 与技能组合，3 秒完成个性化定制。
          </p>
        </button>

        {onOpenStudio && (
          <button
            type="button"
            onClick={onOpenStudio}
            className="text-left p-3.5 rounded-xl border border-slate-800 bg-slate-800/40 hover:border-slate-700 hover:bg-slate-800/70 transition-all text-xs group"
          >
            <div className="flex items-center justify-between text-slate-200 font-medium">
              <span className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-purple-400" />
                一站式智能体工坊
              </span>
              <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-purple-400 transition-transform group-hover:translate-x-0.5" />
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              集中管控已有智能体伙伴、专属技能池、MCP 连接器与知识库挂载。
            </p>
          </button>
        )}
      </div>
    </div>
  );
};
