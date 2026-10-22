import React, { useEffect, useRef, useState } from 'react';
import {
  Search,
  X,
  Plus,
  FolderOpen,
  ArrowUpDown,
  CornerDownLeft,
  Sparkles,
  Command,
} from 'lucide-react';
import {
  useWorkspaceQuickSwitcherStore,
  filterWorkspaces,
} from './useWorkspaceQuickSwitcherStore';
import { WorkspacePaletteItemRow } from './WorkspacePaletteItemRow';
import type { WorkspaceFilterTab } from './workspaceQuickSwitcherTypes';

export function WorkspaceQuickSwitcherModal() {
  const isOpen = useWorkspaceQuickSwitcherStore((s) => s.isOpen);
  const closeSwitcher = useWorkspaceQuickSwitcherStore((s) => s.closeSwitcher);
  const searchQuery = useWorkspaceQuickSwitcherStore((s) => s.searchQuery);
  const setSearchQuery = useWorkspaceQuickSwitcherStore((s) => s.setSearchQuery);
  const activeTab = useWorkspaceQuickSwitcherStore((s) => s.activeTab);
  const setActiveTab = useWorkspaceQuickSwitcherStore((s) => s.setActiveTab);
  const selectedIndex = useWorkspaceQuickSwitcherStore((s) => s.selectedIndex);
  const setSelectedIndex = useWorkspaceQuickSwitcherStore((s) => s.setSelectedIndex);
  const workspaces = useWorkspaceQuickSwitcherStore((s) => s.workspaces);
  const currentWorkspaceId = useWorkspaceQuickSwitcherStore((s) => s.currentWorkspaceId);
  const switchWorkspace = useWorkspaceQuickSwitcherStore((s) => s.switchWorkspace);
  const toggleFavorite = useWorkspaceQuickSwitcherStore((s) => s.toggleFavorite);
  const addWorkspace = useWorkspaceQuickSwitcherStore((s) => s.addWorkspace);

  const inputRef = useRef<HTMLInputElement>(null);
  const listContainerRef = useRef<HTMLUListElement>(null);
  const [isAddingNew, setIsAddingNew] = useState(false);
  const [newWsName, setNewWsName] = useState('');
  const [newWsPath, setNewWsPath] = useState('');

  const filteredItems = filterWorkspaces(workspaces, searchQuery, activeTab);

  // 打开时自动聚焦输入框
  useEffect(() => {
    if (isOpen) {
      setIsAddingNew(false);
      setNewWsName('');
      setNewWsPath('');
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
      return () => {
        clearTimeout(timer);
      };
    }
  }, [isOpen]);

  // 确保选区在有效范围内
  useEffect(() => {
    if (filteredItems.length > 0 && selectedIndex >= filteredItems.length) {
      setSelectedIndex(filteredItems.length - 1);
    }
  }, [filteredItems.length, selectedIndex, setSelectedIndex]);

  // 滚动跟随选中项
  useEffect(() => {
    if (!listContainerRef.current) {
      return;
    }
    const selectedElement = listContainerRef.current.querySelector(
      `[data-index="${selectedIndex}"]`
    ) as HTMLElement | null;
    if (selectedElement) {
      selectedElement.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [selectedIndex]);

  if (!isOpen) {
    return null;
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape') {
      e.preventDefault();
      closeSwitcher();
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (filteredItems.length === 0) {
        return;
      }
      setSelectedIndex((selectedIndex + 1) % filteredItems.length);
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (filteredItems.length === 0) {
        return;
      }
      setSelectedIndex((selectedIndex - 1 + filteredItems.length) % filteredItems.length);
      return;
    }

    if (e.key === 'Enter') {
      e.preventDefault();
      const currentItem = filteredItems[selectedIndex];
      if (currentItem) {
        const openInNewTab = e.metaKey || e.ctrlKey;
        switchWorkspace(currentItem.id, openInNewTab);
      }
      return;
    }

    if (e.key === 'Tab') {
      e.preventDefault();
      const tabs: WorkspaceFilterTab[] = ['all', 'recent', 'favorites'];
      const currentIndex = tabs.indexOf(activeTab);
      const nextTab = tabs[(currentIndex + 1) % tabs.length];
      if (nextTab) {
        setActiveTab(nextTab);
      }
    }
  }

  function handleCreateWorkspace(e: React.FormEvent) {
    e.preventDefault();
    if (!newWsName.trim() || !newWsPath.trim()) {
      return;
    }
    const created = addWorkspace({
      id: `ws-${Date.now()}`,
      name: newWsName.trim(),
      path: newWsPath.trim(),
      isDirty: false,
      dirtyCount: 0,
      rulesLoaded: ['AGENTS.md'],
    });
    switchWorkspace(created.id, false);
  }

  return (
    <dialog
      open
      aria-modal="true"
      aria-label="全局工作区快速切换器"
      className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 bg-background/80 backdrop-blur-sm border-0 w-full h-full m-0 max-w-none max-h-none"
    >
      <section
        role="document"
        aria-label="工作区漫游面板"
        className="w-full max-w-2xl bg-card border border-border shadow-2xl rounded-xl overflow-hidden flex flex-col max-h-[80vh] animate-in zoom-in-95 duration-150"
      >
        {/* 顶部搜索输入栏 */}
        <div className="flex items-center px-4 py-3 border-b border-border/80 gap-3">
          <Search className="h-5 w-5 text-muted-foreground shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
            }}
            onKeyDown={handleKeyDown}
            placeholder="搜索工作区、路径、分支或规约规则 (Cmd+O)..."
            className="flex-1 bg-transparent text-sm md:text-base outline-none placeholder:text-muted-foreground/60 text-foreground"
            aria-label="搜索工作区"
          />
          {searchQuery && (
            <button
              type="button"
              aria-label="清空搜索"
              onClick={() => {
                setSearchQuery('');
                inputRef.current?.focus();
              }}
              className="p-1 text-muted-foreground hover:text-foreground rounded"
            >
              <X className="h-4 w-4" />
            </button>
          )}
          <button
            type="button"
            aria-label="关闭调色板"
            onClick={closeSwitcher}
            className="p-1 text-muted-foreground hover:text-foreground rounded text-xs px-2 py-0.5 bg-muted/50 border border-border/50"
          >
            ESC
          </button>
        </div>

        {/* 分类过滤器 Tab 与快速新建按钮 */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-border/40 bg-muted/20 text-xs">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => {
                setActiveTab('all');
              }}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                activeTab === 'all'
                  ? 'bg-primary text-primary-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              全部 ({workspaces.length})
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab('recent');
              }}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                activeTab === 'recent'
                  ? 'bg-primary text-primary-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              最近打开
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab('favorites');
              }}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                activeTab === 'favorites'
                  ? 'bg-primary text-primary-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              星标收藏 ({workspaces.filter((w) => w.isFavorite).length})
            </button>
          </div>

          <button
            type="button"
            onClick={() => {
              setIsAddingNew(!isAddingNew);
            }}
            className="flex items-center gap-1 px-2 py-1 rounded text-primary hover:bg-primary/10 transition-colors font-medium"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>{isAddingNew ? '取消添加' : '添加本地工作区'}</span>
          </button>
        </div>

        {/* 展开的新建/导入工作区表单 */}
        {isAddingNew && (
          <form
            onSubmit={handleCreateWorkspace}
            className="p-4 border-b border-border/60 bg-muted/10 flex flex-col gap-3"
          >
            <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
              <FolderOpen className="h-4 w-4 text-primary" />
              <span>注册新本地项目空间</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              <div>
                <label
                  htmlFor="new-ws-name"
                  className="block text-[11px] font-medium text-muted-foreground mb-1"
                >
                  项目空间标识名称
                </label>
                <input
                  id="new-ws-name"
                  type="text"
                  value={newWsName}
                  onChange={(e) => {
                    setNewWsName(e.target.value);
                  }}
                  placeholder="例如: data-pipeline-engine"
                  className="w-full text-xs px-2.5 py-1.5 rounded-md border border-border bg-background text-foreground outline-none focus:border-primary"
                  required
                />
              </div>
              <div>
                <label
                  htmlFor="new-ws-path"
                  className="block text-[11px] font-medium text-muted-foreground mb-1"
                >
                  本地绝对路径
                </label>
                <input
                  id="new-ws-path"
                  type="text"
                  value={newWsPath}
                  onChange={(e) => {
                    setNewWsPath(e.target.value);
                  }}
                  placeholder="例如: /Users/username/projects/data-pipeline"
                  className="w-full text-xs px-2.5 py-1.5 rounded-md border border-border bg-background text-foreground outline-none focus:border-primary"
                  required
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-1">
              <button
                type="button"
                onClick={() => {
                  setIsAddingNew(false);
                }}
                className="px-3 py-1 rounded text-xs text-muted-foreground hover:bg-muted"
              >
                取消
              </button>
              <button
                type="submit"
                className="px-3 py-1 rounded text-xs bg-primary text-primary-foreground font-medium hover:bg-primary/90 flex items-center gap-1"
              >
                <Plus className="h-3 w-3" />
                <span>确认添加并切换</span>
              </button>
            </div>
          </form>
        )}

        {/* 结果列表区 */}
        <ul
          ref={listContainerRef}
          aria-label="工作区项目列表"
          className="flex-1 overflow-y-auto p-2 space-y-1 min-h-[160px] max-h-[380px] list-none m-0"
        >
          {filteredItems.length === 0 ? (
            <li className="flex flex-col items-center justify-center py-10 text-center px-4">
              <FolderOpen className="h-10 w-10 text-muted-foreground/40 mb-2" />
              <p className="text-sm font-medium text-muted-foreground">未找到匹配的工作区空间</p>
              <p className="text-xs text-muted-foreground/60 mt-1">
                尝试输入其他关键词，或点击右上角「添加本地工作区」直接引入已有仓库
              </p>
            </li>
          ) : (
            filteredItems.map((ws, index) => {
              return (
                <li key={ws.id} data-index={index}>
                  <WorkspacePaletteItemRow
                    workspace={ws}
                    isSelected={index === selectedIndex}
                    isCurrent={ws.id === currentWorkspaceId}
                    onSelect={() => {
                      switchWorkspace(ws.id, false);
                    }}
                    onToggleFavorite={(e) => {
                      e.stopPropagation();
                      toggleFavorite(ws.id);
                    }}
                    onOpenInNewTab={(e) => {
                      e.stopPropagation();
                      switchWorkspace(ws.id, true);
                    }}
                  />
                </li>
              );
            })
          )}
        </ul>

        {/* 底部键盘流操作指引底栏 */}
        <div className="flex flex-wrap items-center justify-between px-4 py-2 border-t border-border/60 bg-muted/30 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <ArrowUpDown className="h-3 w-3" />
              <span>上下键 选择</span>
            </span>
            <span className="flex items-center gap-1">
              <CornerDownLeft className="h-3 w-3" />
              <span>回车 快速切换</span>
            </span>
            <span className="flex items-center gap-1">
              <Command className="h-3 w-3" />
              <span>⌘+↵ 新窗口漫游</span>
            </span>
            <span className="hidden sm:flex items-center gap-1">
              <span className="px-1 py-0.5 rounded bg-muted border border-border/50 text-[10px]">
                Tab
              </span>
              <span>切换类别</span>
            </span>
          </div>

          <div className="hidden md:flex items-center gap-1 text-primary">
            <Sparkles className="h-3 w-3" />
            <span>无损上下文漫游就绪</span>
          </div>
        </div>
      </section>
    </dialog>
  );
}
