import React, { useState } from 'react';
import {
  Play,
  X,
  Send,
  Sparkles,
  Trash2,
  Clock,
  Zap,
  Bot,
  User,
} from 'lucide-react';
import { useModelSpotlightStore } from './useModelSpotlightStore';
import { formatTokenCount } from './spotlightCatalogData';

export const SpotlightPlaygroundModal: React.FC = () => {
  const {
    isPlaygroundOpen,
    playgroundSpotlight,
    playgroundMessages,
    isPlaygroundThinking,
    closePlayground,
    sendPlaygroundPrompt,
    clearPlayground,
    openMountModal,
  } = useModelSpotlightStore();

  const [inputVal, setInputVal] = useState('');

  if (!isPlaygroundOpen || !playgroundSpotlight) {
    return null;
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputVal.trim() || isPlaygroundThinking) {
      return;
    }
    const text = inputVal;
    setInputVal('');
    sendPlaygroundPrompt(text);
  };

  const handleSelectSamplePrompt = (prompt: string) => {
    if (isPlaygroundThinking) {
      return;
    }
    sendPlaygroundPrompt(prompt);
  };

  const handleSwitchToMount = () => {
    const target = playgroundSpotlight;
    closePlayground();
    openMountModal(target);
  };

  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity"
        aria-hidden="true"
      />
      <dialog
        open
        aria-labelledby="playground-modal-title"
        className="fixed inset-0 z-50 m-auto w-full max-w-3xl max-h-[85vh] bg-slate-900 border border-slate-700/80 rounded-xl shadow-2xl p-0 flex flex-col text-slate-100 overflow-hidden"
        data-testid="spotlight-playground-modal"
      >
        {/* 顶部标题栏 */}
        <header className="px-5 py-3.5 border-b border-slate-800 bg-slate-950/60 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <div className="p-1.5 rounded-lg bg-indigo-600/30 text-indigo-400 border border-indigo-500/40">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3
                  id="playground-modal-title"
                  className="font-bold text-base text-white"
                >
                  {playgroundSpotlight.name} 极速试用沙箱
                </h3>
                <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
                  {formatTokenCount(playgroundSpotlight.contextWindow)} ctx
                </span>
              </div>
              <p className="text-xs text-slate-400">
                临时沙箱环境，试用过程不影响当前生产会话与智能体参数
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={handleSwitchToMount}
              aria-label="一键挂载至当前智能体"
              className="px-2.5 py-1 text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white rounded flex items-center space-x-1"
            >
              <Zap className="w-3.5 h-3.5 fill-current text-amber-300" />
              <span>挂载此模型</span>
            </button>
            <button
              type="button"
              onClick={closePlayground}
              aria-label="关闭试用沙箱"
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* 快捷 Prompt 标签区 */}
        <div className="px-5 py-2.5 bg-slate-950/40 border-b border-slate-800/80">
          <div className="text-[11px] font-semibold text-slate-400 mb-1.5 flex items-center space-x-1">
            <Play className="w-3 h-3 text-indigo-400" />
            <span>基准推荐测试题（点击立即体验）：</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {playgroundSpotlight.samplePrompts.map((sample) => (
              <button
                key={sample}
                type="button"
                disabled={isPlaygroundThinking}
                onClick={() => handleSelectSamplePrompt(sample)}
                className="text-left text-xs px-2.5 py-1 rounded bg-slate-800/70 hover:bg-indigo-950/50 hover:border-indigo-500/50 text-slate-300 border border-slate-700/60 transition-colors truncate max-w-full"
              >
                {sample}
              </button>
            ))}
          </div>
        </div>

        {/* 消息滚动流 */}
        <div
          className="flex-1 p-5 overflow-y-auto space-y-4 bg-slate-900/50"
          data-testid="playground-message-list"
        >
          {playgroundMessages.map((msg) => (
            <div
              key={msg.id}
              className={`flex items-start space-x-3 ${
                msg.role === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              {msg.role === 'assistant' && (
                <div className="w-7 h-7 rounded-full bg-indigo-600/30 text-indigo-400 flex items-center justify-center border border-indigo-500/40 shrink-0 mt-0.5">
                  <Bot className="w-4 h-4" />
                </div>
              )}
              <div
                className={`max-w-[85%] rounded-lg px-4 py-2.5 text-xs leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-800/90 text-slate-200 border border-slate-700/80 whitespace-pre-wrap'
                }`}
              >
                <div>{msg.content}</div>
                {msg.latencyMs && (
                  <div className="mt-1 text-[10px] text-slate-400 flex items-center space-x-1">
                    <Clock className="w-2.5 h-2.5 text-sky-400" />
                    <span>首字响应: {msg.latencyMs}ms</span>
                  </div>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="w-7 h-7 rounded-full bg-slate-700 text-slate-300 flex items-center justify-center shrink-0 mt-0.5">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))}

          {isPlaygroundThinking && (
            <div className="flex items-center space-x-2 text-xs text-indigo-300 animate-pulse pl-10">
              <Sparkles className="w-3.5 h-3.5" />
              <span>{playgroundSpotlight.name} 正在深度推理生成中...</span>
            </div>
          )}
        </div>

        {/* 底部输入框与操作栏 */}
        <footer className="p-3 border-t border-slate-800 bg-slate-950/70">
          <form onSubmit={handleSubmit} className="flex items-center space-x-2">
            <button
              type="button"
              onClick={clearPlayground}
              title="清空临时会话"
              aria-label="清空临时会话"
              className="p-2 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
            <input
              type="text"
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              placeholder={`向 ${playgroundSpotlight.name} 提问测试...`}
              disabled={isPlaygroundThinking}
              className="flex-1 bg-slate-800/80 text-white text-xs px-3 py-2 rounded-lg border border-slate-700/80 focus:outline-none focus:border-indigo-500 transition-colors"
            />
            <button
              type="submit"
              disabled={!inputVal.trim() || isPlaygroundThinking}
              aria-label="发送测试问题"
              className="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg flex items-center space-x-1.5 transition-all"
            >
              <Send className="w-3.5 h-3.5" />
              <span>发送</span>
            </button>
          </form>
        </footer>
      </dialog>
    </>
  );
};
