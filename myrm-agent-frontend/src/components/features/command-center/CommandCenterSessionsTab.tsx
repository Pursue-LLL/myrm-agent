import React, { useState } from 'react';
import {
  Search,
  Pin,
  PinOff,
  Download,
  FileText,
  Clock,
  Bot,
  Check,
} from 'lucide-react';
import { useCommandCenterStore } from './useCommandCenterStore';
import { filterSessions } from './commandCenterEngine';

export const CommandCenterSessionsTab: React.FC = () => {
  const {
    sessions,
    searchQuery,
    setSearchQuery,
    togglePinSession,
    exportSessionAuditPack,
    exportedAuditPack,
  } = useCommandCenterStore();

  const [copiedId, setCopiedId] = useState<string | null>(null);

  const filteredSessions = filterSessions(sessions, searchQuery);

  const handleExport = (sessionId: string) => {
    const pack = exportSessionAuditPack(sessionId);
    if (pack) {
      setCopiedId(sessionId);
      setTimeout(() => {
        setCopiedId(null);
      }, 2000);
    }
  };

  return (
    <div
      data-testid="command-center-sessions-tab"
      className="flex flex-col h-[460px] select-none text-slate-200"
    >
      {/* 搜索框 */}
      <div className="relative mb-3">
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="毫秒级搜索会话标题、负责人或标签 (如: UX, Gateway)..."
          className="w-full bg-slate-900 border border-slate-700/80 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
        />
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {filteredSessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-slate-500 text-xs">
            <Search className="w-6 h-6 mb-2 text-slate-600" />
            <span>未检索到匹配的会话历史</span>
          </div>
        ) : (
          filteredSessions.map((session) => (
            <div
              key={session.id}
              className={`flex items-center justify-between p-3 rounded-xl border transition-all ${
                session.isPinned
                  ? 'bg-slate-900/90 border-indigo-500/40 shadow-sm'
                  : 'bg-slate-900/40 border-slate-800 hover:border-slate-700'
              }`}
            >
              <div className="flex-1 min-w-0 mr-3">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-xs text-slate-100 truncate">
                    {session.title}
                  </span>
                  {session.isPinned && (
                    <span className="px-1.5 py-0.2 text-[9px] bg-indigo-500/20 text-indigo-300 rounded border border-indigo-500/30 font-medium">
                      置顶
                    </span>
                  )}
                </div>

                <div className="mt-1 flex items-center gap-3 text-[11px] text-slate-400">
                  <span className="inline-flex items-center gap-1">
                    <Bot className="w-3 h-3 text-indigo-400" />
                    <span>{session.agentName}</span>
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Clock className="w-3 h-3 text-slate-500" />
                    <span>{session.updatedAt}</span>
                  </span>
                  <span className="text-slate-500 font-mono">
                    {session.messageCount} 轮 / {session.tokenCount} T
                  </span>
                </div>

                <div className="mt-1.5 flex items-center gap-1 flex-wrap">
                  {session.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/50"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>

              {/* 右侧操作按钮 */}
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => togglePinSession(session.id)}
                  className={`p-1.5 rounded-lg border transition-colors ${
                    session.isPinned
                      ? 'bg-indigo-600/20 border-indigo-500/40 text-indigo-300 hover:bg-indigo-600/30'
                      : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
                  }`}
                  title={session.isPinned ? '取消置顶' : '固定置顶'}
                  aria-label={session.isPinned ? '取消置顶' : '固定置顶'}
                >
                  {session.isPinned ? <PinOff className="w-3.5 h-3.5" /> : <Pin className="w-3.5 h-3.5" />}
                </button>

                <button
                  type="button"
                  onClick={() => handleExport(session.id)}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs transition-colors"
                  title="导出全要素审计包"
                >
                  {copiedId === session.id ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-emerald-400 text-[11px]">已打包</span>
                    </>
                  ) : (
                    <>
                      <Download className="w-3.5 h-3.5" />
                      <span className="text-[11px]">导出审计包</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* 底部导出回显提示 */}
      {exportedAuditPack && (
        <div className="mt-2.5 p-2 bg-indigo-950/40 border border-indigo-800/40 rounded-xl text-[11px] text-indigo-200 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <FileText className="w-3.5 h-3.5 text-indigo-400" />
            <span className="truncate max-w-[340px]">
              审计包就绪：{exportedAuditPack.title}
            </span>
          </div>
          <span className="text-[10px] text-indigo-400 font-mono">
            {exportedAuditPack.exportFormat.toUpperCase()}
          </span>
        </div>
      )}
    </div>
  );
};
