/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Vector Icons)
 * - @/components/features/chat-window/three-pane-studio/threePaneStudioTypes
 * - @/components/features/chat-window/three-pane-studio/useThreePaneStudioStore
 * - @/components/features/chat-window/three-pane-studio/ContextTreePane
 * - @/components/features/chat-window/three-pane-studio/MiddleContentPane
 *
 * [OUTPUT]
 * - ThreePaneContextStudio (POS: Main modern three-pane workbench studio component)
 *
 * [POS]
 * Primary studio shell for Item 198 (P0): ThreePaneContextStudioAndRealtimeToolHighlightSuite.
 * Features left context tree, middle file/memory content preview, right dual-mode chat/terminal,
 * collapsible panels, and automatic real-time tool highlight event bridging.
 */

import React, { useEffect } from 'react';
import {
  MessageSquare,
  Terminal,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
} from 'lucide-react';
import type {
  ContextTreeNode,
  RightPaneMode,
  ToolHighlightEvent,
} from './threePaneStudioTypes';
import { useThreePaneStudioStore } from './useThreePaneStudioStore';
import { ContextTreePane } from './ContextTreePane';
import { MiddleContentPane } from './MiddleContentPane';

export interface ThreePaneContextStudioProps {
  readonly chatId?: string;
  readonly renderAgentChat?: () => React.ReactNode;
  readonly renderTerminal?: () => React.ReactNode;
  readonly onInsertReference?: (node: ContextTreeNode) => void;
  readonly className?: string;
}

export const ThreePaneContextStudio: React.FC<ThreePaneContextStudioProps> = ({
  renderAgentChat,
  renderTerminal,
  onInsertReference,
  className = '',
}) => {
  const {
    layout,
    rightPaneMode,
    setRightPaneMode,
    toggleLeftCollapse,
    toggleRightCollapse,
    triggerToolHighlight,
  } = useThreePaneStudioStore();

  useEffect(() => {
    const handleStudioEvent = (event: Event) => {
      const customEvent = event as CustomEvent<ToolHighlightEvent>;
      if (customEvent.detail) {
        triggerToolHighlight(customEvent.detail);
      }
    };

    if (typeof window !== 'undefined') {
      window.addEventListener('myrm:studio-tool-highlight', handleStudioEvent);
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('myrm:studio-tool-highlight', handleStudioEvent);
      }
    };
  }, [triggerToolHighlight]);

  const handleModeSwitch = (mode: RightPaneMode) => {
    setRightPaneMode(mode);
  };

  return (
    <div
      data-testid="three-pane-context-studio"
      className={`flex h-full w-full overflow-hidden bg-slate-950 text-slate-100 ${className}`}
    >
      {/* 左栏：统一上下文树 */}
      {!layout.isLeftCollapsed && (
        <div
          data-testid="left-pane-container"
          style={{ width: `${layout.leftWidth}px` }}
          className="shrink-0 h-full flex flex-col"
        >
          <ContextTreePane onInsertReference={onInsertReference} />
        </div>
      )}

      {/* 中栏：文件与记忆内容查阅 */}
      <div className="flex-1 min-w-[280px] h-full flex flex-col overflow-hidden">
        {/* 顶部工具栏：折叠控制器与辅助状态 */}
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-800 bg-slate-900/90 text-xs shrink-0">
          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="btn-toggle-left-pane"
              aria-label={layout.isLeftCollapsed ? '展开左侧上下文树' : '折叠左侧上下文树'}
              title={layout.isLeftCollapsed ? '展开上下文树' : '折叠上下文树'}
              onClick={toggleLeftCollapse}
              className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
            >
              {layout.isLeftCollapsed ? (
                <PanelLeftOpen className="w-4 h-4" />
              ) : (
                <PanelLeftClose className="w-4 h-4" />
              )}
            </button>
            <span className="text-slate-400 font-mono text-[11px]">
              Studio 工作台
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="btn-toggle-right-pane"
              aria-label={layout.isRightCollapsed ? '展开右侧会话区' : '折叠右侧会话区'}
              title={layout.isRightCollapsed ? '展开会话区' : '折叠会话区'}
              onClick={toggleRightCollapse}
              className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
            >
              {layout.isRightCollapsed ? (
                <PanelRightOpen className="w-4 h-4" />
              ) : (
                <PanelRightClose className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>

        <div className="flex-1 min-h-0">
          <MiddleContentPane />
        </div>
      </div>

      {/* 右栏：双模式会话区 (Agent 对话 vs 终端) */}
      {!layout.isRightCollapsed && (
        <aside
          data-testid="right-pane-container"
          style={{ width: `${layout.rightWidth}px` }}
          className="shrink-0 h-full flex flex-col bg-slate-900 border-l border-slate-800 overflow-hidden"
        >
          {/* 模式切换药丸组件 */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800 bg-slate-950/40 shrink-0">
            <div className="flex items-center p-0.5 rounded-lg bg-slate-800 border border-slate-700/60">
              <button
                type="button"
                data-testid="btn-mode-chat"
                aria-pressed={rightPaneMode === 'agent_chat'}
                onClick={() => handleModeSwitch('agent_chat')}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                  rightPaneMode === 'agent_chat'
                    ? 'bg-cyan-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <MessageSquare className="w-3.5 h-3.5" />
                <span>智能体对话</span>
              </button>

              <button
                type="button"
                data-testid="btn-mode-terminal"
                aria-pressed={rightPaneMode === 'terminal'}
                onClick={() => handleModeSwitch('terminal')}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                  rightPaneMode === 'terminal'
                    ? 'bg-cyan-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Terminal className="w-3.5 h-3.5" />
                <span>系统终端</span>
              </button>
            </div>
          </div>

          {/* 会话内容或终端展示 */}
          <div className="flex-1 min-h-0 overflow-hidden">
            {rightPaneMode === 'agent_chat' ? (
              <div
                data-testid="agent-chat-slot"
                className="h-full w-full overflow-y-auto"
              >
                {renderAgentChat ? (
                  renderAgentChat()
                ) : (
                  <div className="flex flex-col items-center justify-center h-full p-6 text-center text-slate-500">
                    <MessageSquare className="w-8 h-8 mb-2 opacity-40 text-cyan-400" />
                    <p className="text-xs">Agent 交互对话区就绪</p>
                  </div>
                )}
              </div>
            ) : (
              <div
                data-testid="terminal-slot"
                className="h-full w-full overflow-hidden bg-black font-mono text-xs text-emerald-400 p-3"
              >
                {renderTerminal ? (
                  renderTerminal()
                ) : (
                  <div className="flex flex-col gap-1">
                    <span className="text-slate-500"># Myrm Studio Interactive Terminal Bridge</span>
                    <span className="text-emerald-400">$ ready</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </aside>
      )}
    </div>
  );
};
