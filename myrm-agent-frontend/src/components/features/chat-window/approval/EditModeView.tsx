'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Pencil } from 'lucide-react';

import { Button } from '@/components/primitives/button';
import { Textarea } from '@/components/primitives/textarea';
import { Label } from '@/components/primitives/label';
import { Input } from '@/components/primitives/input';
import { Checkbox } from '@/components/primitives/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import type { AllowAlwaysScope } from '@/lib/approval/allowAlwaysScope';
import { deriveCommandPattern } from '@/lib/approval/shellCommandDisplay';

interface EditModeViewProps {
  editedArgs: Record<string, string>;
  setEditedArgs: (args: Record<string, string>) => void;
  inputEntries: Array<[string, unknown]>;
  isSingleStringParam: boolean;
  editValidationErrors: string[];
  allowAlwaysInEdit: boolean;
  setAllowAlwaysInEdit: (checked: boolean) => void;
  allowAlwaysScopeInEdit: AllowAlwaysScope;
  setAllowAlwaysScopeInEdit: (scope: AllowAlwaysScope) => void;
  permissionTypeLabel: string;
  toolName: string;
  shellCommand?: string;
  requestId: string;
  onConfirm: () => void;
  onCancel: () => void;
  isLoading: boolean;
}

export default function EditModeView({
  editedArgs,
  setEditedArgs,
  inputEntries,
  isSingleStringParam,
  editValidationErrors,
  allowAlwaysInEdit,
  setAllowAlwaysInEdit,
  allowAlwaysScopeInEdit,
  setAllowAlwaysScopeInEdit,
  permissionTypeLabel,
  toolName,
  shellCommand = '',
  requestId,
  onConfirm,
  onCancel,
  isLoading,
}: EditModeViewProps) {
  const t = useTranslations('toolApproval');
  const effectiveShellCommand = useMemo(() => {
    if (isSingleStringParam && inputEntries[0]) {
      const edited = editedArgs[inputEntries[0][0]];
      if (typeof edited === 'string' && edited.trim()) {
        return edited;
      }
    }
    return shellCommand;
  }, [editedArgs, inputEntries, isSingleStringParam, shellCommand]);
  const patternPreview = useMemo(
    () => (effectiveShellCommand ? deriveCommandPattern(effectiveShellCommand) : null),
    [effectiveShellCommand],
  );
  const patternConfirmBlocked =
    allowAlwaysInEdit &&
    allowAlwaysScopeInEdit === 'pattern' &&
    effectiveShellCommand.trim().length > 0 &&
    patternPreview === null;

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Pencil className="h-4 w-4 text-blue-500" />
        {t('editTitle')}
      </div>
      <div className="space-y-2">
        {isSingleStringParam ? (
          <Textarea
            value={editedArgs[inputEntries[0][0]] ?? ''}
            onChange={(e) => setEditedArgs({ ...editedArgs, [inputEntries[0][0]]: e.target.value })}
            className="font-mono text-xs min-h-[80px]"
            autoFocus
          />
        ) : (
          inputEntries.map(([key]) => (
            <div key={key} className="space-y-1">
              <Label className="text-xs font-mono">{key}</Label>
              <Input
                value={editedArgs[key] ?? ''}
                onChange={(e) => setEditedArgs({ ...editedArgs, [key]: e.target.value })}
                className={`font-mono text-xs ${editValidationErrors.includes(key) ? 'border-destructive' : ''}`}
              />
            </div>
          ))
        )}
      </div>
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Checkbox
            id={`allow-always-${requestId}`}
            checked={allowAlwaysInEdit}
            onCheckedChange={(checked) => setAllowAlwaysInEdit(!!checked)}
          />
          <Label htmlFor={`allow-always-${requestId}`} className="cursor-pointer text-amber-600 hover:text-amber-700">
            {t('allowAlwaysAfterEdit')}
          </Label>
        </div>

        {allowAlwaysInEdit && (
          <div className="ml-6 space-y-1">
            <Select
              value={allowAlwaysScopeInEdit}
              onValueChange={(v) => setAllowAlwaysScopeInEdit(v as AllowAlwaysScope)}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="exact">{t('allowAlwaysConfirm.scopeExact')}</SelectItem>
                <SelectItem value="pattern">{t('allowAlwaysConfirm.scopePattern')}</SelectItem>
                <SelectItem value="tool">{t('allowAlwaysConfirm.scopeTool')}</SelectItem>
                <SelectItem value="permission">{t('allowAlwaysConfirm.scopePermission')}</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-[10px] text-muted-foreground">
              {allowAlwaysScopeInEdit === 'permission' &&
                t('allowAlwaysConfirm.scopePermissionDesc', {
                  permissionType: permissionTypeLabel,
                })}
              {allowAlwaysScopeInEdit === 'tool' && t('allowAlwaysConfirm.scopeToolDesc', { toolName })}
              {allowAlwaysScopeInEdit === 'exact' && t('allowAlwaysConfirm.scopeExactDesc')}
              {allowAlwaysScopeInEdit === 'pattern' && t('allowAlwaysConfirm.scopePatternDesc')}
            </p>
            {allowAlwaysScopeInEdit === 'pattern' && effectiveShellCommand && (
              <p className="text-[10px]">
                {patternPreview ? (
                  <span className="font-mono text-foreground/80">
                    {t('allowAlwaysConfirm.scopePatternPreview', { pattern: patternPreview })}
                  </span>
                ) : (
                  <span className="text-destructive">{t('allowAlwaysConfirm.scopePatternUnavailable')}</span>
                )}
              </p>
            )}
          </div>
        )}
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={onConfirm} disabled={isLoading || patternConfirmBlocked}>
          {t('confirmEdit')}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={isLoading}>
          {t('cancel')}
        </Button>
      </div>
    </div>
  );
}
