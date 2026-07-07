'use client';

import { GitCompareArrows } from 'lucide-react';
import { sortKeys } from '@/services/config/configFingerprint';
import ReactDiffViewer from 'react-diff-viewer';
import { useTheme } from 'next-themes';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { cn } from '@/lib/utils/classnameUtils';

export interface ConfigConflictData {
  configKey: string;
  configLabel: string;
  serverVersion: string;
  localVersion: string;
  deviceId?: string;
  localValue?: unknown;
  serverValue?: unknown;
}

interface ConfigConflictDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conflict: ConfigConflictData | null;
  onKeepLocal: () => void;
  onUseServer: () => void;
  t?: (key: string, params?: Record<string, string>) => string;
}

const defaultTranslations = {
  title: 'Configuration Conflict Detected',
  description: '"{configLabel}" has been updated on another device',
  serverVersion: 'Server Version',
  localVersion: 'Local Version',
  device: 'Device',
  unknown: 'Unknown',
  keepLocal: 'Keep Local Changes',
  useServer: 'Use Server Version',
  keepLocalDesc: 'Overwrite server with your local changes',
  useServerDesc: 'Discard local changes and adopt server version',
};

/**
 * 配置冲突解决对话框
 *
 * 当多设备同时修改同一配置时，提供用户友好的冲突解决界面。
 * 替换原生 window.confirm，提供更好的移动端体验和 UI 一致性。
 */
export const ConfigConflictDialog = ({
  open,
  onOpenChange,
  conflict,
  onKeepLocal,
  onUseServer,
  t = (key, params?) => {
    const raw = defaultTranslations[key as keyof typeof defaultTranslations] || key;
    if (!params) return raw;
    return Object.entries(params).reduce((s, [k, v]) => s.replace(`{${k}}`, v), raw);
  },
}: ConfigConflictDialogProps) => {
  const { resolvedTheme } = useTheme();

  const oldCode = conflict?.serverValue ? JSON.stringify(sortKeys(conflict.serverValue), null, 2) : '';
  const newCode = conflict?.localValue ? JSON.stringify(sortKeys(conflict.localValue), null, 2) : '';
  const showDiff = !!(conflict?.serverValue && conflict?.localValue);

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="sm:max-w-[700px] max-h-[90vh] overflow-y-auto">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-amber-600 dark:text-amber-500">
            <GitCompareArrows size={20} />
            {t('title')}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="text-base pt-2 space-y-3">
              <div className="font-medium text-foreground">
                {t('description', { configLabel: conflict?.configLabel || '' })}
              </div>

              <div className="bg-muted/50 rounded-lg p-3 space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">{t('serverVersion')}:</span>
                  <code className="bg-background px-2 py-0.5 rounded text-xs font-mono">
                    {conflict?.serverVersion || ''}
                  </code>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">{t('localVersion')}:</span>
                  <code className="bg-background px-2 py-0.5 rounded text-xs font-mono">
                    {conflict?.localVersion || ''}
                  </code>
                </div>

                {conflict?.deviceId && (
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">{t('device')}:</span>
                    <span className="font-medium">{conflict.deviceId}</span>
                  </div>
                )}
              </div>

              {showDiff && (
                <div className="mt-4 border rounded-md overflow-hidden text-xs">
                  <div className="bg-muted px-3 py-2 border-b flex justify-between font-medium">
                    <span className="text-red-500">{t('serverVersion')}</span>
                    <span className="text-green-500">{t('localVersion')}</span>
                  </div>
                  <div className="max-h-[300px] overflow-y-auto">
                    <ReactDiffViewer
                      oldValue={oldCode}
                      newValue={newCode}
                      splitView={false}
                      useDarkTheme={resolvedTheme === 'dark'}
                      hideLineNumbers={true}
                    />
                  </div>
                </div>
              )}

              <div className="text-sm text-muted-foreground pt-2">
                {t('keepLocalDesc')} <span className="font-semibold">({t('keepLocal')})</span>
                <br />
                {t('useServerDesc')} <span className="font-semibold">({t('useServer')})</span>
              </div>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>

        <AlertDialogFooter className="sm:space-x-2">
          <AlertDialogCancel onClick={onUseServer} className="transition-all duration-200 hover:scale-105">
            {t('useServer')}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onKeepLocal}
            className={cn(
              'bg-primary text-primary-foreground hover:bg-primary/90',
              'transition-all duration-200 hover:scale-105 hover:shadow-md',
            )}
          >
            {t('keepLocal')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

export default ConfigConflictDialog;
