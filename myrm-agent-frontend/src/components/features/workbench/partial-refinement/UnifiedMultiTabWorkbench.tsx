import React, { useState } from 'react';
import {
  Layout,
  FileText,
  Globe,
  Terminal,
  Code,
  Plus,
  X,
  PanelRightClose,
  PanelRightOpen,
  Sparkles,
  Zap,
} from 'lucide-react';
import { useWorkbenchStore } from './useWorkbenchStore';
import { WorkbenchResourceType, WorkbenchTab } from './workbenchTypes';
import { WorkbenchResourceViewers } from './WorkbenchResourceViewers';
import { InPlacePartialRefinementPopover } from './InPlacePartialRefinementPopover';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';

export const UnifiedMultiTabWorkbench: React.FC = () => {
  const {
    tabs,
    activeTabId,
    isDocked,
    tokenStats,
    switchTab,
    closeTab,
    openTab,
    toggleDock,
  } = useWorkbenchStore();

  const [isExpanded, setIsExpanded] = useState(false);

  const activeTab = tabs.find((t) => t.id === activeTabId) || tabs[0];

  const getTabIcon = (type: WorkbenchResourceType) => {
    switch (type) {
      case 'document':
        return <FileText className="w-3.5 h-3.5 text-indigo-400" />;
      case 'browser':
        return <Globe className="w-3.5 h-3.5 text-emerald-400" />;
      case 'terminal':
        return <Terminal className="w-3.5 h-3.5 text-slate-400" />;
      case 'code':
      case 'table':
      default:
        return <Code className="w-3.5 h-3.5 text-amber-400" />;
    }
  };

  const handleAddNewScratchpad = () => {
    const newTab: WorkbenchTab = {
      id: `tab-scratch-${Date.now()}`,
      title: '新草稿笔记.md',
      type: 'document',
      content: '# 临时协同草稿\n输入内容或划选任意段落发起局部微调...',
    };
    openTab(newTab);
  };

  return (
    <aside
      aria-label="多标签全要素统一侧边工作台"
      className={`bg-slate-900 border-l border-slate-800 flex flex-col h-full text-slate-100 transition-all duration-300 relative ${
        isDocked ? (isExpanded ? 'w-[720px]' : 'w-[480px]') : 'w-14'
      }`}
      data-testid="unified-multitab-workbench"
    >
      {/* 折叠收起模式下的轻量快捷条 */}
      {!isDocked && (
        <div className="flex flex-col items-center py-4 space-y-4">
          <button
            type="button"
            onClick={toggleDock}
            aria-label="展开侧边工作台"
            className="p-2 text-indigo-400 hover:text-indigo-300 hover:bg-slate-800 rounded-lg transition-colors"
          >
            <PanelRightOpen className="w-5 h-5" />
          </button>
          <div className="w-6 h-px bg-slate-800" />
          <div className="writing-vertical text-xs text-slate-400 font-medium tracking-widest select-none">
            全要素工作台
          </div>
        </div>
      )}

      {/* 展开模式下的全功能工作台 */}
      {isDocked && (
        <>
          {/* 工作台顶栏：标题、算力节约汇总徽章与操作控制 */}
          <header className="px-4 py-2.5 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <div className="p-1.5 rounded-md bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
                <Layout className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-xs font-bold text-white tracking-tight">
                  统一全要素侧边工作台
                </h3>
                <div className="flex items-center space-x-1.5 text-[10px] text-emerald-400">
                  <Zap className="w-2.5 h-2.5" />
                  <span>
                    累计就地微调 {tokenStats.totalRefinements} 次 · 节省{' '}
                    {(tokenStats.totalTokensSaved / 1000).toFixed(1)}k Token
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center space-x-1">
              <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                aria-label={isExpanded ? '恢复标准宽度' : '加宽工作台视界'}
                className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors text-xs font-mono"
              >
                {isExpanded ? '标准宽' : '全要素宽'}
              </button>
              <button
                type="button"
                onClick={toggleDock}
                aria-label="收起侧边工作台"
                className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
              >
                <PanelRightClose className="w-4 h-4" />
              </button>
            </div>
          </header>

          {/* 多标签页导航条 (Tab Bar) */}
          <nav
            aria-label="工作台资源标签"
            className="flex items-center px-2 pt-1.5 bg-slate-950/40 border-b border-slate-800 overflow-x-auto space-x-1 scrollbar-none"
          >
            {tabs.map((tab) => {
              const isActive = tab.id === activeTab.id;
              return (
                <div
                  key={tab.id}
                  className={`group flex items-center space-x-1.5 px-3 py-1.5 rounded-t-lg text-xs font-medium cursor-pointer transition-colors border-t border-x ${
                    isActive
                      ? 'bg-slate-900 border-slate-700/80 text-white shadow-sm'
                      : 'bg-transparent border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/40'
                  }`}
                  onClick={() => switchTab(tab.id)}
                  role="tab"
                  aria-selected={isActive}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      switchTab(tab.id);
                    }
                  }}
                >
                  {getTabIcon(tab.type)}
                  <span className="truncate max-w-[120px]">{tab.title}</span>
                  {tab.isModified && (
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
                  )}
                  {tabs.length > 1 && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        closeTab(tab.id);
                      }}
                      aria-label={`关闭标签 ${tab.title}`}
                      className={`${REVEAL_ON_HOVER} p-0.5 hover:bg-slate-800 rounded transition-opacity text-slate-400 hover:text-slate-200`}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>
              );
            })}

            <button
              type="button"
              onClick={handleAddNewScratchpad}
              aria-label="新建协同草稿标签"
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors ml-1"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </nav>

          {/* 主视口渲染区：根据活跃标签类型动态分发 */}
          <main className="flex-1 overflow-y-auto bg-slate-900">
            {activeTab && <WorkbenchResourceViewers tab={activeTab} />}
          </main>

          {/* 划选就地局部重构编辑卡浮层 */}
          <InPlacePartialRefinementPopover />
        </>
      )}
    </aside>
  );
};
