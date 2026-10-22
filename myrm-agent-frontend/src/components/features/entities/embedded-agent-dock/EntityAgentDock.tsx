import React, { useState } from 'react';
import {
  Bot,
  X,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  MinusCircle,
  HelpCircle,
  Send,
  Sparkles,
  Layers,
  ArrowRight,
  Database,
} from 'lucide-react';
import { useEntityEmbeddedAgentStore } from './useEntityEmbeddedAgentStore';
import type { DossierStepRecord } from './entityEmbeddedAgentTypes';

export const EntityAgentDock: React.FC = () => {
  const {
    isDockOpen,
    activeEntity,
    currentSignedToken,
    stepLedger,
    chatHistory,
    closeEntityDock,
    resolveDisambiguation,
    sendUserMessage,
  } = useEntityEmbeddedAgentStore();

  const [inputText, setInputText] = useState<string>('');

  if (!isDockOpen || !activeEntity) {
    return null;
  }

  const handleSend = (e: React.FormEvent): void => {
    e.preventDefault();
    if (inputText.trim()) {
      sendUserMessage(inputText);
      setInputText('');
    }
  };

  const renderStepItem = (step: DossierStepRecord): React.ReactElement => {
    switch (step.status) {
      case 'verified':
        return (
          <div
            key={step.id}
            className="p-3 border rounded-lg bg-emerald-950/20 border-emerald-500/20 text-xs space-y-1"
          >
            <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
              <span>{step.title}</span>
            </div>
            {step.evidenceSource && (
              <div className="text-[10px] text-slate-400 flex items-center gap-1">
                <Database className="w-3 h-3 text-slate-500" />
                <span>证据源: {step.evidenceSource}</span>
              </div>
            )}
          </div>
        );

      case 'discarded':
        return (
          <div
            key={step.id}
            className="p-3 border rounded-lg bg-rose-950/20 border-rose-500/20 text-xs space-y-1.5"
          >
            <div className="flex items-center gap-1.5 text-rose-400 font-medium">
              <MinusCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{step.title}</span>
              <span className="text-[9px] px-1 py-0.2 rounded bg-rose-950 text-rose-300 border border-rose-800">
                已丢弃线索
              </span>
            </div>
            {step.discardedReason && (
              <p className="text-[11px] text-slate-300 leading-relaxed bg-slate-950/60 p-2 rounded border border-rose-900/30">
                <span className="text-rose-400 font-semibold">排除理由: </span>
                {step.discardedReason}
              </p>
            )}
          </div>
        );

      case 'pending_decision':
        return (
          <div
            key={step.id}
            className="p-3.5 border rounded-lg bg-amber-950/30 border-amber-500/30 text-xs space-y-2.5 animate-pulse-subtle"
          >
            <div className="flex items-center gap-1.5 text-amber-300 font-medium">
              <HelpCircle className="w-4 h-4 shrink-0 text-amber-400" />
              <span>{step.title}</span>
              <span className="text-[9px] px-1 py-0.2 rounded bg-amber-900/60 text-amber-300 border border-amber-700">
                需要人类就地仲裁
              </span>
            </div>
            {step.disambiguationPrompt && (
              <p className="text-xs text-slate-300">{step.disambiguationPrompt}</p>
            )}
            {step.disambiguationOptions && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                {step.disambiguationOptions.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => resolveDisambiguation(step.id, opt.id)}
                    className="p-2.5 text-left rounded-lg border bg-slate-900/90 hover:bg-slate-800 border-amber-500/30 hover:border-amber-400 transition-all text-xs space-y-1 group"
                  >
                    <div className="font-semibold text-white group-hover:text-amber-300 flex items-center justify-between">
                      <span>{opt.label}</span>
                      <ArrowRight className="w-3 h-3 text-amber-400 opacity-60 group-hover:opacity-100" />
                    </div>
                    <p className="text-[10px] text-slate-400 leading-tight">
                      {opt.description}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>
        );

      default:
        return (
          <div key={step.id} className="p-2 text-xs text-slate-400">
            {step.title}
          </div>
        );
    }
  };

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="entity-dock-title"
      className="fixed inset-0 z-50 flex items-center justify-end w-full h-full p-0 sm:p-4 bg-black/60 backdrop-blur-sm"
    >
      <section
        role="document"
        className="w-full sm:max-w-xl h-full sm:h-[92vh] flex flex-col overflow-hidden border sm:rounded-xl shadow-2xl bg-slate-900 border-slate-800 text-slate-100 animate-in slide-in-from-right duration-200"
      >
        {/* 顶部 Header */}
        <header className="flex items-center justify-between px-5 py-4 border-b border-slate-800/80 bg-slate-950/60 shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0">
              <Bot className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 id="entity-dock-title" className="text-sm font-semibold text-white truncate">
                  {activeEntity.title}
                </h2>
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                  {activeEntity.type.toUpperCase()}
                </span>
              </div>
              {currentSignedToken && (
                <div className="flex items-center gap-1 mt-0.5 text-[10px] text-emerald-400">
                  <ShieldCheck className="w-3 h-3 shrink-0" />
                  <span className="font-mono truncate max-w-[240px]">
                    {currentSignedToken.tokenString}
                  </span>
                  <span className="text-slate-500">· 免粘贴验签通过</span>
                </div>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={closeEntityDock}
            className="p-1.5 transition-colors rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 shrink-0"
            aria-label="关闭专属智能体抽屉"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* 身体区：上半部步态透明账本，下半部对话历史 */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* 推演步态与排除线索透明账本 */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-300 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-sky-400" />
                推演步态与丢弃线索透明账本 (Step Dossier & Dropped Leads)
              </span>
              <span className="text-[10px] text-slate-500">
                实时记录 {stepLedger.length} 项推演步
              </span>
            </div>
            <div className="space-y-2">
              {stepLedger.map(renderStepItem)}
            </div>
          </div>

          {/* 会话流 */}
          <div className="pt-3 border-t border-slate-800/80 space-y-3">
            <div className="text-xs font-semibold text-slate-400">
              实体专属会话线程 (Durable Entity Thread)
            </div>
            <div className="space-y-2.5">
              {chatHistory.map((msg) => (
                <div
                  key={msg.id}
                  className={`p-3 rounded-lg text-xs leading-relaxed ${
                    msg.sender === 'user'
                      ? 'bg-sky-950/40 border border-sky-500/30 text-white ml-6'
                      : msg.sender === 'system'
                      ? 'bg-slate-950/80 border border-slate-800 text-slate-400 font-mono text-[11px]'
                      : 'bg-slate-950/60 border border-slate-800/80 text-slate-200 mr-6'
                  }`}
                >
                  <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                    <span>{msg.sender === 'user' ? '您' : msg.sender === 'system' ? '系统信使' : '实体专属 Agent'}</span>
                    <span>{new Date(msg.timestamp).toLocaleTimeString()}</span>
                  </div>
                  <p>{msg.text}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 底部输入框 */}
        <footer className="p-4 border-t border-slate-800/80 bg-slate-950/60 shrink-0">
          <form onSubmit={handleSend} className="flex items-center gap-2">
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder={`向专属智能体询问关于【${activeEntity.title}】的任何细节...`}
              className="flex-1 px-3.5 py-2 text-xs border rounded-lg bg-slate-950 border-slate-800 text-slate-200 focus:outline-none focus:border-sky-500"
            />
            <button
              type="submit"
              disabled={!inputText.trim()}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium transition-colors border rounded-lg bg-sky-600 hover:bg-sky-500 text-white border-sky-500 shadow-sm disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" />
              <span>发送</span>
            </button>
          </form>
        </footer>
      </section>
    </dialog>
  );
};
