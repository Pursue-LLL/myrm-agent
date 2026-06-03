/**
 * CLI 右键菜单组件
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - position: 菜单位置
 * - file: 目标文件节点
 * - onAction: 菜单操作回调
 *
 * [OUTPUT]
 * - CLIContextMenu: 右键菜单组件
 *   - 预览
 *   - 在编辑器中打开
 *   - 在 Finder 中显示
 *   - 复制路径
 *
 * [POS]
 * CLI 可视化工具的右键菜单组件。提供文件操作菜单，
 * 仅在 Tauri 桌面环境使用。
 */

'use client';

import React, { memo, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Eye, ExternalLink, Folder, Copy, FileText, FolderOpen } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { FileNode } from './CLIWorkspaceTree';

export interface CLIContextMenuProps {
  /** 菜单位置 */
  position: { x: number; y: number };
  /** 目标文件 */
  file: FileNode;
  /** 是否可见 */
  visible: boolean;
  /** 预览回调 */
  onPreview: () => void;
  /** 在编辑器中打开 */
  onOpenInEditor: () => void;
  /** 在 Finder 中显示 */
  onShowInFinder: () => void;
  /** 复制路径 */
  onCopyPath: () => void;
  /** 关闭菜单 */
  onClose: () => void;
  /** 类名 */
  className?: string;
}

interface MenuItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  divider?: boolean;
}

/**
 * CLI 右键菜单组件
 */
export const CLIContextMenu: React.FC<CLIContextMenuProps> = memo(
  ({ position, file, visible, onPreview, onOpenInEditor, onShowInFinder, onCopyPath, onClose, className }) => {
    const menuRef = useRef<HTMLDivElement>(null);
    const isDirectory = file.type === 'directory';

    // 点击外部关闭
    useEffect(() => {
      const handleClickOutside = (event: MouseEvent) => {
        if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
          onClose();
        }
      };

      if (visible) {
        document.addEventListener('mousedown', handleClickOutside);
        // 按 ESC 关闭
        const handleKeyDown = (event: KeyboardEvent) => {
          if (event.key === 'Escape') {
            onClose();
          }
        };
        document.addEventListener('keydown', handleKeyDown);

        return () => {
          document.removeEventListener('mousedown', handleClickOutside);
          document.removeEventListener('keydown', handleKeyDown);
        };
      }
    }, [visible, onClose]);

    // 菜单项
    const menuItems: MenuItem[] = [
      // 文件专用：预览
      ...(!isDirectory
        ? [
            {
              id: 'preview',
              label: 'Preview',
              icon: <Eye className="h-4 w-4" />,
              onClick: () => {
                onPreview();
                onClose();
              },
            },
          ]
        : []),
      // 在编辑器中打开
      {
        id: 'open',
        label: isDirectory ? 'Open in Finder' : 'Open in Editor',
        icon: isDirectory ? <FolderOpen className="h-4 w-4" /> : <ExternalLink className="h-4 w-4" />,
        onClick: () => {
          if (isDirectory) {
            onShowInFinder();
          } else {
            onOpenInEditor();
          }
          onClose();
        },
      },
      // 在 Finder 中显示
      ...(!isDirectory
        ? [
            {
              id: 'reveal',
              label: 'Reveal in Finder',
              icon: <Folder className="h-4 w-4" />,
              onClick: () => {
                onShowInFinder();
                onClose();
              },
              divider: true,
            },
          ]
        : []),
      // 复制路径
      {
        id: 'copy',
        label: 'Copy Path',
        icon: <Copy className="h-4 w-4" />,
        onClick: () => {
          onCopyPath();
          onClose();
        },
      },
    ];

    // 处理菜单项点击
    const handleItemClick = useCallback((item: MenuItem) => {
      if (!item.disabled) {
        item.onClick();
      }
    }, []);

    // 计算菜单位置（避免超出屏幕）
    const getAdjustedPosition = useCallback(() => {
      const menuWidth = 180;
      const menuHeight = menuItems.length * 36 + 16;
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;

      let x = position.x;
      let y = position.y;

      // 避免超出右边界
      if (x + menuWidth > viewportWidth) {
        x = viewportWidth - menuWidth - 8;
      }

      // 避免超出下边界
      if (y + menuHeight > viewportHeight) {
        y = viewportHeight - menuHeight - 8;
      }

      return { x, y };
    }, [position, menuItems.length]);

    const adjustedPosition = getAdjustedPosition();

    return (
      <AnimatePresence>
        {visible && (
          <motion.div
            ref={menuRef}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.1 }}
            className={cn(
              'fixed z-50 min-w-[180px] py-1',
              'bg-popover border border-border rounded-lg shadow-lg',
              className,
            )}
            style={{
              left: adjustedPosition.x,
              top: adjustedPosition.y,
            }}
          >
            {/* 文件信息头 */}
            <div className="px-3 py-2 border-b border-border mb-1">
              <div className="flex items-center gap-2">
                {isDirectory ? (
                  <Folder className="h-4 w-4 text-amber-500" />
                ) : (
                  <FileText className="h-4 w-4 text-muted-foreground" />
                )}
                <span className="text-sm font-medium truncate max-w-[140px]" title={file.name}>
                  {file.name}
                </span>
              </div>
            </div>

            {/* 菜单项 */}
            {menuItems.map((item, index) => (
              <React.Fragment key={item.id}>
                {item.divider && index > 0 && <div className="h-px bg-border my-1" />}
                <button
                  onClick={() => handleItemClick(item)}
                  disabled={item.disabled}
                  className={cn(
                    'w-full flex items-center gap-2 px-3 py-2 text-sm text-left',
                    'hover:bg-muted transition-colors',
                    item.disabled && 'opacity-50 cursor-not-allowed',
                  )}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </button>
              </React.Fragment>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    );
  },
);

CLIContextMenu.displayName = 'CLIContextMenu';

export default CLIContextMenu;
