'use client';

import { memo, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';

export interface WorkflowTemplateArgsDialogProps {
  open: boolean;
  templateName: string;
  placeholders: string[];
  onOpenChange: (open: boolean) => void;
  onConfirm: (args: Record<string, string>) => void;
}

const WorkflowTemplateArgsDialog = memo(
  ({
    open,
    templateName,
    placeholders,
    onOpenChange,
    onConfirm,
  }: WorkflowTemplateArgsDialogProps) => {
    const t = useTranslations('settings.skills.workflowTemplates');
    const [values, setValues] = useState<Record<string, string>>({});

    const sortedPlaceholders = useMemo(() => [...placeholders], [placeholders]);

    useEffect(() => {
      if (!open) {
        return;
      }
      setValues(Object.fromEntries(sortedPlaceholders.map((key) => [key, ''])));
    }, [open, sortedPlaceholders]);

    const allFilled = sortedPlaceholders.every((key) => values[key]?.trim());

    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('argsDialogTitle', { name: templateName })}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{t('argsDialogDescription')}</p>
          <div className="space-y-3 py-1">
            {sortedPlaceholders.map((key) => (
              <div key={key} className="space-y-1.5">
                <Label htmlFor={`wf-arg-${key}`} className="text-xs">
                  {key}
                </Label>
                <Input
                  id={`wf-arg-${key}`}
                  value={values[key] ?? ''}
                  onChange={(event) =>
                    setValues((prev) => ({ ...prev, [key]: event.target.value }))
                  }
                  placeholder={t('argsFieldPlaceholder', { key })}
                />
              </div>
            ))}
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t('argsCancel')}
            </Button>
            <Button
              type="button"
              disabled={!allFilled}
              onClick={() => {
                const args = Object.fromEntries(
                  sortedPlaceholders.map((key) => [key, values[key]?.trim() ?? '']),
                );
                onConfirm(args);
                onOpenChange(false);
              }}
            >
              {t('argsConfirmRun')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  },
);

WorkflowTemplateArgsDialog.displayName = 'WorkflowTemplateArgsDialog';

export default WorkflowTemplateArgsDialog;
