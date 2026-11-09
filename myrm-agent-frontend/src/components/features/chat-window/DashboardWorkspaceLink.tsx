'use client';

/**
 * [INPUT]
 * - @/components/features/dashboard-workspace/useDashboardWorkspaceStore::useDashboardWorkspaceStore
 * - @/components/primitives/tooltip::{Tooltip, TooltipContent, TooltipTrigger}
 *
 * [OUTPUT]
 * - DashboardWorkspaceLink: 会话工具栏里的工作台入口（固定组件数量 + 打开抽屉）
 *
 * [POS]
 * 聊天会话工具栏的薄入口：没有固定组件时不渲染，避免占用空白会话的横向空间。
 */

import { useTranslations } from 'next-intl';
import { LayoutDashboard } from 'lucide-react';
import { useDashboardWorkspaceStore } from '@/components/features/dashboard-workspace/useDashboardWorkspaceStore';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';

export function DashboardWorkspaceLink() {
  const t = useTranslations('dashboardWorkspace');
  const count = useDashboardWorkspaceStore((state) => state.widgets.length);
  const isDrawerOpen = useDashboardWorkspaceStore((state) => state.isDrawerOpen);
  const toggleDrawer = useDashboardWorkspaceStore((state) => state.toggleDrawer);

  if (count === 0 || isDrawerOpen) {
    return null;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={toggleDrawer}
          data-testid="dashboard-workspace-link"
          className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-muted/40 px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
        >
          <LayoutDashboard className="h-3 w-3" />
          <span>{t('pin')}</span>
          <span className="rounded-full bg-primary/10 px-1.5 font-medium text-primary">{count}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent>{t('drawerTitle')}</TooltipContent>
    </Tooltip>
  );
}
