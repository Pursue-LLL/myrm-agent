'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useTheme } from 'next-themes';
import ReactDiffViewer from 'react-diff-viewer';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useSkillVersions, type SkillVersionSummary } from '@/hooks/useSkillVersions';

interface SkillVersionHistoryProps {
  skillId: string;
}

export function SkillVersionHistory({ skillId }: SkillVersionHistoryProps) {
  const t = useTranslations('settings.skillOptimization.versions');
  const tParent = useTranslations('settings.skillOptimization');
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const { versions, loading, fetchVersions, getVersionDetail, compareVersions, rollbackToVersion } =
    useSkillVersions(skillId);

  const [rollbackTarget, setRollbackTarget] = useState<number | null>(null);
  const [rollbackLoading, setRollbackLoading] = useState(false);
  const [contentDialogVersion, setContentDialogVersion] = useState<number | null>(null);
  const [contentDialogText, setContentDialogText] = useState('');
  const [compareDialog, setCompareDialog] = useState<{
    v1: number;
    v2: number;
  } | null>(null);
  const [compareResult, setCompareResult] = useState<{
    score_delta: Record<string, number> | null;
    content_changed: boolean;
    v1_content: string;
    v2_content: string;
  } | null>(null);
  const [selectedForCompare, setSelectedForCompare] = useState<number | null>(null);

  useEffect(() => {
    fetchVersions();
  }, [fetchVersions]);

  const handleViewContent = useCallback(
    async (version: number) => {
      const detail = await getVersionDetail(version);
      if (detail) {
        setContentDialogText(detail.content);
        setContentDialogVersion(version);
      }
    },
    [getVersionDetail],
  );

  const handleRollback = useCallback(
    async (version: number) => {
      setRollbackLoading(true);
      try {
        await rollbackToVersion(version);
      } finally {
        setRollbackLoading(false);
        setRollbackTarget(null);
      }
    },
    [rollbackToVersion],
  );

  const handleCompare = useCallback(
    async (v1: number, v2: number) => {
      setCompareDialog({ v1, v2 });
      const result = await compareVersions(v1, v2);
      if (result) {
        setCompareResult({
          score_delta: result.score_delta,
          content_changed: result.content_changed,
          v1_content: result.v1.content,
          v2_content: result.v2.content,
        });
      }
      setSelectedForCompare(null);
    },
    [compareVersions],
  );

  const handleSelectForCompare = useCallback(
    (version: number) => {
      if (selectedForCompare === null) {
        setSelectedForCompare(version);
      } else if (selectedForCompare !== version) {
        handleCompare(selectedForCompare, version);
      } else {
        setSelectedForCompare(null);
      }
    },
    [selectedForCompare, handleCompare],
  );

  const formatCreatedBy = (createdBy: string) => {
    switch (createdBy) {
      case 'llm':
        return t('createdByLlm');
      case 'manual':
        return t('createdByManual');
      case 'rollback':
        return t('createdByRollback');
      default:
        return createdBy;
    }
  };

  if (loading && versions.length === 0) {
    return <div className="flex items-center justify-center py-8 text-muted-foreground">{t('noVersions')}</div>;
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold">{t('title')}</h3>

      {versions.length === 0 ? (
        <div className="py-8 text-center text-muted-foreground">{t('noVersions')}</div>
      ) : (
        <div className="rounded-full border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[80px]">{t('version')}</TableHead>
                <TableHead>{t('createdAt')}</TableHead>
                <TableHead>{t('createdBy')}</TableHead>
                <TableHead className="text-center">{t('active')}</TableHead>
                <TableHead className="text-right">{tParent('overallScore')}</TableHead>
                <TableHead className="text-right">{/* Actions */}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {versions.map((v) => (
                <VersionRow
                  key={v.version}
                  version={v}
                  selectedForCompare={selectedForCompare}
                  onViewContent={handleViewContent}
                  onRollback={setRollbackTarget}
                  onCompare={handleSelectForCompare}
                  formatCreatedBy={formatCreatedBy}
                  t={t}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Rollback Confirmation Dialog */}
      <Dialog open={rollbackTarget !== null} onOpenChange={() => setRollbackTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('rollback')}</DialogTitle>
            <DialogDescription>
              {rollbackTarget !== null && t('rollbackConfirm', { version: rollbackTarget })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRollbackTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={rollbackLoading}
              onClick={() => rollbackTarget !== null && handleRollback(rollbackTarget)}
            >
              {rollbackLoading ? '...' : t('rollback')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Content View Dialog */}
      <Dialog open={contentDialogVersion !== null} onOpenChange={() => setContentDialogVersion(null)}>
        <DialogContent className="max-h-[80vh] max-w-3xl overflow-auto">
          <DialogHeader>
            <DialogTitle>
              v{contentDialogVersion} - {t('viewContent')}
            </DialogTitle>
          </DialogHeader>
          <pre className="max-h-[60vh] overflow-auto rounded-lg bg-muted p-4 text-sm">{contentDialogText}</pre>
        </DialogContent>
      </Dialog>

      {/* Compare Dialog */}
      <Dialog
        open={compareDialog !== null}
        onOpenChange={() => {
          setCompareDialog(null);
          setCompareResult(null);
        }}
      >
        <DialogContent className="max-h-[90vh] max-w-5xl overflow-auto">
          <DialogHeader>
            <DialogTitle>{compareDialog && t('comparing', { v1: compareDialog.v1, v2: compareDialog.v2 })}</DialogTitle>
          </DialogHeader>
          {compareResult ? (
            <div className="space-y-4">
              {/* Score delta */}
              {compareResult.score_delta && (
                <div className="space-y-2">
                  <h4 className="font-medium">{t('scoreDelta')}</h4>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                    {Object.entries(compareResult.score_delta).map(([key, value]) => (
                      <div key={key} className="rounded-lg border p-2 text-center">
                        <div className="text-xs text-muted-foreground">{key}</div>
                        <div
                          className={`text-sm font-semibold ${
                            value > 0 ? 'text-green-500' : value < 0 ? 'text-red-500' : 'text-muted-foreground'
                          }`}
                        >
                          {value > 0 ? '+' : ''}
                          {(value * 100).toFixed(1)}%
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Content diff */}
              <div>
                <Badge variant={compareResult.content_changed ? 'default' : 'secondary'}>
                  {compareResult.content_changed ? t('contentChanged') : t('contentUnchanged')}
                </Badge>
              </div>

              {compareResult.content_changed && (
                <div className="max-h-[50vh] overflow-auto rounded-lg border">
                  <ReactDiffViewer
                    oldValue={compareResult.v1_content}
                    newValue={compareResult.v2_content}
                    splitView={true}
                    useDarkTheme={isDark}
                    leftTitle={`v${compareDialog?.v1}`}
                    rightTitle={`v${compareDialog?.v2}`}
                  />
                </div>
              )}
            </div>
          ) : (
            <div className="py-8 text-center text-muted-foreground">Loading...</div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface VersionRowProps {
  version: SkillVersionSummary;
  selectedForCompare: number | null;
  onViewContent: (version: number) => void;
  onRollback: (version: number) => void;
  onCompare: (version: number) => void;
  formatCreatedBy: (createdBy: string) => string;
  t: ReturnType<typeof useTranslations>;
}

function VersionRow({
  version: v,
  selectedForCompare,
  onViewContent,
  onRollback,
  onCompare,
  formatCreatedBy,
  t,
}: VersionRowProps) {
  return (
    <TableRow className={selectedForCompare === v.version ? 'bg-accent/50' : ''}>
      <TableCell className="font-mono font-medium">v{v.version}</TableCell>
      <TableCell className="text-muted-foreground">{new Date(v.created_at).toLocaleString()}</TableCell>
      <TableCell>
        <Badge variant="outline" className="text-xs">
          {formatCreatedBy(v.created_by)}
        </Badge>
      </TableCell>
      <TableCell className="text-center">
        {v.is_active ? (
          <Badge className="bg-green-500/10 text-green-600 dark:text-green-400">{t('active')}</Badge>
        ) : (
          <span className="text-xs text-muted-foreground">{t('inactive')}</span>
        )}
      </TableCell>
      <TableCell className="text-right font-mono">
        {v.quality_score ? (v.quality_score.overall_score * 100).toFixed(0) : '-'}
      </TableCell>
      <TableCell className="text-right">
        <div className="flex items-center justify-end gap-1">
          <Button variant="ghost" size="sm" onClick={() => onViewContent(v.version)}>
            {t('viewContent')}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onCompare(v.version)}
            className={selectedForCompare === v.version ? 'ring-2 ring-ring' : ''}
          >
            {t('compare')}
          </Button>
          {!v.is_active && (
            <Button
              variant="ghost"
              size="sm"
              className="text-orange-600 hover:text-orange-700"
              onClick={() => onRollback(v.version)}
            >
              {t('rollback')}
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}
