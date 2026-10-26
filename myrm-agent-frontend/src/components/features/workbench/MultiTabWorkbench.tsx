'use client';

/**
 * [INPUT]
 * - useWorkbenchStore from @/store/useWorkbenchStore
 * - useChatStore from @/store/useChatStore (POS: the chat whose workspace the tabs work in)
 * - WorkbenchFileExplorer, WorkbenchTerminal from ./tabs
 * - useTranslations from next-intl (namespace: 'workbench')
 *
 * [OUTPUT]
 * - MultiTabWorkbench: Resizable right & bottom multi-tab auxiliary drawer shell
 *
 * [POS]
 * Auxiliary Workbench container orchestrator: files and terminal of the current chat's workspace.
 * Selection and terminal history reset whenever the chat changes.
 */

import React, { useRef, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  FolderTree,
  Terminal,
  X,
  PanelRight,
  PanelBottom,
  GripVertical,
  GripHorizontal,
} from 'lucide-react';
import useChatStore from '@/store/useChatStore';
import { useWorkbenchStore, type WorkbenchTabId } from '@/store/useWorkbenchStore';
import { WorkbenchFileExplorer } from './tabs/WorkbenchFileExplorer';
import { WorkbenchTerminal } from './tabs/WorkbenchTerminal';

export function MultiTabWorkbench() {
  const t = useTranslations('workbench');
  const isOpen = useWorkbenchStore((s) => s.isOpen);
  const placement = useWorkbenchStore((s) => s.placement);
  const width = useWorkbenchStore((s) => s.width);
  const height = useWorkbenchStore((s) => s.height);
  const activeTab = useWorkbenchStore((s) => s.activeTab);
  const chatId = useChatStore((s) => s.chatId);

  const setOpen = useWorkbenchStore((s) => s.setOpen);
  const setPlacement = useWorkbenchStore((s) => s.setPlacement);
  const setWidth = useWorkbenchStore((s) => s.setWidth);
  const setHeight = useWorkbenchStore((s) => s.setHeight);
  const setActiveTab = useWorkbenchStore((s) => s.setActiveTab);
  const resetWorkspaceSession = useWorkbenchStore((s) => s.resetWorkspaceSession);

  const [isResizing, setIsResizing] = useState<boolean>(false);
  const startPosRef = useRef<number>(0);
  const startDimRef = useRef<number>(0);

  // File selection and terminal history describe one chat's workspace
  useEffect(() => {
    resetWorkspaceSession();
  }, [chatId, resetWorkspaceSession]);

  // Keyboard shortcut: Escape to close workbench
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, setOpen]);

  // Handle resizing drag
  const handleMouseDownResize = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsResizing(true);
      if (placement === 'right') {
        startPosRef.current = e.clientX;
        startDimRef.current = width;
      } else {
        startPosRef.current = e.clientY;
        startDimRef.current = height;
      }

      const handleMouseMove = (moveEvent: MouseEvent) => {
        if (placement === 'right') {
          const delta = startPosRef.current - moveEvent.clientX;
          setWidth(startDimRef.current + delta);
        } else {
          const delta = startPosRef.current - moveEvent.clientY;
          setHeight(startDimRef.current + delta);
        }
      };

      const handleMouseUp = () => {
        setIsResizing(false);
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };

      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    },
    [placement, width, height, setWidth, setHeight],
  );

  if (!isOpen) {
    return null;
  }

  const tabs: Array<{ id: WorkbenchTabId; label: string; icon: React.ComponentType<{ className?: string }> }> = [
    { id: 'files', label: t('tabFiles'), icon: FolderTree },
    { id: 'terminal', label: t('tabTerminal'), icon: Terminal },
  ];

  return (
    <aside
      aria-label={t('workbenchAriaLabel')}
      style={
        placement === 'right'
          ? { width: `${width}px` }
          : { height: `${height}px` }
      }
      className={`fixed z-[9970] bg-card border-border shadow-2xl backdrop-blur-md flex flex-col select-none transition-all ${
        isResizing ? 'select-none pointer-events-auto' : ''
      } ${
        placement === 'right'
          ? 'top-0 right-0 bottom-0 border-l max-w-[90vw]'
          : 'bottom-0 left-0 right-0 border-t max-h-[80vh]'
      }`}
    >
      {/* Resize Handle */}
      <button
        type="button"
        onMouseDown={handleMouseDownResize}
        aria-label={t('resizeHandleAria')}
        className={`absolute z-10 flex items-center justify-center transition-colors group border-0 bg-transparent p-0 ${
          placement === 'right'
            ? 'left-0 top-0 bottom-0 w-2.5 -translate-x-1/2 cursor-ew-resize hover:bg-primary/20'
            : 'top-0 left-0 right-0 h-2.5 -translate-y-1/2 cursor-ns-resize hover:bg-primary/20'
        }`}
      >
        <span className="p-0.5 rounded bg-muted/80 text-muted-foreground group-hover:text-primary transition-colors">
          {placement === 'right' ? (
            <GripVertical className="w-3 h-3" />
          ) : (
            <GripHorizontal className="w-3 h-3" />
          )}
        </span>
      </button>

      {/* Workbench Header & Tab Bar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/60 bg-muted/40">
        {/* Navigation Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-hide">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-card text-foreground shadow-xs font-semibold border border-border/80'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-primary' : ''}`} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1 shrink-0">
          {/* Switch Placement */}
          <button
            type="button"
            onClick={() => setPlacement(placement === 'right' ? 'bottom' : 'right')}
            title={placement === 'right' ? t('dockBottom') : t('dockRight')}
            aria-label={placement === 'right' ? t('dockBottom') : t('dockRight')}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            {placement === 'right' ? (
              <PanelBottom className="w-4 h-4" />
            ) : (
              <PanelRight className="w-4 h-4" />
            )}
          </button>

          {/* Close Workbench */}
          <button
            type="button"
            onClick={() => setOpen(false)}
            title={t('closeAction')}
            aria-label={t('closeAction')}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Tab Panel Content */}
      <div className="flex-1 overflow-hidden relative">
        {!chatId && (
          <div className="h-full flex flex-col items-center justify-center gap-2 p-6 text-center text-xs text-muted-foreground">
            <FolderTree className="w-8 h-8 opacity-40" />
            <span>{t('noChat')}</span>
          </div>
        )}
        {chatId && activeTab === 'files' && <WorkbenchFileExplorer key={chatId} chatId={chatId} />}
        {chatId && activeTab === 'terminal' && <WorkbenchTerminal key={chatId} chatId={chatId} />}
      </div>
    </aside>
  );
}
