'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, Trash2, FolderOpen, RefreshCw, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useSkillStore } from '@/store/skill';
import { toast } from '@/hooks/useToast';

interface LocalPathsConfigProps {
  className?: string;
}

const LocalPathsConfig = memo(({ className }: LocalPathsConfigProps) => {
  const t = useTranslations('settings.skills.local');

  const {
    localSkillPaths,
    defaultLocalPaths,
    localSkills,
    isLoadingLocal,
    fetchLocalSkillPaths,
    addLocalSkillPath,
    removeLocalSkillPath,
    scanLocalSkills,
  } = useSkillStore();

  const [newPath, setNewPath] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [isScanning, setIsScanning] = useState(false);

  // 使用 isMounted 状态来避免 hydration 不匹配
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  // 初始化加载
  useEffect(() => {
    fetchLocalSkillPaths();
  }, [fetchLocalSkillPaths]);

  // 添加路径
  const handleAddPath = useCallback(async () => {
    if (!newPath.trim()) return;

    // 验证路径格式
    if (!newPath.startsWith('/') && !newPath.startsWith('~')) {
      toast({
        title: t('error.invalidPath'),
        description: t('error.pathFormat'),
        variant: 'destructive',
      });
      return;
    }

    setIsAdding(true);
    try {
      await addLocalSkillPath(newPath.trim());
      setNewPath('');
      toast({
        title: t('success.pathAdded'),
        description: newPath.trim(),
      });
    } catch (error) {
      toast({
        title: t('error.addFailed'),
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setIsAdding(false);
    }
  }, [newPath, addLocalSkillPath, t]);

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
              {localSkillPaths.map((path) => (
                <div key={path} className="flex items-center justify-between gap-2 p-3 rounded-lg bg-muted/50 group">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <FolderOpen className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <code className="text-sm truncate">{path}</code>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity text-destructive hover:text-destructive"
                    onClick={() => handleRemovePath(path)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 添加新路径 */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t('addPath')}</label>
          <div className="flex gap-2">
            <Input
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
            <Button onClick={handleAddPath} disabled={!newPath.trim() || isAdding}>
              <Plus className="h-4 w-4 mr-2" />
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
      </CardContent>
    </Card>
  );
});

LocalPathsConfig.displayName = 'LocalPathsConfig';

export default LocalPathsConfig;
