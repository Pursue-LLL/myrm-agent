'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';

import { IconAlertTriangle, IconLoader, IconUpload } from '@/components/features/icons/PremiumIcons';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { useDragDrop } from '@/hooks/ui/useDragDrop';
import { cn } from '@/lib/utils/classnameUtils';

interface PluginImportDropzoneProps {
  isParsing: boolean;
  disabled: boolean;
  error: string | null;
  onFilesSelected: (files: FileList | File[]) => void;
}

/** Drag, click or keyboard target for choosing one plugin ZIP. */
export const PluginImportDropzone = memo(
  ({ isParsing, disabled, error, onFilesSelected }: PluginImportDropzoneProps) => {
    const t = useTranslations('settings.plugins.import');
    const { isDragging, dragHandlers } = useDragDrop({
      onFilesSelected,
      accept: ['application/zip'],
      maxFiles: 1,
      disabled,
    });

    return (
      <label
        className={cn(
          'block cursor-pointer rounded-xl border-2 border-dashed bg-background p-8 text-center transition-colors sm:p-12',
          isDragging && 'border-primary bg-primary/5',
          error && 'border-destructive bg-destructive/5',
          !isDragging && !error && 'border-muted-foreground/25 hover:border-primary/50',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        )}
        {...dragHandlers}
      >
        <input
          type="file"
          accept=".zip"
          className="sr-only"
          disabled={isParsing}
          onChange={(event) => {
            if (event.target.files?.length) {
              onFilesSelected(event.target.files);
            }
          }}
        />
        {isParsing ? (
          <IconLoader className="mx-auto mb-4 h-10 w-10 animate-spin text-primary" />
        ) : (
          <IconUpload className={cn('mx-auto mb-4 h-10 w-10', error ? 'text-destructive' : 'text-muted-foreground')} />
        )}

        <p className="text-base font-medium">{isParsing ? t('upload.parsing') : t('upload.dropHint')}</p>
        <p className="mt-2 text-sm text-muted-foreground">{t('upload.keyboardHint')}</p>
        <p className="mt-1 text-sm text-muted-foreground">{t('upload.formatHint')}</p>

        {error && (
          <Alert variant="destructive" className="mt-6 inline-block text-left">
            <IconAlertTriangle className="h-4 w-4" />
            <AlertTitle>{t('errors.parseTitle')}</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </label>
    );
  },
);
PluginImportDropzone.displayName = 'PluginImportDropzone';
