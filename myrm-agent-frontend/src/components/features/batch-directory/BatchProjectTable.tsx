'use client';

/**
 * [INPUT] ./batchProjectModel (POS: 进度与时间格式化), ./BatchStatusBadges::BatchListStatusBadge (POS: 状态徽标), ./BatchConfirmAlert (POS: 二次确认弹窗)
 * [OUTPUT] BatchProjectTable: 批量项目表格（名称链接、状态、进度、目录数、创建时间，以及打开详情 / 取消 / 删除动作）
 * [POS] 列表页的项目表；运行中的项目只能取消，其余项目只能删除，两种操作都需二次确认。
 */

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { ArrowRight, Loader2, XCircle } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent } from '@/components/primitives/card';
import { Progress } from '@/components/primitives/progress';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/primitives/table';
import type { BatchProject } from '@/services/batch-directory';
import { BatchConfirmAlert } from './BatchConfirmAlert';
import { BatchListStatusBadge } from './BatchStatusBadges';
import { batchProgressPercent, formatDateTime } from './batchProjectModel';

interface BatchProjectTableProps {
  projects: BatchProject[];
  cancellingId: string | null;
  onCancel: (project: BatchProject) => Promise<void>;
  onDelete: (project: BatchProject) => Promise<void>;
}

interface BatchProjectRowProps extends Omit<BatchProjectTableProps, 'projects'> {
  project: BatchProject;
}

function BatchProjectRow({ project: p, cancellingId, onCancel, onDelete }: BatchProjectRowProps) {
  const t = useTranslations('batchDirectory');
  const detailHref = `/batch-directories/${p.project_id}`;

  return (
    <TableRow data-testid="bd-project-row">
      <TableCell className="font-medium">
        <Link href={detailHref} className="hover:underline" data-testid="bd-project-row-name">
          {p.name}
        </Link>
      </TableCell>
      <TableCell>
        <BatchListStatusBadge status={p.status} />
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2 min-w-36">
          <Progress value={batchProgressPercent(p)} className="w-24" />
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {p.completed_tasks}/{p.total_tasks}
          </span>
        </div>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">{t('dirsCount', { count: p.directories.length })}</TableCell>
      <TableCell className="text-xs text-muted-foreground">{formatDateTime(p.created_at)}</TableCell>
      <TableCell className="text-right">
        <div className="flex justify-end gap-1">
          <Button variant="ghost" size="sm" asChild aria-label={t('openDetailLabel', { name: p.name })}>
            <Link href={detailHref}>
              <ArrowRight className="size-4" />
            </Link>
          </Button>
          {p.status === 'running' ? (
            <BatchConfirmAlert
              trigger={
                <Button variant="outline" size="sm" disabled={cancellingId === p.project_id}>
                  {cancellingId === p.project_id ? <Loader2 className="size-4 animate-spin" /> : t('cancelAction')}
                </Button>
              }
              title={t('confirmCancelTitle', { name: p.name })}
              description={t('confirmCancelDescription')}
              confirmLabel={t('confirmCancelAction')}
              onConfirm={() => void onCancel(p)}
            />
          ) : (
            <BatchConfirmAlert
              trigger={
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive-text"
                  aria-label={t('deleteLabel', { name: p.name })}
                >
                  <XCircle className="size-4" />
                </Button>
              }
              title={t('confirmDeleteTitle', { name: p.name })}
              description={t('confirmDeleteDescription')}
              confirmLabel={t('confirmDeleteAction')}
              onConfirm={() => void onDelete(p)}
              destructive
            />
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}

export function BatchProjectTable({ projects, cancellingId, onCancel, onDelete }: BatchProjectTableProps) {
  const t = useTranslations('batchDirectory');

  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('tableName')}</TableHead>
              <TableHead>{t('tableStatus')}</TableHead>
              <TableHead>{t('tableProgress')}</TableHead>
              <TableHead>{t('tableDirectories')}</TableHead>
              <TableHead>{t('tableCreated')}</TableHead>
              <TableHead className="text-right">{t('tableActions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {projects.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-10 text-muted-foreground">
                  {t('emptyState')}
                </TableCell>
              </TableRow>
            )}
            {projects.map((p) => (
              <BatchProjectRow
                key={p.project_id}
                project={p}
                cancellingId={cancellingId}
                onCancel={onCancel}
                onDelete={onDelete}
              />
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
