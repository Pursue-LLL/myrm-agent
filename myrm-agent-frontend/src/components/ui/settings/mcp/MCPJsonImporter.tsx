import { IconUpload, IconX } from '@/components/ui/icons/PremiumIcons';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';

interface MCPJsonImporterProps {
  show: boolean;
  importJsonText: string;
  importError: string;
  importPlaceholder: string;
  supportsStdio: boolean;
  onImportJsonTextChange: (value: string) => void;
  onImport: () => void;
  onCancel: () => void;
}

export function MCPJsonImporter({
  show,
  importJsonText,
  importError,
  importPlaceholder,
  supportsStdio,
  onImportJsonTextChange,
  onImport,
  onCancel,
}: MCPJsonImporterProps) {
  const t = useTranslations('settings');

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-background rounded-2xl max-w-2xl w-full mx-4 shadow-xl overflow-hidden">
        {/* 弹窗头部 */}
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <IconUpload className="w-[18px] h-[18px] text-primary" />
            </div>
            <h3 className="text-lg font-semibold text-foreground">{t('mcpImportTitle')}</h3>
          </div>
          <button onClick={onCancel} className="p-2 rounded-lg hover:bg-muted transition-colors">
            <IconX className="w-[18px] h-[18px] text-muted-foreground" />
          </button>
        </div>

        {/* 弹窗内容 */}
        <div className="p-5 space-y-4">
          <p className="text-sm text-muted-foreground">
            {supportsStdio ? t('mcpImportDescription') : t('mcpImportDescriptionSandbox')}
          </p>

          <textarea
            value={importJsonText}
            onChange={(e) => {
              onImportJsonTextChange(e.target.value);
            }}
            className={cn(
              'w-full h-80 px-4 py-3 rounded-xl resize-none font-mono text-sm',
              'bg-muted/30 border border-border/50',
              'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
              'placeholder:text-muted-foreground/50',
              importError && 'border-destructive focus:ring-destructive/20',
            )}
            placeholder={importPlaceholder}
          />

          {importError && (
            <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg">
              <p className="text-sm text-destructive">{importError}</p>
            </div>
          )}
        </div>

        {/* 弹窗底部 */}
        <div className="flex justify-end gap-3 p-5 border-t border-border bg-muted/20">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-muted-foreground hover:bg-muted rounded-lg transition-colors"
          >
            {t('mcpCancel')}
          </button>
          <button
            onClick={onImport}
            className="px-4 py-2 text-sm bg-primary text-white hover:bg-primary/90 rounded-lg transition-colors"
          >
            {t('mcpImportButton')}
          </button>
        </div>
      </div>
    </div>
  );
}
