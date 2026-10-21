import { useEffect } from 'react';
import { useGlobalCommandHubStore } from './useGlobalCommandHubStore';

export const useGlobalCommandShortcuts = (): void => {
  const {
    isOpen,
    toggleHub,
    closeHub,
    selectNext,
    selectPrevious,
    executeSelectedCommand,
  } = useGlobalCommandHubStore();

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent): void => {
      // 1. ⌘K 或 Ctrl+K 全局呼出/关闭
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        toggleHub();
        return;
      }

      // 仅当面板打开时接管键盘导航
      if (!isOpen) {
        return;
      }

      if (event.key === 'Escape') {
        event.preventDefault();
        closeHub();
        return;
      }

      if (event.key === 'ArrowDown') {
        event.preventDefault();
        selectNext();
        return;
      }

      if (event.key === 'ArrowUp') {
        event.preventDefault();
        selectPrevious();
        return;
      }

      if (event.key === 'Enter') {
        event.preventDefault();
        executeSelectedCommand();
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, toggleHub, closeHub, selectNext, selectPrevious, executeSelectedCommand]);
};
