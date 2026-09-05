'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, Trash2, FolderOpen, RefreshCw, AlertCircle, Loader2, Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Badge } from '@/components/primitives/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Alert, AlertDescription } from '@/components/primitives/alert';
import { useSkillStore } from '@/store/skill';
import { toast } from '@/hooks/shared/useToast';
import { previewLocalSkillPath } from '@/services/skill';
import type { LocalSkillPathPreviewResponse } from '@/store/skill/types';
import { LocalSkillPathScanPreviewBeforeAdoptDialog } from './LocalSkillPathScanPreviewBeforeAdoptDialog';

interface LocalPathsConfigProps {
  className?: string;
}

const LocalPathsConfig = memo(({ className }: LocalPathsConfigProps) => {
  const t = useTranslations('settings.skills.local');

  const {
    localSkillPaths,
    defaultLocalPaths,
    localPathStatuses,
    localSkills,
    isLoadingLocal,
    fetchLocalSkillPaths,
    addLocalSkillPath,
    adoptLocalSkillPath,
    removeLocalSkillPath,
    scanLocalSkills,
  } = useSkillStore();

  const [newPath, setNewPath] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  // 探测预览与两段式采纳状态
  const [previewData, setPreviewData] = useState<LocalSkillPathPreviewResponse | null>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [isAdopting, setIsAdopting] = useState(false);

  // 使用 isMounted 状态来避免 hydration 不匹配
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  // 初始化加载
  useEffect(() => {
    fetchLocalSkillPaths();
  }, [fetchLocalSkillPaths]);

  // 探查路径并唤起预览弹窗
  const handleAddPath = useCallback(async () => {
    const trimmed = newPath.trim();
    if (!trimmed) {
      return;
    }

    // 验证路径格式
    if (!trimmed.startsWith('/') && !trimmed.startsWith('~')) {
      toast({
        title: t('error.invalidPath'),
        description: t('error.pathFormat'),
        variant: 'destructive',
      });
      return;
    }

    // 防范路径穿越 (CWE-22)
    if (trimmed.includes('..')) {
      toast({
        title: t('error.invalidPath'),
        description: t('error.pathTraversal'),
        variant: 'destructive',
      });
      return;
    }

    if (localSkillPaths.includes(trimmed)) {
      toast({
        title: t('error.addFailed'),
        description: t('customPaths'),
        variant: 'destructive',
      });
      return;
    }

    setIsAdding(true);
    try {
      const preview = await previewLocalSkillPath(trimmed);
      if (!preview.exists || !preview.is_directory) {
        toast({
          title: t('error.previewFailed'),
          description: preview.warning_message || t('error.invalidPath'),
          variant: 'destructive',
        });
        return;
      }

      setPreviewData(preview);
      setIsPreviewOpen(true);
    } catch (error) {
      toast({
        title: t('error.previewFailed'),
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setIsAdding(false);
    }
  }, [newPath, localSkillPaths, t]);

  // 确认采纳路径并持久化（调用原子采纳接口，启用用户勾选的技能）
  const handleConfirmAdopt = useCallback(
    async (selectedSkillIds: string[]) => {
      if (!previewData) {
        return;
      }

      setIsAdopting(true);
      try {
        const targetPath = newPath.trim();
        await adoptLocalSkillPath(targetPath, selectedSkillIds);
        setNewPath('');
        setIsPreviewOpen(false);
        setPreviewData(null);
        toast({
          title: t('success.pathAdded'),
          description: t('success.foundSkills', { count: previewData.total_discovered }),
        });
      } catch (error) {
        toast({
          title: t('error.addFailed'),
          description: error instanceof Error ? error.message : 'Unknown error',
          variant: 'destructive',
        });
      } finally {
        setIsAdopting(false);
      }
    },
    [previewData, newPath, adoptLocalSkillPath, t],
  );

  // 仅添加路径（不采纳启用任何技能）
  const handleAddPathOnly = useCallback(async () => {
    if (!previewData) {
      return;
    }

    setIsAdopting(true);
    try {
      const targetPath = newPath.trim();
      await adoptLocalSkillPath(targetPath, []);
      setNewPath('');
      setIsPreviewOpen(false);
      setPreviewData(null);
      toast({
        title: t('success.pathAdded'),
        description: targetPath,
      });
    } catch (error) {
      toast({
        title: t('error.addFailed'),
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setIsAdopting(false);
    }
  }, [previewData, newPath, adoptLocalSkillPath, t]);

  // 复制路径到剪贴板
  const handleCopyPath = useCallback(
    async (path: string) => {
      try {
        await navigator.clipboard.writeText(path);
        setCopiedPath(path);
        toast({
          title: t('success.pathCopied'),
        });
        setTimeout(() => setCopiedPath(null), 2000);
      } catch {
        // Fallback or ignore
      }
    },
    [t],
  );

  // 移除路径
  const handleRemovePath = useCallback(
    async (path: string) => {
      try {
        await removeLocalSkillPath(path);
        toast({
          title: t('success.pathRemoved'),
        });
      } catch (error) {
        toast({
          title: t('error.removeFailed'),
          description: error instanceof Error ? error.message : 'Unknown error',
          variant: 'destructive',
        });
      }
    },
    [removeLocalSkillPath, t],
  );

  // 扫描技能
  const handleScan = useCallback(async () => {
    setIsScanning(true);
    try {
      await scanLocalSkills();
      toast({
        title: t('success.scanComplete'),
        description: t('success.foundSkills', { count: localSkills.length }),
      });
    } catch (error) {
      toast({
        title: t('error.scanFailed'),
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setIsScanning(false);
    }
  }, [scanLocalSkills, localSkills.length, t]);

  if (!isMounted) {
    return null;
  }

  return (
    <Card className={cn('', className)}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <FolderOpen className="h-5 w-5" />
              {t('title')}
            </CardTitle>
            <CardDescription className="mt-1">{t('description')}</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={handleScan} disabled={isScanning || isLoadingLocal}>
            <RefreshCw className={cn('h-4 w-4 mr-2', (isScanning || isLoadingLocal) && 'animate-spin')} />
            {t('scan')}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* 默认路径提示 */}
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {t('defaultPathHint')}:{' '}
            {defaultLocalPaths.length > 0 ? defaultLocalPaths.join(', ') : t('defaultPathPlaceholder')}
          </AlertDescription>
        </Alert>

        {/* 已配置的路径列表 */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t('customPaths')}</label>

          {localSkillPaths.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">{t('noCustomPaths')}</p>
          ) : (
            <div className="space-y-2">
              {localSkillPaths.map((path) => {
                const status = localPathStatuses.find((s) => s.path === path);
                return (
                  <div key={path} className="flex items-center justify-between gap-2 p-3 rounded-lg bg-muted/50 group border border-border/40 hover:border-border transition-colors">
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <FolderOpen className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      <code className="text-sm truncate font-mono">{path}</code>
                      {status && (
                        <div className="flex items-center gap-1.5 shrink-0">
                          {status.skills_count > 0 ? (
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10">
                              {t('discoveredSkillsBadge', { count: status.skills_count })}
                            </Badge>
                          ) : !status.exists ? (
                            <Badge variant="destructive" className="text-[10px] px-1.5 py-0">
                              {t('pathNotFoundBadge')}
                            </Badge>
                          ) : (
                            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 text-muted-foreground">
                              {t('emptySkillsBadge')}
                            </Badge>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-foreground"
                        title={t('copyPath')}
                        onClick={() => handleCopyPath(path)}
                      >
                        {copiedPath === path ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity text-destructive hover:text-destructive"
                        onClick={() => handleRemovePath(path)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 添加新路径 */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t('addPath')}</label>
          <div className="flex gap-2">
            <Input
              data-testid="local-skill-path-input"
              placeholder={t('pathPlaceholder')}
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAddPath();
                }
              }}
              className="flex-1"
            />
            <Button data-testid="local-skill-path-add-btn" onClick={handleAddPath} disabled={!newPath.trim() || isAdding}>
              {isAdding ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Plus className="h-4 w-4 mr-2" />
              )}
              {t('add')}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">{t('pathFormatHint')}</p>
        </div>

        {/* 扫描到的技能数量 */}
        {localSkills.length > 0 && (
          <div className="pt-2 border-t">
            <div className="flex items-center gap-2">
              <Badge variant="secondary">{t('foundSkillsCount', { count: localSkills.length })}</Badge>
            </div>
          </div>
        )}

        {/* 预检与采纳确认弹窗 */}
        <LocalSkillPathScanPreviewBeforeAdoptDialog
          open={isPreviewOpen}
          onOpenChange={setIsPreviewOpen}
          previewData={previewData}
          onConfirmAdopt={handleConfirmAdopt}
          onAddPathOnly={handleAddPathOnly}
          isAdopting={isAdopting}
        />
      </CardContent>
    </Card>
  );
});

LocalPathsConfig.displayName = 'LocalPathsConfig';

export default LocalPathsConfig;
