'use client';

/**
 * Batch directory parallel prompt runner — list + create wizard.
 *
 * [INPUT]
 * - @/components/features/batch-directory (POS: 项目表 / 统计 / 创建向导与其状态 hooks)
 * - @/services/batch-directory::BatchProjectDetail (POS: 创建结果)
 *
 * [OUTPUT]
 * - BatchDirectoriesPage: 批量项目列表 + 创建向导
 *
 * [POS]
 * BatchDirectory 列表页薄壳。装配项目列表、聚合统计与创建向导；创建成功后刷新列表并跳转详情。
 */

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Plus } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Skeleton } from '@/components/primitives/skeleton';
import { BatchProjectCreateCard } from '@/components/features/batch-directory/BatchProjectCreateCard';
import { BatchProjectStats } from '@/components/features/batch-directory/BatchProjectStats';
import { BatchProjectTable } from '@/components/features/batch-directory/BatchProjectTable';
import { useBatchProjectCreate } from '@/components/features/batch-directory/useBatchProjectCreate';
import { useBatchProjects } from '@/components/features/batch-directory/useBatchProjects';
import type { BatchProjectDetail } from '@/services/batch-directory';

export default function BatchDirectoriesPage() {
  const t = useTranslations('batchDirectory');
  const router = useRouter();
  const [showCreate, setShowCreate] = useState(false);
  const { projects, loading, cancellingId, summary, refresh, cancel, remove } = useBatchProjects();

  const handleCreated = useCallback(
    async (created: BatchProjectDetail) => {
      setShowCreate(false);
      await refresh();
      router.push(`/batch-directories/${created.project_id}`);
    },
    [refresh, router],
  );
  const create = useBatchProjectCreate({ active: showCreate, onCreated: handleCreated });

  if (loading) {
    return (
      <div className="container mx-auto max-w-5xl px-4 py-8 space-y-4">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-5xl px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t('pageTitle')}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t('pageDescription')}</p>
        </div>
        <Button onClick={() => setShowCreate((v) => !v)} disabled={create.creating}>
          <Plus className="size-4 mr-1" />
          {t('createButton')}
        </Button>
      </div>

      {showCreate ? (
        <BatchProjectCreateCard create={create} onCancel={() => setShowCreate(false)} />
      ) : (
        <BatchProjectStats summary={summary} />
      )}

      <BatchProjectTable projects={projects} cancellingId={cancellingId} onCancel={cancel} onDelete={remove} />
    </div>
  );
}
