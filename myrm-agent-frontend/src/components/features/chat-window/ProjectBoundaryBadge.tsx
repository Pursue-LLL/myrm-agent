'use client';

/**
 * [INPUT]
 * - @/store/useChatStore (POS: current chatId & chatHistoryItems to resolve assigned projectId)
 * - @/store/useProjectStore (POS: project list & activeFilter fallback)
 * - lucide-react::FolderLock (POS: secure boundary indicator icon)
 *
 * [OUTPUT]
 * - ProjectBoundaryBadge: Subtle indicator displaying current project isolation status
 *
 * [POS]
 * Chat composer visibility layer for project-level sandbox boundary & zero-leakage memory isolation.
 * Rendered above composer input when the active session belongs to a project.
 */

import { useMemo } from 'react';
import { FolderLock } from 'lucide-react';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';
import type { Project } from '@/services/projects';

interface ProjectBoundaryBadgeProps {
  className?: string;
}

export default function ProjectBoundaryBadge({ className = '' }: ProjectBoundaryBadgeProps) {
  const chatId = useChatStore((state) => state.chatId);
  const chatHistoryItems = useChatStore((state) => state.chatHistoryItems);
  const projects = useProjectStore((state) => state.projects);
  const activeFilter = useProjectStore((state) => state.activeFilter);

  const matchedProject: Project | null = useMemo(() => {
    // 1. Try finding projectId from active chat history item
    let targetProjectId: string | null = null;
    if (chatId) {
      const activeItem = chatHistoryItems.find((item) => item.id === chatId);
      if (activeItem?.projectId) {
        targetProjectId = activeItem.projectId;
      }
    }

    // 2. Fall back to activeFilter when in a newly created or active project session
    if (!targetProjectId && typeof activeFilter === 'string' && activeFilter.trim().length > 0) {
      targetProjectId = activeFilter;
    }

    if (!targetProjectId) {
      return null;
    }

    return projects.find((p) => p.id === targetProjectId) ?? null;
  }, [chatId, chatHistoryItems, projects, activeFilter]);

  if (!matchedProject) {
    return null;
  }

  const tooltipText = matchedProject.workspacePath
    ? `项目隔离工作区: ${matchedProject.workspacePath}`
    : '项目沙箱与专属记忆隔离已激活';

  return (
    <div
      data-testid="project-boundary-badge"
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 mb-2 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-emerald-800 dark:text-emerald-200 text-xs w-fit select-none transition-colors ${className}`}
      title={tooltipText}
    >
      <FolderLock className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
      <span className="font-medium truncate max-w-[180px] sm:max-w-[240px]">{matchedProject.name}</span>
      <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-900 dark:text-emerald-100 font-semibold tracking-wide">
        隔离保护
      </span>
    </div>
  );
}
