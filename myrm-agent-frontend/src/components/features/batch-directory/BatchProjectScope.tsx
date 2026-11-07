'use client';

/**
 * [INPUT] ./BatchStatusBadges::BATCH_TONE (POS: 危险色调), next-intl (POS: batchDirectory 文案)
 * [OUTPUT] BatchProjectScope: 详情页的提示词、产物匹配规则、目录清单（失败目录高亮）与缺失产物目录四张只读卡片
 * [POS] 描述批量项目「对什么目录跑什么」的范围信息；提示词与产物规则为空时不渲染，缺失产物目录仅在存在时渲染。
 */

import { useTranslations } from 'next-intl';
import { FolderOpen, XCircle } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { cn } from '@/lib/utils/classnameUtils';
import type { BatchProjectDetail } from '@/services/batch-directory';
import { BATCH_TONE } from './BatchStatusBadges';

function DirectoryChip({ dir, failed }: { dir: string; failed: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-mono',
        failed ? BATCH_TONE.danger : 'border-muted bg-muted/40 text-foreground',
      )}
    >
      {failed ? <XCircle className="size-3" /> : <FolderOpen className="size-3" />}
      <span className="max-w-64 truncate">{dir}</span>
    </span>
  );
}

export function BatchProjectScope({ project }: { project: BatchProjectDetail }) {
  const t = useTranslations('batchDirectory');
  const failedDirs = project.failed_directories ?? [];
  const missingDirs = project.missing_artifact_directories ?? [];

  return (
    <>
      {project.prompt && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">{t('promptTitle')}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap text-muted-foreground">{project.prompt}</p>
          </CardContent>
        </Card>
      )}

      {project.artifact_patterns.length > 0 && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">{t('artifactsTitle')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {project.artifact_patterns.map((pattern) => (
                <Badge key={pattern} variant="outline" className="font-mono">
                  {pattern}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Card data-testid="bd-directories-card">
        <CardHeader>
          <CardTitle className="text-base">{t('directoriesTitle')}</CardTitle>
          <CardDescription>{t('dirsCountTitle', { count: project.directories.length })}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {project.directories.map((dir) => (
              <DirectoryChip key={dir} dir={dir} failed={failedDirs.includes(dir)} />
            ))}
          </div>
        </CardContent>
      </Card>

      {missingDirs.length > 0 && (
        <Card className="mt-6 border-destructive/40 bg-destructive/5">
          <CardHeader>
            <CardTitle className="text-base text-destructive-text">{t('missingArtifactsTitle')}</CardTitle>
            <CardDescription>{t('missingArtifactsDescription')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {missingDirs.map((dir) => (
                <DirectoryChip key={dir} dir={dir} failed />
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </>
  );
}
