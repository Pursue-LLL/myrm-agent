'use client';

import { cn } from '@/lib/utils/classnameUtils';
import { SquarePen, Search, Menu, X } from 'lucide-react';
import { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter, usePathname } from 'next/navigation';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import ChatHistoryList from './ChatHistoryList';
import { STYLES } from './constants';
import { useSidebarState } from './useSidebarState';
import MobileDragButton from './MobileDragButton';
import UserMenu from './UserMenu';
import { PWAInstallButton } from '@/components/ui/pwa-install-button';
import { CatchupInbox } from '../chat-window/catchup/CatchupInbox';

interface SidebarProps {
  currentChatId?: string;
}

const Sidebar = memo<SidebarProps>(({ currentChatId }) => {
  const t = useTranslations();
  const router = useRouter();
  const pathname = usePathname();
  const { initializeChat } = useChatStore(useShallow((state) => ({ initializeChat: state.initializeChat })));

  const { isPinned, setIsPinned, setIsHovered, isMobileOpen, setIsMobileOpen, isMobile, isScrolling, isExpanded } =
    useSidebarState();

  const handleMobileToggle = useCallback(() => setIsMobileOpen(!isMobileOpen), [isMobileOpen, setIsMobileOpen]);

  const handleNewChat = useCallback(() => {
    setIsMobileOpen(false);

    // 如果不在首页，跳转到首页
    if (pathname !== '/') {
      router.push('/');
    }

    // 强制清空聊天状态，开启新对话
    initializeChat(undefined);
  }, [setIsMobileOpen, initializeChat, router, pathname]);

  const handleToggleSidebar = useCallback(() => {
    if (isMobile) {
      setIsMobileOpen(false);
    } else {
      setIsPinned(!isPinned);
    }
  }, [isMobile, setIsMobileOpen, setIsPinned, isPinned]);

  const getToggleTooltip = () => {
    if (isMobile) return t('common.close');
    return isExpanded ? (isPinned ? t('common.unpinSidebar') : t('common.pinSidebar')) : t('common.expandMenu');
  };

  // 通用按钮样式
  const getButtonClasses = (variant: 'hover' | 'hoverStrong' = 'hover') =>
    cn(STYLES.button.base, STYLES.button[variant], STYLES.button.touch);

  // 新建对话按钮渲染
  const renderNewChatButton = (isCollapsed = false) => {
    const buttonClasses = cn(
      isCollapsed
        ? 'p-2 lg:p-3 w-10 h-10 lg:w-12 lg:h-12 flex items-center justify-center rounded-xl'
        : 'flex items-center gap-3 lg:gap-4 w-full px-3 lg:px-4 py-3 lg:py-3.5 rounded-xl',
      STYLES.newChat.base,
      STYLES.newChat.hover,
      STYLES.button.touch,
    );

    const iconElement = (
      <div className="relative">
        <SquarePen size={18} className="text-primary" />
        <div className="absolute inset-0 blur-sm bg-primary/30 rounded-full scale-150" />
      </div>
    );

    return (
      <button
        onClick={handleNewChat}
        className={buttonClasses}
        title={isCollapsed ? t('chat.newChat') : undefined}
        aria-label={t('chat.newChat')}
      >
        {iconElement}
        {!isCollapsed && <span className="text-sm lg:text-base font-semibold text-primary">{t('chat.newChat')}</span>}
      </button>
    );
  };

  return (
    <>
      {/* 移动端拖拽按钮 */}
      {isMobile && !isMobileOpen && <MobileDragButton isScrolling={isScrolling} onToggle={handleMobileToggle} />}

      {/* 遮罩层 */}
      {isMobileOpen && <div className={STYLES.overlay} onClick={() => setIsMobileOpen(false)} aria-hidden="true" />}

      {/* 侧边栏 */}
      <aside
        className={cn(
          STYLES.sidebar.base,
          STYLES.sidebar.glass,
          isMobile ? STYLES.sidebar.mobile : isExpanded ? STYLES.sidebar.expanded : STYLES.sidebar.collapsed,
          isMobile ? (isMobileOpen ? 'translate-x-0' : '-translate-x-full') : 'translate-x-0',
        )}
        onMouseEnter={() => !isMobile && setIsHovered(true)}
        onMouseLeave={() => !isMobile && !isPinned && setIsHovered(false)}
      >
        <div className="flex grow flex-col overflow-hidden h-full">
          {/* Header */}
          <div className="px-3 py-4 lg:py-5 flex-shrink-0">
            {(isExpanded && !isMobile) || isMobileOpen ? (
              <div className="space-y-3 lg:space-y-4">
                {/* 顶部控制按钮 */}
                <div className="flex items-center justify-between">
                  <button
                    onClick={isMobile ? () => setIsMobileOpen(false) : handleToggleSidebar}
                    className={cn(getButtonClasses(), 'flex justify-center items-center')}
                    title={getToggleTooltip()}
                    aria-label={getToggleTooltip()}
                  >
                    {isMobile ? (
                      <X size={20} className={STYLES.text.secondary} />
                    ) : (
                      <Menu size={20} className={STYLES.text.secondary} />
                    )}
                  </button>
                  <div className="flex items-center gap-1">
                    <CatchupInbox />
                    <button className={getButtonClasses()} aria-label={t('common.search')}>
                      <Search size={20} className={STYLES.text.secondary} />
                    </button>
                  </div>
                </div>

                {/* 新建对话按钮 */}
                {renderNewChatButton(false)}
              </div>
            ) : (
              !isMobile && (
                <div className="flex flex-col items-center gap-4">
                  <CatchupInbox />
                  {renderNewChatButton(true)}
                </div>
              )
            )}
          </div>

          {/* Chat History */}
          <div className="flex-1 overflow-y-auto">
            <ChatHistoryList
              isExpanded={(isExpanded && !isMobile) || isMobileOpen}
              currentChatId={currentChatId}
              isMobile={isMobile}
            />
          </div>

          {/* Footer - 用户菜单 */}
          <div className="p-3 flex-shrink-0 flex flex-col gap-2">
            <PWAInstallButton
              className={cn('w-full justify-start', !isExpanded && !isMobileOpen && 'justify-center px-0')}
            />
            <UserMenu
              isExpanded={isExpanded}
              isMobile={isMobile}
              isMobileOpen={isMobileOpen}
              onMobileClose={() => setIsMobileOpen(false)}
            />
          </div>
        </div>
      </aside>
    </>
  );
});

Sidebar.displayName = 'Sidebar';

export default Sidebar;
