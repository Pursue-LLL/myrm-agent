import React, { useState } from 'react';
import {
  X,
  GitFork,
  Sparkles,
  FileCode,
  Send,
  Terminal,
  ShieldCheck,
  ChevronRight,
  HelpCircle,
} from 'lucide-react';
import { useSideTrackStore } from './useSideTrackStore';

export interface SideTrackExplainerDrawerProps {
  className?: string;
}

export const SideTrackExplainerDrawer: React.FC<SideTrackExplainerDrawerProps> = ({
  className = '',
}) => {
  const {
    isDrawerOpen,
    activeSession,
    selectedCodeSnapshot,
    closeSideTrack,
    selectCodeSnapshot,
    sendInquiry,
  } = useSideTrackStore();

  const [inputQuery, setInputQuery] = useState('');
  const [showCodeViewer, setShowCodeViewer] = useState(false);

  if (!isDrawerOpen || !activeSession) {
    return null;
  }

  const { snapshot, messages, presetInquiries, status } = activeSession;

  const handleSend = (e?: React.FormEvent) => {
    if (e) {
      e.preventDefault();
    }
    if (!inputQuery.trim()) {
      return;
    }
    sendInquiry(inputQuery);
    setInputQuery('');
  };

  const handleChipClick = (inquiry: string) => {
    sendInquiry(inquiry);
  };

  return (
    <aside
      data-testid="side-track-explainer-drawer"
      aria-label="侧边独立解释分支"
      className={`fixed top-0 right-0 z-50 h-full w-full sm:w-[480px] bg-zinc-900/98 backdrop-blur-xl border-l border-zinc-800 shadow-2xl flex flex-col font-sans transition-all duration-300 ${className}`}
    >
      {/* 1. 抽屉顶部导航头 */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 bg-zinc-950/70">
        <div className="flex items-center gap-2 truncate">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0">
            <GitFork className="w-4 h-4" />
          </div>
          <div className="truncate">
            <div className="flex items-center gap-1.5">
              <h2 className="text-xs font-bold text-zinc-100 truncate">
                侧边独立解释分支
              </h2>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono shrink-0">
                只读快照
              </span>
            </div>
            <p className="text-[10px] text-zinc-400 truncate">
              源自主任务: {snapshot.mainTaskName}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={closeSideTrack}
          aria-label="关闭侧边解释抽屉"
          title="关闭"
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors shrink-0"
        >
          <X className="w-4 h-4" />
        </button>
      </header>

      {/* 2. 状态隔离保证条 (Zero-Context Pollution Banner) */}
      <div className="px-3.5 py-2 bg-indigo-950/30 border-b border-indigo-500/20 flex items-center justify-between text-[11px] text-indigo-300">
        <span className="flex items-center gap-1 font-mono">
          <ShieldCheck className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
          主 Agent 全速执行中 · 零上下文污染
        </span>
        {snapshot.activeStep && (
          <span className="text-[10px] text-zinc-400 truncate max-w-[140px] font-mono">
            {snapshot.activeStep.stepTitle}
          </span>
        )}
      </div>

      {/* 3. 快照挂载代码文件标签与切换 */}
      {snapshot.codeSnapshots.length > 0 && (
        <div className="px-3 py-2 border-b border-zinc-800 bg-zinc-950/40 space-y-1.5">
          <div className="flex items-center justify-between text-[11px] text-zinc-400">
            <span className="flex items-center gap-1">
              <FileCode className="w-3 h-3 text-cyan-400" />
              挂载代码快照 ({snapshot.codeSnapshots.length})
            </span>
            <button
              type="button"
              onClick={() => {
                setShowCodeViewer(!showCodeViewer);
              }}
              className="text-[10px] text-indigo-400 hover:underline"
            >
              {showCodeViewer ? '折叠代码预览' : '展开代码预览'}
            </button>
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
            {snapshot.codeSnapshots.map((file) => {
              const isSelected = selectedCodeSnapshot?.filePath === file.filePath;
              return (
                <button
                  key={file.filePath}
                  type="button"
                  onClick={() => {
                    selectCodeSnapshot(file);
                    setShowCodeViewer(true);
                  }}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono whitespace-nowrap border transition-colors ${
                    isSelected
                      ? 'bg-zinc-800 text-cyan-300 border-cyan-500/40'
                      : 'bg-zinc-950 text-zinc-400 border-zinc-800 hover:border-zinc-700'
                  }`}
                >
                  {file.filePath.split('/').pop()}
                </button>
              );
            })}
          </div>

          {showCodeViewer && selectedCodeSnapshot && (
            <div className="mt-1 p-2 rounded-lg bg-zinc-950 border border-zinc-800 text-[11px] font-mono overflow-x-auto max-h-36">
              <div className="text-[10px] text-zinc-500 pb-1 border-b border-zinc-850">
                {selectedCodeSnapshot.filePath} ({selectedCodeSnapshot.language})
              </div>
              <pre className="text-zinc-300 mt-1 whitespace-pre-wrap">
                {selectedCodeSnapshot.codeSnippet}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* 4. 对话消息列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3.5">
        {messages.map((msg) => {
          if (msg.sender === 'system') {
            return (
              <div
                key={msg.id}
                className="p-2.5 rounded-xl bg-zinc-950/80 border border-zinc-800 text-xs text-zinc-400 leading-relaxed font-sans flex items-start gap-2"
              >
                <Sparkles className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                <p>{msg.content}</p>
              </div>
            );
          }

          if (msg.sender === 'user') {
            return (
              <div key={msg.id} className="flex justify-end">
                <div className="max-w-[85%] p-3 rounded-2xl rounded-tr-sm bg-indigo-600 text-white text-xs leading-relaxed shadow-md">
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            );
          }

          return (
            <div key={msg.id} className="flex justify-start">
              <div className="max-w-[90%] p-3.5 rounded-2xl rounded-tl-sm bg-zinc-950 border border-zinc-800 text-xs text-zinc-200 leading-relaxed shadow-sm space-y-2">
                <div className="flex items-center gap-1.5 text-[10px] text-zinc-500 font-mono pb-1 border-b border-zinc-850">
                  <Terminal className="w-3 h-3 text-indigo-400" />
                  <span>只读架构师分析</span>
                </div>
                <div className="whitespace-pre-wrap font-sans text-zinc-300 leading-normal">
                  {msg.content}
                </div>
              </div>
            </div>
          );
        })}

        {status === 'generating' && (
          <div className="flex justify-start">
            <div className="p-3 rounded-xl bg-zinc-950 border border-zinc-800 text-xs text-indigo-400 flex items-center gap-2 animate-pulse font-mono">
              <Sparkles className="w-3.5 h-3.5" />
              <span>正在推导原理解释...</span>
            </div>
          </div>
        )}
      </div>

      {/* 5. 智能推荐快捷提问芯片 */}
      {presetInquiries.length > 0 && (
        <div className="px-4 py-2 border-t border-zinc-850 bg-zinc-950/50 space-y-1">
          <div className="flex items-center gap-1 text-[10px] text-zinc-500 font-mono">
            <HelpCircle className="w-3 h-3 text-indigo-400" />
            <span>推荐探究问题:</span>
          </div>
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
            {presetInquiries.map((inq, idx) => (
              <button
                key={`inq-${idx}`}
                type="button"
                onClick={() => {
                  handleChipClick(inq);
                }}
                className="px-2 py-1 rounded-lg bg-zinc-800/80 hover:bg-zinc-700/80 text-[11px] text-zinc-300 whitespace-nowrap border border-zinc-700 transition-colors flex items-center gap-1"
              >
                <span>{inq}</span>
                <ChevronRight className="w-3 h-3 text-zinc-500" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 6. 底部提问输入栏 */}
      <footer className="p-3.5 border-t border-zinc-800 bg-zinc-950/90">
        <form onSubmit={handleSend} className="flex items-center gap-2">
          <input
            type="text"
            value={inputQuery}
            onChange={(e) => {
              setInputQuery(e.target.value);
            }}
            placeholder="询问当前步骤设计原理、架构决策或代码实现..."
            className="flex-1 px-3 py-2 text-xs bg-zinc-900 text-zinc-100 rounded-xl border border-zinc-750 focus:outline-none focus:border-indigo-500 placeholder-zinc-500 font-sans"
          />
          <button
            type="submit"
            disabled={!inputQuery.trim() || status === 'generating'}
            aria-label="发送提问"
            className="p-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl disabled:opacity-40 transition-colors flex items-center justify-center shrink-0 shadow"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </footer>
    </aside>
  );
};
