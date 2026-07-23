'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { ShieldAlert } from 'lucide-react';

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
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import type { AllowAlwaysScope } from '@/lib/approval/allowAlwaysScope';
import { deriveCommandPattern } from '@/lib/approval/shellCommandDisplay';

interface AllowAlwaysConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  allowAlwaysScope: AllowAlwaysScope;
  setAllowAlwaysScope: (scope: AllowAlwaysScope) => void;
  permissionTypeLabel: string;
  toolName: string;
  shellCommand?: string;
  onConfirm: () => void;
  isLoading: boolean;
}

export default function AllowAlwaysConfirmDialog({
  open,
  onOpenChange,
  allowAlwaysScope,
  setAllowAlwaysScope,
  permissionTypeLabel,
  toolName,
  shellCommand = '',
  onConfirm,
  isLoading,
}: AllowAlwaysConfirmDialogProps) {
  const t = useTranslations('toolApproval');
  const patternPreview = useMemo(
    () => (shellCommand ? deriveCommandPattern(shellCommand) : null),
    [shellCommand],
  );
  const patternConfirmBlocked =
    allowAlwaysScope === 'pattern' && shellCommand.trim().length > 0 && patternPreview === null;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-amber-500" />
            {t('allowAlwaysConfirm.title')}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="text-sm text-muted-foreground space-y-3">
              <span>{t('allowAlwaysConfirm.description', { permissionType: permissionTypeLabel })}</span>
              <div className="rounded-md border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 p-3 text-xs">
                <div className="flex items-start gap-2">
                  <ShieldAlert className="h-4 w-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
                  <div className="space-y-1 text-amber-900 dark:text-amber-100">
                    <span className="font-medium block">{t('allowAlwaysConfirm.warning')}</span>
                    <ul className="list-disc list-inside space-y-1 text-amber-800 dark:text-amber-200">
                      <li>{t('allowAlwaysConfirm.risk1')}</li>
                      <li>{t('allowAlwaysConfirm.risk2')}</li>
                      <li>{t('allowAlwaysConfirm.risk3')}</li>
                    </ul>
                  </div>
                </div>
              </div>

              <div className="space-y-2 pt-2">
                <Label htmlFor="allowlist-scope" className="text-sm font-medium">
                  {t('allowAlwaysConfirm.scopeLabel')}
                </Label>
                <Select value={allowAlwaysScope} onValueChange={(v) => setAllowAlwaysScope(v as AllowAlwaysScope)}>
                  <SelectTrigger id="allowlist-scope">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="exact">{t('allowAlwaysConfirm.scopeExact')}</SelectItem>
                    <SelectItem value="pattern">{t('allowAlwaysConfirm.scopePattern')}</SelectItem>
                    <SelectItem value="tool">{t('allowAlwaysConfirm.scopeTool')}</SelectItem>
                    <SelectItem value="permission">{t('allowAlwaysConfirm.scopePermission')}</SelectItem>
                  </SelectContent>
                </Select>
                <span className="text-xs text-muted-foreground block">
                  {allowAlwaysScope === 'permission' &&
                    t('allowAlwaysConfirm.scopePermissionDesc', {
                      permissionType: permissionTypeLabel,
                    })}
                  {allowAlwaysScope === 'tool' && t('allowAlwaysConfirm.scopeToolDesc', { toolName })}
                  {allowAlwaysScope === 'exact' && t('allowAlwaysConfirm.scopeExactDesc')}
                  {allowAlwaysScope === 'pattern' && t('allowAlwaysConfirm.scopePatternDesc')}
                </span>
                {allowAlwaysScope === 'pattern' && shellCommand && (
                  <span className="text-xs block">
                    {patternPreview ? (
                      <span className="font-mono text-foreground/80">
                        {t('allowAlwaysConfirm.scopePatternPreview', { pattern: patternPreview })}
                      </span>
                    ) : (
                      <span className="text-destructive">{t('allowAlwaysConfirm.scopePatternUnavailable')}</span>
                    )}
                  </span>
                )}
              </div>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={isLoading || patternConfirmBlocked}
            className="bg-amber-600 hover:bg-amber-700"
          >
            {t('allowAlwaysConfirm.confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
