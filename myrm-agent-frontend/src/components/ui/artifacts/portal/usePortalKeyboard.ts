import { useEffect } from 'react';
import { ArtifactDisplayMode } from '@/store/useArtifactPortalStore';

interface UsePortalKeyboardProps {
  isOpen: boolean;
  isFullscreen: boolean;
  displayMode: ArtifactDisplayMode;
  content: string;
  openTabsLength: number;
  activeTabIndex: number;
  onClose: () => void;
  onSetFullscreen: (fullscreen: boolean) => void;
  onSetDisplayMode: (mode: ArtifactDisplayMode) => void;
  onDownload: () => void;
  onCloseTab: (index: number) => void;
  onSwitchTab: (index: number) => void;
  onCopy?: () => void;
  onCloseAllTabs?: () => void;
}

/** Portal 键盘快捷键 Hook */
export function usePortalKeyboard({
  isOpen,
  isFullscreen,
  displayMode,
  content,
  openTabsLength,
  activeTabIndex,
  onClose,
  onSetFullscreen,
  onSetDisplayMode,
  onDownload,
  onCloseTab,
  onSwitchTab,
  onCopy,
  onCloseAllTabs,
}: UsePortalKeyboardProps) {
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // ESC: 关闭全屏或关闭面板
      if (e.key === 'Escape') {
        if (isFullscreen) {
          onSetFullscreen(false);
        } else {
          onClose();
        }
        return;
      }

      // 以下快捷键需要 Cmd/Ctrl 修饰键
      const isMod = e.metaKey || e.ctrlKey;
      if (!isMod) return;

      switch (e.key.toLowerCase()) {
        // Cmd/Ctrl + K: 快速切换显示模式（预览 <-> 代码）
        case 'k':
          e.preventDefault();
          onSetDisplayMode(
            displayMode === ArtifactDisplayMode.Preview ? ArtifactDisplayMode.Code : ArtifactDisplayMode.Preview,
          );
          break;
        // Cmd/Ctrl + P: 切换到预览模式
        case 'p':
          e.preventDefault();
          onSetDisplayMode(ArtifactDisplayMode.Preview);
          break;
        // Cmd/Ctrl + U: 切换到代码模式
        case 'u':
          e.preventDefault();
          onSetDisplayMode(ArtifactDisplayMode.Code);
          break;
        // Cmd/Ctrl + Shift + F: 切换全屏
        case 'f':
          if (e.shiftKey) {
            e.preventDefault();
            onSetFullscreen(!isFullscreen);
          }
          break;
        // Cmd/Ctrl + S: 下载
        case 's':
          e.preventDefault();
          onDownload();
          break;
        // Cmd/Ctrl + Shift + C: 复制内容到剪贴板
        case 'c':
          if (e.shiftKey && onCopy) {
            e.preventDefault();
            onCopy();
          }
          // 否则让默认复制行为生效
          break;
        // Cmd/Ctrl + W: 关闭当前标签页
        case 'w':
          if (e.shiftKey) {
            // Cmd/Ctrl + Shift + W: 关闭所有标签页
            e.preventDefault();
            if (onCloseAllTabs) {
              onCloseAllTabs();
            }
          } else {
            // Cmd/Ctrl + W: 关闭当前标签页
            e.preventDefault();
            if (openTabsLength > 0) {
              onCloseTab(activeTabIndex);
            }
          }
          break;
        // Cmd/Ctrl + D: 快速下载
        case 'd':
          e.preventDefault();
          onDownload();
          break;
        // Cmd/Ctrl + [: 切换到上一个标签页
        case '[':
          e.preventDefault();
          if (activeTabIndex > 0) {
            onSwitchTab(activeTabIndex - 1);
          }
          break;
        // Cmd/Ctrl + ]: 切换到下一个标签页
        case ']':
          e.preventDefault();
          if (activeTabIndex < openTabsLength - 1) {
            onSwitchTab(activeTabIndex + 1);
          }
          break;
      }

      // Cmd/Ctrl + 数字键: 切换到指定标签页
      const num = parseInt(e.key);
      if (!isNaN(num) && num >= 1 && num <= 9) {
        e.preventDefault();
        const targetIndex = num - 1;
        if (targetIndex < openTabsLength) {
          onSwitchTab(targetIndex);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    isOpen,
    isFullscreen,
    displayMode,
    content,
    openTabsLength,
    activeTabIndex,
    onClose,
    onSetFullscreen,
    onSetDisplayMode,
    onDownload,
    onCloseTab,
    onSwitchTab,
    onCopy,
    onCloseAllTabs,
  ]);
}

/**
 * 键盘快捷键说明
 *
 * 通用：
 * - ESC: 关闭全屏/关闭面板
 *
 * 显示模式：
 * - Cmd/Ctrl + K: 快速切换（预览 <-> 代码）
 * - Cmd/Ctrl + P: 切换到预览模式
 * - Cmd/Ctrl + U: 切换到代码模式
 *
 * 窗口管理：
 * - Cmd/Ctrl + Shift + F: 切换全屏
 *
 * 文件操作：
 * - Cmd/Ctrl + S: 下载文件
 * - Cmd/Ctrl + D: 快速下载
 * - Cmd/Ctrl + Shift + C: 复制内容
 *
 * 标签页管理：
 * - Cmd/Ctrl + W: 关闭当前标签页
 * - Cmd/Ctrl + Shift + W: 关闭所有标签页
 * - Cmd/Ctrl + [: 切换到上一个标签页
 * - Cmd/Ctrl + ]: 切换到下一个标签页
 * - Cmd/Ctrl + 1-9: 切换到指定标签页
 */
