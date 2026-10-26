'use client';

/**
 * Workspace file right-click menu
 *
 * [INPUT]
 * - state: Click position and the entry the menu was opened on
 * - FileEntry from @/services/chat
 *
 * [OUTPUT]
 * - ContextMenu: Menu anchored at the click and kept inside the viewport: rename, move, delete and, for folders,
 *   the AI-organize and project-root actions
 * - ContextMenuState: Click position and target entry
 *
 * [POS]
 * Menu half of WorkspaceFileBrowser's write operations, split from WorkspaceFileOps.tsx to keep each file under
 * 400 lines. Closes on any click, on another right-click and on Escape.
 */

import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { FolderOpen, Move, Pencil, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { FileEntry } from '@/services/chat';
import { useEscapeDismiss } from './useEscapeDismiss';

export interface ContextMenuState {
  x: number;
  y: number;
  node: FileEntry;
}

interface ContextMenuProps {
  state: ContextMenuState;
  onClose: () => void;
  onRename: (node: FileEntry) => void;
  onDelete: (node: FileEntry) => void;
  onMove: (node: FileEntry) => void;
  onOrganize?: (node: FileEntry) => void;
  onSetProjectRoot?: (node: FileEntry) => void;
}

export const ContextMenu: React.FC<ContextMenuProps> = ({
  state,
  onClose,
  onRename,
  onDelete,
  onMove,
  onOrganize,
  onSetProjectRoot,
}) => {
  const t = useTranslations('workspace');
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x: state.x, y: state.y });

  useEscapeDismiss(onClose);

  useEffect(() => {
    const handler = () => onClose();
    window.addEventListener('click', handler);
    window.addEventListener('contextmenu', handler);
    return () => {
      window.removeEventListener('click', handler);
      window.removeEventListener('contextmenu', handler);
    };
  }, [onClose]);

  useEffect(() => {
    const el = menuRef.current;
    if (!el) {
      return;
    }
    // Layout size rather than the bounding rect: the entry animation scales the menu, which would hide an overflow.
    const { offsetWidth, offsetHeight } = el;
    setPos({
      x: state.x + offsetWidth > window.innerWidth ? Math.max(0, state.x - offsetWidth) : state.x,
      y: state.y + offsetHeight > window.innerHeight ? Math.max(0, state.y - offsetHeight) : state.y,
    });
  }, [state.x, state.y]);

  const items = [
    ...(state.node.type === 'directory' && onSetProjectRoot
      ? [{ icon: FolderOpen, label: t('setProjectRoot'), action: () => onSetProjectRoot(state.node) }]
      : []),
    ...(state.node.type === 'directory' && onOrganize
      ? [{ icon: FolderOpen, label: t('organizeFolder'), action: () => onOrganize(state.node) }]
      : []),
    { icon: Pencil, label: t('rename'), action: () => onRename(state.node) },
    { icon: Move, label: t('move'), action: () => onMove(state.node) },
    { icon: Trash2, label: t('delete'), action: () => onDelete(state.node), danger: true },
  ];

  return (
    <motion.div
      ref={menuRef}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.1 }}
      className="fixed z-50 bg-popover border border-border rounded-lg shadow-lg py-1 min-w-[160px]"
      style={{ left: pos.x, top: pos.y }}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map(({ icon: Icon, label, action, danger }) => (
        <button
          key={label}
          className={cn(
            'flex items-center gap-2 w-full px-3 py-1.5 text-sm hover:bg-muted transition-colors',
            danger && 'text-destructive hover:text-destructive',
          )}
          onClick={(e) => {
            e.stopPropagation();
            action();
            onClose();
          }}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </button>
      ))}
    </motion.div>
  );
};
