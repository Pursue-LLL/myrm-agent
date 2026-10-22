import React, { useState } from 'react';
import {
  X,
  Plus,
  Trash2,
  BookOpen,
  GitBranch,
  Boxes,
  Code,
  Wrench,
  Search,
} from 'lucide-react';
import { useSpeechBiasStore } from './useSpeechBiasStore';
import { DevTermCategory, DevTermItem } from './speechBiasTypes';

export interface DevLexiconBiasDrawerProps {
  onClose?: () => void;
  className?: string;
}

export const DevLexiconBiasDrawer: React.FC<DevLexiconBiasDrawerProps> = ({
  onClose,
  className = '',
}) => {
  const {
    isDrawerOpen,
    lexicon,
    activeBranchName,
    recentAstSymbols,
    installedSkills,
    setDrawerOpen,
    addCustomTerm,
    removeTerm,
  } = useSpeechBiasStore();

  const [newTerm, setNewTerm] = useState('');
  const [newAliases, setNewAliases] = useState('');
  const [newCategory, setNewCategory] = useState<DevTermCategory>('custom');
  const [searchFilter, setSearchFilter] = useState('');

  if (!isDrawerOpen) {
    return null;
  }

  const handleClose = () => {
    setDrawerOpen(false);
    if (onClose) {
      onClose();
    }
  };

  const handleAddTerm = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTerm.trim()) {
      return;
    }
    const aliasArr = newAliases
      .split(/[,，/]/)
      .map((a) => a.trim())
      .filter((a) => a.length > 0);

    addCustomTerm(newTerm.trim(), aliasArr, newCategory);
    setNewTerm('');
    setNewAliases('');
  };

  const renderCategoryIcon = (category: DevTermCategory) => {
    if (category === 'git_branch') {
      return <GitBranch className="w-3.5 h-3.5 text-orange-400" />;
    }
    if (category === 'cli_tool' || category === 'skill') {
      return <Wrench className="w-3.5 h-3.5 text-blue-400" />;
    }
    if (category === 'ast_symbol') {
      return <Code className="w-3.5 h-3.5 text-emerald-400" />;
    }
    return <Boxes className="w-3.5 h-3.5 text-purple-400" />;
  };

  const filteredLexicon = lexicon.filter((item: DevTermItem) => {
    if (!searchFilter.trim()) {
      return true;
    }
    const q = searchFilter.toLowerCase();
    return (
      item.term.toLowerCase().includes(q) ||
      item.aliases.some((a) => a.toLowerCase().includes(q)) ||
      item.category.includes(q)
    );
  });

  return (
    <div
      data-testid="dev-lexicon-bias-drawer"
      className={`fixed inset-y-0 right-0 z-50 w-96 bg-zinc-900 border-l border-zinc-800 shadow-2xl flex flex-col transition-all duration-300 ${className}`}
    >
      {/* 头部标题与关闭 */}
      <div className="flex items-center justify-between p-4 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-indigo-400" />
          <h3 className="text-sm font-semibold text-zinc-100">工程术语与声学偏置词典</h3>
        </div>
        <button
          type="button"
          onClick={handleClose}
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* 项目上下文感知状态条 */}
      <div className="px-4 py-3 bg-zinc-950/60 border-b border-zinc-850 text-xs space-y-1.5">
        <div className="text-zinc-400 font-medium">当前上下文感知注入:</div>
        <div className="flex flex-wrap gap-2 text-zinc-300">
          {activeBranchName && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700">
              <GitBranch className="w-3 h-3 text-orange-400" />
              分支: {activeBranchName}
            </span>
          )}
          {recentAstSymbols.length > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700">
              <Code className="w-3 h-3 text-emerald-400" />
              AST 符号: {recentAstSymbols.length} 个
            </span>
          )}
          {installedSkills.length > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700">
              <Wrench className="w-3 h-3 text-blue-400" />
              激活技能: {installedSkills.length} 个
            </span>
          )}
        </div>
      </div>

      {/* 检索过滤输入框 */}
      <div className="p-3 border-b border-zinc-800">
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-zinc-500" />
          <input
            type="text"
            value={searchFilter}
            onChange={(e) => {
              setSearchFilter(e.target.value);
            }}
            placeholder="搜索术语、易误听别名或分类..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-zinc-950 text-zinc-200 rounded-lg border border-zinc-800 focus:outline-none focus:border-indigo-500"
          />
        </div>
      </div>

      {/* 词典列表 */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {filteredLexicon.length === 0 ? (
          <div className="text-center py-8 text-xs text-zinc-500">
            暂无匹配的工程术语
          </div>
        ) : (
          filteredLexicon.map((item: DevTermItem) => (
            <div
              key={item.id}
              className="p-2.5 rounded-lg bg-zinc-950/40 border border-zinc-800/80 hover:border-zinc-700 transition-colors"
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5 font-mono text-xs font-semibold text-zinc-200">
                  {renderCategoryIcon(item.category)}
                  <span>{item.term}</span>
                  {item.source && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-zinc-800 text-zinc-400 font-sans">
                      {item.source}
                    </span>
                  )}
                </div>
                {item.category === 'custom' && (
                  <button
                    type="button"
                    onClick={() => {
                      removeTerm(item.id);
                    }}
                    title="删除自定义术语"
                    className="text-zinc-500 hover:text-red-400 p-1 rounded"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                )}
              </div>

              {item.aliases.length > 0 && (
                <div className="text-[11px] text-zinc-400 flex flex-wrap gap-1 mt-1">
                  <span className="text-zinc-500">误听别名:</span>
                  {item.aliases.map((alias, idx) => (
                    <span
                      key={`${item.id}-alias-${idx}`}
                      className="px-1.5 py-0.5 rounded bg-zinc-800/80 text-zinc-300 font-mono text-[10px]"
                    >
                      {alias}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* 底部新增自定义术语表单 */}
      <form onSubmit={handleAddTerm} className="p-3 border-t border-zinc-800 bg-zinc-950/80 space-y-2">
        <div className="text-xs font-semibold text-zinc-300 flex items-center gap-1">
          <Plus className="w-3.5 h-3.5 text-indigo-400" />
          快速添加自定义偏置术语
        </div>
        <div className="grid grid-cols-2 gap-2">
          <input
            type="text"
            value={newTerm}
            onChange={(e) => {
              setNewTerm(e.target.value);
            }}
            placeholder="标准技术术语 (如 pnpm)"
            className="w-full px-2.5 py-1.5 text-xs bg-zinc-900 text-zinc-200 rounded border border-zinc-700 focus:outline-none focus:border-indigo-500 font-mono"
          />
          <select
            value={newCategory}
            onChange={(e) => {
              setNewCategory(e.target.value as DevTermCategory);
            }}
            className="w-full px-2 py-1.5 text-xs bg-zinc-900 text-zinc-300 rounded border border-zinc-700 focus:outline-none focus:border-indigo-500"
          >
            <option value="custom">通用自定义</option>
            <option value="cli_tool">命令行工具</option>
            <option value="framework">框架 / 运行时</option>
            <option value="ast_symbol">代码符号</option>
          </select>
        </div>
        <input
          type="text"
          value={newAliases}
          onChange={(e) => {
            setNewAliases(e.target.value);
          }}
          placeholder="常见语音误听词，逗号分隔 (如 屁恩屁恩, pen pm)"
          className="w-full px-2.5 py-1.5 text-xs bg-zinc-900 text-zinc-200 rounded border border-zinc-700 focus:outline-none focus:border-indigo-500 font-mono"
        />
        <button
          type="submit"
          disabled={!newTerm.trim()}
          className="w-full py-1.5 text-xs font-medium bg-indigo-600 text-white rounded hover:bg-indigo-500 disabled:opacity-40 transition-colors flex items-center justify-center gap-1"
        >
          <Plus className="w-3.5 h-3.5" />
          添加到本地偏置词典
        </button>
      </form>
    </div>
  );
};
