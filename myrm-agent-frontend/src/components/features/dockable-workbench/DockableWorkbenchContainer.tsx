import React from 'react';
import {
  PanelRight,
  PanelBottom,
  X,
  ChevronDown,
  ChevronUp,
  GitCommit,
  FileText,
  Monitor,
  Terminal,
  Layers,
} from 'lucide-react';
import { useDockableWorkbenchStore } from './useDockableWorkbenchStore';
import { DockableChangesViewer } from './DockableChangesViewer';
import type { DockablePanelId, DockPosition } from './dockableWorkbenchTypes';

export interface DockableWorkbenchContainerProps {
  readonly className?: string;
  readonly children?: React.ReactNode;
}

export const DockableWorkbenchContainer: React.FC<DockableWorkbenchContainerProps> = ({
  className = '',
  children,
}) => {
  const {
    activePanelId,
    dockPosition,
    isCollapsed,
    openPanel,
    closePanel,
    setDockPosition,
    toggleCollapse,
    bootstrapData,
  } = useDockableWorkbenchStore();

  const isPanelOpen = dockPosition !== 'closed' && activePanelId !== null;

  const handlePanelTabClick = (panelId: DockablePanelId) => {
    if (activePanelId === panelId && !isCollapsed) {
      toggleCollapse();
    } else {
      openPanel(panelId);
    }
  };

  const handlePositionToggle = () => {
    const nextPos: DockPosition = dockPosition === 'right' ? 'bottom' : 'right';
    setDockPosition(nextPos);
  };

  return (
    <div
      data-testid="dockable-workbench-container"
      className={`relative flex w-full h-full overflow-hidden ${
        dockPosition === 'bottom' ? 'flex-col' : 'flex-row'
      } ${className}`}
    >
      {/* 中央主会话区域 */}
      <div className="flex-1 flex flex-col min-w-0 overflow-auto bg-slate-950">
        {bootstrapData && (
          <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800/80 bg-slate-900/40 text-xs text-slate-400">
            <div className="flex items-center gap-2">
              <span className="flex h-2 w-2 rounded-full bg-emerald-400" />
              <span className="font-medium text-slate-200">
                {bootstrapData.sessionTitle}
              </span>
              <span className="text-[10px] text-slate-500">
                ({bootstrapData.activeAgentName})
              </span>
            </div>
            <div className="flex items-center gap-2 text-[10px] font-mono">
              <span>基线代次: E{bootstrapData.eventBaselineEpoch}</span>
              <span>消息数: {bootstrapData.initialMessagesCount}</span>
            </div>
          </div>
        )}

        <div className="flex-1 p-4">{children}</div>
      </div>

      {/* 停靠上下文观察抽屉 */}
      {isPanelOpen && (
        <aside
          data-testid="dockable-workbench-panel"
          className={`flex flex-col border-slate-800 bg-slate-900/95 backdrop-blur-md transition-all duration-200 ${
            dockPosition === 'bottom'
              ? `w-full border-t ${isCollapsed ? 'h-10' : 'h-72'}`
              : `h-full border-l ${isCollapsed ? 'w-10' : 'w-80 md:w-96'}`
          }`}
        >
          {/* 面板顶栏控制区 */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800 text-xs">
            <div className="flex items-center gap-1.5 overflow-x-auto">
              <button
                type="button"
                onClick={() => {
                  handlePanelTabClick('changes');
                }}
                className={`flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${
                  activePanelId === 'changes'
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <GitCommit className="h-3 w-3" />
                <span className={isCollapsed && dockPosition === 'right' ? 'hidden' : 'inline'}>
                  Changes
                </span>
              </button>

              <button
                type="button"
                onClick={() => {
                  handlePanelTabClick('file_preview');
                }}
                className={`flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${
                  activePanelId === 'file_preview'
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <FileText className="h-3 w-3" />
                <span className={isCollapsed && dockPosition === 'right' ? 'hidden' : 'inline'}>
                  文件速览
                </span>
              </button>

              <button
                type="button"
                onClick={() => {
                  handlePanelTabClick('live_browser');
                }}
                className={`flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${
                  activePanelId === 'live_browser'
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Monitor className="h-3 w-3" />
                <span className={isCollapsed && dockPosition === 'right' ? 'hidden' : 'inline'}>
                  浏览器
                </span>
              </button>

              <button
                type="button"
                onClick={() => {
                  handlePanelTabClick('terminal');
                }}
                className={`flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${
                  activePanelId === 'terminal'
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Terminal className="h-3 w-3" />
                <span className={isCollapsed && dockPosition === 'right' ? 'hidden' : 'inline'}>
                  终端
                </span>
              </button>
            </div>

            <div className="flex items-center gap-1 text-slate-400">
              <button
                type="button"
                onClick={handlePositionToggle}
                aria-label="切换停靠位置"
                className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200"
              >
                {dockPosition === 'right' ? (
                  <PanelBottom className="h-3.5 w-3.5" />
                ) : (
                  <PanelRight className="h-3.5 w-3.5" />
                )}
              </button>

              <button
                type="button"
                onClick={toggleCollapse}
                aria-label="折叠或展开面板"
                className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200"
              >
                {isCollapsed ? (
                  <ChevronDown className="h-3.5 w-3.5" />
                ) : (
                  <ChevronUp className="h-3.5 w-3.5" />
                )}
              </button>

              <button
                type="button"
                onClick={closePanel}
                aria-label="关闭面板"
                className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {/* 面板内容渲染区 */}
          {!isCollapsed && (
            <div className="flex-1 p-2.5 overflow-auto">
              {activePanelId === 'changes' && <DockableChangesViewer />}
              {activePanelId === 'file_preview' && (
                <div className="p-4 text-xs text-slate-400 font-mono">
                  [只读文件速览] 仅供实时审查 Agent 修改后的工程代码，禁止手动新建/删除
                </div>
              )}
              {activePanelId === 'live_browser' && (
                <div className="p-4 text-xs text-slate-400 font-mono">
                  [画中画自动化视窗] 正在监听实时 Chromium 会话视口
                </div>
              )}
              {activePanelId === 'terminal' && (
                <div className="p-4 text-xs text-slate-400 font-mono">
                  [全屏 Web 终端] 正在监听沙箱命令执行流
                </div>
              )}
            </div>
          )}
        </aside>
      )}
    </div>
  );
};
