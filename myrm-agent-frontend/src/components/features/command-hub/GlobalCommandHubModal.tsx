import React, { useEffect, useRef } from 'react';
import {
  Activity,
  BookOpen,
  Bot,
  Command,
  Download,
  FileText,
  GitBranch,
  GitCommit,
  History,
  Laptop,
  PlusCircle,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { useGlobalCommandHubStore } from './useGlobalCommandHubStore';
import { useGlobalCommandShortcuts } from './useGlobalCommandShortcuts';
import { CommandCategoryFilterBadge } from './CommandCategoryFilterBadge';
import type { CommandItem } from './globalCommandHubTypes';

interface GlobalCommandHubModalProps {
  className?: string;
}

export const GlobalCommandHubModal: React.FC<GlobalCommandHubModalProps> = ({
  className = '',
}) => {
  useGlobalCommandShortcuts();

  const {
    isOpen,
    searchQuery,
    selectedIndex,
    recentCommandIds,
    closeHub,
    setSearchQuery,
    setSelectedIndex,
    recordCommandExecution,
    getFilteredCommands,
  } = useGlobalCommandHubStore();

  const inputRef = useRef<HTMLInputElement>(null);
  const filteredCommands = getFilteredCommands();

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
    }
  }, [isOpen]);

  if (!isOpen) {
    return null;
  }

  const renderIcon = (name: string): React.ReactElement => {
    switch (name) {
      case 'Bot':
        return <Bot className="w-4 h-4 text-indigo-400" />;
      case 'BookOpen':
        return <BookOpen className="w-4 h-4 text-amber-400" />;
      case 'Laptop':
        return <Laptop className="w-4 h-4 text-sky-400" />;
      case 'Activity':
        return <Activity className="w-4 h-4 text-emerald-400" />;
      case 'Sparkles':
        return <Sparkles className="w-4 h-4 text-purple-400" />;
      case 'FileText':
        return <FileText className="w-4 h-4 text-indigo-400" />;
      case 'ShieldCheck':
        return <ShieldCheck className="w-4 h-4 text-emerald-400" />;
      case 'PlusCircle':
        return <PlusCircle className="w-4 h-4 text-sky-400" />;
      case 'Trash2':
        return <Trash2 className="w-4 h-4 text-rose-400" />;
      case 'Download':
        return <Download className="w-4 h-4 text-emerald-400" />;
      case 'GitBranch':
        return <GitBranch className="w-4 h-4 text-orange-400" />;
      case 'GitCommit':
        return <GitCommit className="w-4 h-4 text-sky-400" />;
      default:
        return <Command className="w-4 h-4 text-slate-400" />;
    }
  };

  const handleItemClick = (cmd: CommandItem): void => {
    recordCommandExecution(cmd.id);
    cmd.action();
    closeHub();
  };

  return (
    <dialog
      open
      aria-modal="true"
      aria-label="全局 ⌘K 全能命令中枢"
      className={`fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4 w-full h-full border-0 select-none ${className}`}
    >
      <section
        role="document"
        aria-label="命令中枢面板"
        className="relative flex flex-col w-full max-w-2xl max-h-[580px] rounded-2xl border border-slate-700/80 bg-slate-900/95 shadow-2xl overflow-hidden backdrop-blur-xl animate-in fade-in zoom-in-95 duration-150"
      >
        {/* 顶部搜索输入条 */}
        <div className="relative flex items-center px-4 py-3 border-b border-slate-800">
          <Search className="w-4 h-4 text-slate-400 mr-2.5 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
            }}
            placeholder="搜索导航、AI 派工、快捷操作或 Git 命令... (⌘K / Esc)"
            className="flex-1 bg-transparent text-sm text-white placeholder-slate-500 focus:outline-none"
            aria-label="命令搜索输入框"
          />
          <div className="flex items-center gap-2">
            <kbd className="hidden sm:inline-block rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-400 border border-slate-700">
              ESC
            </kbd>
            <button
              type="button"
              onClick={() => {
                closeHub();
              }}
              className="text-slate-400 hover:text-slate-200 transition-colors p-1"
              aria-label="关闭命令面板"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 四大类动作筛选栏 */}
        <CommandCategoryFilterBadge />

        {/* 命令列表滚动区 */}
        <ul
          aria-label="命令匹配列表"
          className="flex-1 overflow-y-auto p-2 space-y-1 list-none m-0"
        >
          {filteredCommands.length === 0 ? (
            <li className="py-12 text-center text-slate-500 text-xs">
              未找到匹配的命令或动作，换个关键词试试
            </li>
          ) : (
            filteredCommands.map((cmd, idx) => {
              const isSelected = selectedIndex === idx;
              const isRecent = recentCommandIds.includes(cmd.id);

              return (
                <li key={cmd.id}>
                  <button
                    type="button"
                    onClick={() => {
                      handleItemClick(cmd);
                    }}
                    onMouseEnter={() => {
                      setSelectedIndex(idx);
                    }}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs text-left transition-all ${
                      isSelected
                        ? 'bg-indigo-600/20 text-white border border-indigo-500/40'
                        : 'text-slate-300 hover:bg-slate-800/40 border border-transparent'
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="p-1.5 rounded-lg bg-slate-800/80 border border-slate-700/60 shrink-0">
                        {renderIcon(cmd.iconName)}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-100">{cmd.title}</span>
                          {isRecent && (
                            <span
                              className="inline-flex items-center gap-0.5 text-[10px] font-mono text-indigo-400"
                              title="最近执行"
                            >
                              <History className="w-2.5 h-2.5" />
                              <span>最近</span>
                            </span>
                          )}
                        </div>
                        {cmd.subtitle && (
                          <p className="text-[11px] text-slate-400 truncate mt-0.5">
                            {cmd.subtitle}
                          </p>
                        )}
                      </div>
                    </div>

                    {cmd.shortcut && (
                      <kbd className="shrink-0 font-mono text-[10px] text-slate-400 bg-slate-800/80 border border-slate-700 px-1.5 py-0.5 rounded">
                        {cmd.shortcut}
                      </kbd>
                    )}
                  </button>
                </li>
              );
            })
          )}
        </ul>

        {/* 底部按键流提示 */}
        <footer
          aria-label="键盘操作指引"
          className="flex items-center justify-between px-4 py-2 border-t border-slate-800/80 bg-slate-900/80 text-[11px] text-slate-400"
        >
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <kbd className="rounded bg-slate-800 px-1 font-mono text-[10px]">↑</kbd>
              <kbd className="rounded bg-slate-800 px-1 font-mono text-[10px]">↓</kbd>
              <span>导航切换</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded bg-slate-800 px-1 font-mono text-[10px]">↵</kbd>
              <span>立即执行</span>
            </span>
          </div>

          <div className="flex items-center gap-1 font-mono text-slate-500 text-[10px]">
            <span>⌘K Omni-Action Dispatcher</span>
          </div>
        </footer>
      </section>
    </dialog>
  );
};
