import React, { useState } from 'react';
import {
  Bot,
  CheckCircle2,
  FileText,
  FolderLock,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Stethoscope,
} from 'lucide-react';
import { useProgressiveOnboardingStore } from './useProgressiveOnboardingStore';
import { DeferredConfigPrompt } from './DeferredConfigPrompt';
import { ProviderFailureAttributionCard } from './ProviderFailureAttributionCard';
import { SelfHealingDoctor } from './SelfHealingDoctor';
import type { OnboardingWorkspaceTab } from './progressiveOnboardingTypes';

interface ProgressiveOnboardingGatewayProps {
  className?: string;
}

export const ProgressiveOnboardingGateway: React.FC<ProgressiveOnboardingGatewayProps> = ({
  className = '',
}) => {
  const {
    stage,
    activeTab,
    isFirstChatDispatched,
    firstChatPrompt,
    setActiveTab,
    dispatchFirstChat,
  } = useProgressiveOnboardingStore();

  const [inputMessage, setInputMessage] = useState<string>(firstChatPrompt);

  const handleSendPrompt = (): void => {
    if (inputMessage.trim()) {
      dispatchFirstChat(inputMessage.trim());
    }
  };

  const tabs: Array<{ id: OnboardingWorkspaceTab; label: string; icon: React.FC<{ className?: string }> }> = [
    { id: 'chat', label: '对话 (Chat)', icon: Bot },
    { id: 'files', label: '文件与工件 (Files)', icon: FileText },
    { id: 'approvals', label: '高危审批 (Approvals)', icon: FolderLock },
    { id: 'search', label: '全局搜索 (Search)', icon: Search },
    { id: 'settings', label: '设置 (Settings)', icon: Settings },
  ];

  return (
    <section
      aria-label="渐进式延迟配置新手引导与五合一工作台网关"
      className={`relative flex h-full w-full flex-col bg-slate-950 text-slate-100 overflow-y-auto p-4 sm:p-6 space-y-4 ${className}`}
    >
      {/* 顶部标题与五合一工作台导航抽屉 */}
      <header
        aria-label="工作台多合一导航顶栏"
        className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-tight">
                零门槛开箱即聊与多合一工作台
              </h2>
              <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-mono text-emerald-400 border border-emerald-500/20">
                Zero-Config Ready
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              内置默认通用智能体 · 复杂配置按需延迟触发 · 钥匙/地址/房间类比归因
            </p>
          </div>
        </div>

        {/* 五合一 Tab 导航 */}
        <nav
          aria-label="五合一工作台标签导航"
          className="flex items-center rounded-lg bg-slate-900/90 p-1 border border-slate-800 text-xs"
        >
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setActiveTab(tab.id);
                }}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                aria-label={`切换到 ${tab.label}`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </header>

      {/* 挂载按需延迟配置与新手归因卡片 */}
      <DeferredConfigPrompt />
      <ProviderFailureAttributionCard />

      {/* 核心工作区：开箱即聊面板 */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow-sm backdrop-blur">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-indigo-400" />
            <span className="text-sm font-semibold text-white">默认通用智能体 (General Assistant)</span>
          </div>
          <span className="text-[11px] font-mono text-slate-400">
            通道: 本地嗅探 / 免费试用基线
          </span>
        </div>

        {/* 对话首句即聊输入框 */}
        <div className="mt-3">
          <div className="relative">
            <textarea
              rows={3}
              value={inputMessage}
              onChange={(e) => {
                setInputMessage(e.target.value);
              }}
              placeholder="无需任何配置，直接输入您的需求（如：帮我总结这段文字、写一个 Python 脚本）..."
              className="w-full rounded-lg border border-slate-700 bg-slate-950/80 p-3 text-xs text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none font-sans"
              aria-label="开箱即聊首句输入框"
            />
            <div className="absolute right-2.5 bottom-2.5">
              <button
                type="button"
                onClick={handleSendPrompt}
                className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 transition-colors shadow-sm"
                aria-label="发送首句指令"
              >
                <Send className="w-3.5 h-3.5" />
                <span>即刻发送</span>
              </button>
            </div>
          </div>

          {isFirstChatDispatched && (
            <div className="mt-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-between text-xs text-emerald-300">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>首句指令已成功派发，3 秒内验证产品核心价值！</span>
              </div>
              <span className="font-mono text-[10px] text-emerald-400">Dispatch Status: 200 OK</span>
            </div>
          )}
        </div>
      </div>

      {/* 模块：一键自检自愈诊断探针 */}
      <SelfHealingDoctor />
    </section>
  );
};
