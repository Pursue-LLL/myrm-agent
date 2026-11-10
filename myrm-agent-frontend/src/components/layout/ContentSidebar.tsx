'use client';

/**
 * 内容侧边栏组件
 *
 * [INPUT]
 * - isCollapsed: 是否折叠
 * - onToggleCollapse: 折叠切换回调（移动端抽屉里同时是关闭抽屉的回调）
 * - navbarWidth: 导航栏宽度
 * - isMobile: 是否移动端
 * - width / isDragging / onResizeStart / onResizeDoubleClick: 桌面端宽度与拖拽
 *
 * [OUTPUT]
 * - ContentSidebar: 聊天标签页的侧边栏外壳
 *
 * [POS]
 * 折叠时只显示展开按钮；展开时桌面端贴着导航栏定位并带拖拽手柄，移动端铺满抽屉。
 * 侧边栏内容（聊天历史、工作区文件）见 ChatSidebarContent；移动端在用户选定会话或发起新会话后关闭抽屉。
 */

import { memo, useCallback } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import { ChatSidebarContent } from './ChatSidebarContent';
import { SidebarPanelIcon } from './SidebarPanelIcon';

interface ContentSidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  navbarWidth: number;
  isMobile?: boolean;
  width?: number;
  isDragging?: boolean;
  onResizeStart?: (e: React.MouseEvent) => void;
  onResizeDoubleClick?: () => void;
}

const ContentSidebar = memo<ContentSidebarProps>(
  ({
    isCollapsed,
    onToggleCollapse,
    navbarWidth,
    isMobile = false,
    width,
    isDragging = false,
    onResizeStart,
    onResizeDoubleClick,
  }) => {
    const t = useTranslations('layout');
    const router = useRouter();
    const pathname = usePathname();
    const initializeChat = useChatStore((state) => state.initializeChat);

    const handleNewChat = useCallback(() => {
      if (pathname !== '/') {
        router.push('/');
      }
      initializeChat(undefined);
    }, [initializeChat, router, pathname]);

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
          aria-label={t('showSidebar')}
        >
          <SidebarPanelIcon />
        </button>
      );
    }

    return (
      <aside
        data-theme-shell="sidebar"
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
        <ChatSidebarContent
          onNewChat={handleNewChat}
          onToggleCollapse={onToggleCollapse}
          isMobile={isMobile}
          onMobileItemClick={isMobile ? onToggleCollapse : undefined}
        />

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
