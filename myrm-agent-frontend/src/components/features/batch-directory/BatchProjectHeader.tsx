'use client';

/**
 * [INPUT] ./BatchProjectToolbar (POS: 动作栏), ./BatchStatusBadges::BatchProjectStatusBadge (POS: 状态徽标)
 * [OUTPUT] BatchProjectHeader: 详情页头部（返回列表按钮、项目名、状态徽标、项目 id、动作栏）
 * [POS] 详情页标题区；窄屏下标题与动作栏上下堆叠。
 */

import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { ChevronLeft } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import type { BatchProjectDetail } from '@/services/batch-directory';
import { BatchProjectStatusBadge } from './BatchStatusBadges';
import { BatchProjectToolbar } from './BatchProjectToolbar';
import type { BatchProjectFlags } from './batchProjectModel';
import type { BatchProjectActions } from './useBatchProjectActions';

interface BatchProjectHeaderProps {
  project: BatchProjectDetail;
  flags: BatchProjectFlags;
  actions: BatchProjectActions;
  onRefresh: () => Promise<void>;
}

export function BatchProjectHeader({ project, flags, actions, onRefresh }: BatchProjectHeaderProps) {
  const t = useTranslations('batchDirectory');
  const router = useRouter();

  return (
    <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-6">
      <div className="flex items-center gap-3 min-w-0">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => router.push('/batch-directories')}
          aria-label={t('backToList')}
        >
          <ChevronLeft className="size-5 shrink-0" />
        </Button>
        <div className="min-w-0" data-testid="bd-project-header">
          <h1 className="text-xl md:text-2xl font-semibold tracking-tight truncate" data-testid="bd-project-name">
            {project.name}
          </h1>
          <div className="text-sm text-muted-foreground mt-1 flex items-center gap-2 flex-wrap">
            <span data-testid="bd-project-status">
              <BatchProjectStatusBadge status={project.status} />
            </span>
            <span className="text-xs" data-testid="bd-project-id">
              {t('projectIdLabel', { id: project.project_id })}
            </span>
          </div>
        </div>
      </div>
      <BatchProjectToolbar project={project} flags={flags} actions={actions} onRefresh={onRefresh} />
    </div>
  );
}
