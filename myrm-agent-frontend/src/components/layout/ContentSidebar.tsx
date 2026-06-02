'use client';

/**
 * 内容侧边栏组件
 *
 * [INPUT]
 * - activeTab: 当前激活的导航标签
 * - isCollapsed: 是否折叠
 * - onToggleCollapse: 折叠切换回调
 * - navbarWidth: 导航栏宽度
 * - selectedAgentId: 选中的智能体 ID
 * - onSelectAgent: 智能体选择回调
 * - isMobile: 是否移动端
 *
 * [OUTPUT]
 * - ContentSidebar: 内容侧边栏组件
 *
 * [POS]
 * 根据 activeTab 显示不同的侧边栏内容：
 * - chat: 聊天历史 + CLI 工作区（ChatSidebarContent）
 * - agent: 智能体列表（AgentSidebarContent）
 */

import { memo, useCallback } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import type { NavTab } from './NavBar';
import { ChatSidebarContent } from './ChatSidebarContent';
import { AgentSidebarContent } from './AgentSidebarContent';

interface ContentSidebarProps {
  activeTab: NavTab;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  navbarWidth: number;
  selectedAgentId?: string;
  onSelectAgent?: (id: string | undefined) => void;
  isMobile?: boolean;
  width?: number;
  isDragging?: boolean;
  onResizeStart?: (e: React.MouseEvent) => void;
  onResizeDoubleClick?: () => void;
}

const ContentSidebar = memo<ContentSidebarProps>(
  ({
    activeTab,
    isCollapsed,
    onToggleCollapse,
    navbarWidth,
    selectedAgentId,
    onSelectAgent,
    isMobile = false,
    width,
    isDragging = false,
    onResizeStart,
    onResizeDoubleClick,
  }) => {
    const router = useRouter();
    const pathname = usePathname();
    const { initializeChat } = useChatStore(useShallow((state) => ({ initializeChat: state.initializeChat })));

    const handleNewChat = useCallback(() => {
      if (pathname !== '/') {
        router.push('/');
      }
      initializeChat(undefined);
    }, [initializeChat, router, pathname]);

    // 折叠时显示展开按钮
    const SidebarIcon = () => (
      <svg width="20" height="20" fill="none" viewBox="0 0 20 20" className="text-muted-foreground">
        <path
          fillRule="evenodd"
          clipRule="evenodd"
          d="M2.167 6.667A2.833 2.833 0 0 1 5 3.833h2.708v12.334H5a2.833 2.833 0 0 1-2.833-2.834V6.667ZM9.042 17.5H5a4.167 4.167 0 0 1-4.167-4.167V6.667A4.167 4.167 0 0 1 5 2.5h10a4.167 4.167 0 0 1 4.167 4.167v6.666A4.167 4.167 0 0 1 15 17.5H9.042Zm0-13.667H15a2.833 2.833 0 0 1 2.833 2.834v6.666A2.833 2.833 0 0 1 15 16.167H9.042V3.833ZM3.583 6.5c0-.368.336-.667.75-.667H5.75c.414 0 .75.299.75.667 0 .368-.336.667-.75.667H4.333c-.414 0-.75-.299-.75-.667Zm.75 1.833c-.414 0-.75.299-.75.667 0 .368.336.667.75.667H5.75c.414 0 .75-.299.75-.667 0-.368-.336-.667-.75-.667H4.333Z"
          fill="currentColor"
        />
      </svg>
    );

    if (isCollapsed) {
      return (
        <button
          onClick={onToggleCollapse}
          className={cn(
            'fixed top-4 z-40 w-9 h-9 rounded-lg flex items-center justify-center',
            'bg-background/80 backdrop-blur-sm border border-border/50',
            'hover:bg-muted transition-colors',
          )}
          style={{ left: `${navbarWidth + 8}px` }}
          aria-label="Expand sidebar"
        >
          <SidebarIcon />
        </button>
      );
    }

    return (
      <aside
        className={cn(
          'flex flex-col relative',
          isMobile
            ? 'flex-1 min-w-0 h-full bg-background'
            : 'fixed top-0 bottom-0 border-r border-border bg-background z-30',
          isDragging && 'select-none',
        )}
        style={{
          left: isMobile ? undefined : `${navbarWidth}px`,
          width: isMobile ? undefined : width ? `${width}px` : '280px',
          transition: isDragging ? 'none' : undefined,
        }}
      >
        {activeTab === 'chat' ? (
          <ChatSidebarContent onNewChat={handleNewChat} onToggleCollapse={onToggleCollapse} isMobile={isMobile} />
        ) : activeTab === 'agent' ? (
          <AgentSidebarContent
            selectedId={selectedAgentId}
            onSelect={onSelectAgent}
            onToggleCollapse={onToggleCollapse}
          />
        ) : null}

        {/* 拖拽手柄 - 仅桌面端 */}
        {!isMobile && onResizeStart && (
          <div
            className={cn(
              'absolute top-0 bottom-0 right-0 w-[6px] cursor-col-resize z-50',
              'group hover:bg-primary/20 active:bg-primary/30',
              isDragging && 'bg-primary/30',
            )}
            onMouseDown={onResizeStart}
            onDoubleClick={onResizeDoubleClick}
          >
            <div
              className={cn(
                'absolute top-0 bottom-0 right-0 w-[2px]',
                'opacity-0 group-hover:opacity-100 bg-primary/50 transition-opacity',
                isDragging && 'opacity-100',
              )}
            />
          </div>
        )}
      </aside>
    );
  },
);

ContentSidebar.displayName = 'ContentSidebar';

export default ContentSidebar;
