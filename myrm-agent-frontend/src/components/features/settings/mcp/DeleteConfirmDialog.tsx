import { useTranslations } from 'next-intl';

interface DeleteConfirmDialogProps {
  show: boolean;
  configName: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DeleteConfirmDialog({ show, configName, onConfirm, onCancel }: DeleteConfirmDialogProps) {
  const t = useTranslations('settings');

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-background rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
        <h3 className="text-lg font-medium text-black/90 dark:text-white/90 mb-2">{t('mcpDeleteConfirmTitle')}</h3>
        <p className="text-sm text-black/70 dark:text-white/70 mb-4">
          {t('mcpDeleteConfirmMessage', { name: configName })}
        </p>
        <div className="flex justify-end space-x-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-black/70 dark:text-white/70 hover:bg-muted dark:hover:bg-muted rounded-lg transition-colors"
          >
            {t('mcpCancel')}
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm bg-red-500 text-white hover:bg-red-600 rounded-lg transition-colors"
          >
            {t('mcpConfirmDelete')}
          </button>
        </div>
      </div>
    </div>
  );
}
