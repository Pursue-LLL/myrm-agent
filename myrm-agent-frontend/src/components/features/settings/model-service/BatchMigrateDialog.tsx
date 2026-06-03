import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Loader2, ArrowRight } from 'lucide-react';
import { batchMigrateProvider, previewBatchMigrateProvider, BatchMigratePreviewResponse } from '@/services/provider';
import { toast } from '@/hooks/useToast';
import useProviderStore from '@/store/useProviderStore';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';

interface BatchMigrateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  fromProviderId: string;
  fromProviderName: string;
  onSuccess?: () => void;
}

export const BatchMigrateDialog = memo<BatchMigrateDialogProps>(
  ({ open, onOpenChange, fromProviderId, fromProviderName, onSuccess }) => {
    const t = useTranslations('settings.modelService.migrateProvider');
    const providers = useProviderStore((state) => state.providers);
    const [toProviderId, setToProviderId] = useState<string>('');
    const [toModel, setToModel] = useState<string>('');
    const [preview, setPreview] = useState<BatchMigratePreviewResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [migrating, setMigrating] = useState(false);

    const availableProviders = providers.filter((p) => p.id !== fromProviderId && p.isEnabled);
    const selectedProvider = providers.find((p) => p.id === toProviderId);
    const availableModels = selectedProvider?.enabledModels || [];

    // Load preview when dialog opens
    useEffect(() => {
      if (open && fromProviderId) {
        setLoading(true);
        previewBatchMigrateProvider({
          from_provider_id: fromProviderId,
          to_provider_id: '', // Not needed for preview count only
          to_model: '',
        })
          .then(setPreview)
          .catch((error) => {
            console.error('Failed to get migration preview:', error);
          })
          .finally(() => setLoading(false));
      } else {
        setPreview(null);
        setToProviderId('');
        setToModel('');
      }
    }, [open, fromProviderId]);

    const handleMigrate = async () => {
      if (!toProviderId || !toModel) return;

      try {
        setMigrating(true);
        await batchMigrateProvider({
          from_provider_id: fromProviderId,
          to_provider_id: toProviderId,
          to_model: toModel,
        });

        toast({
          title: t('migrateSuccess'),
          description: t('migrateSuccessDesc', { count: preview?.affected_count || 0 }),
        });

        onOpenChange(false);
        onSuccess?.();
      } catch (error) {
        console.error('Failed to migrate provider:', error);
        toast({
          title: t('migrateFailed'),
          description: error instanceof Error ? error.message : 'Unknown error',
          variant: 'destructive',
        });
      } finally {
        setMigrating(false);
      }
    };

    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[450px]">
          <DialogHeader>
            <DialogTitle>{t('title', { name: fromProviderName })}</DialogTitle>
            <DialogDescription>{t('description')}</DialogDescription>
          </DialogHeader>

          <div className="py-4 space-y-4">
            {loading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : preview?.affected_count === 0 ? (
              <p className="text-sm text-muted-foreground">{t('noAgentsToMigrate')}</p>
            ) : (
              <>
                <div className="space-y-4">
                  <div className="space-y-2">
                    <label className="text-sm font-medium">{t('selectTargetProvider')}</label>
                    <Select value={toProviderId} onValueChange={setToProviderId}>
                      <SelectTrigger>
                        <SelectValue placeholder={t('selectProviderPlaceholder')} />
                      </SelectTrigger>
                      <SelectContent>
                        {availableProviders.map((p) => (
                          <SelectItem key={p.id} value={p.id}>
                            {p.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium">{t('selectTargetModel')}</label>
                    <Select value={toModel} onValueChange={setToModel} disabled={!toProviderId}>
                      <SelectTrigger>
                        <SelectValue placeholder={t('selectModelPlaceholder')} />
                      </SelectTrigger>
                      <SelectContent>
                        {availableModels.map((m) => (
                          <SelectItem key={m} value={m}>
                            {m}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="max-h-[200px] overflow-y-auto rounded-full border p-3 text-sm bg-muted/30">
                  <p className="font-medium mb-2">{t('affectedAgents', { count: preview?.affected_count })}</p>
                  <ul className="space-y-2">
                    {preview?.affected_agents.map((agent) => (
                      <li
                        key={agent.id}
                        className="flex items-center justify-between border-b pb-2 last:border-0 last:pb-0"
                      >
                        <span className="font-medium">{agent.name}</span>
                        <div className="flex items-center text-xs text-muted-foreground">
                          <span>{agent.current_model || 'none'}</span>
                          {toModel && (
                            <>
                              <ArrowRight className="h-3 w-3 mx-1" />
                              <span className="text-primary">{toModel}</span>
                            </>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              </>
            )}
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={migrating}>
              {t('cancel')}
            </Button>
            <Button
              onClick={handleMigrate}
              disabled={migrating || loading || preview?.affected_count === 0 || !toProviderId || !toModel}
            >
              {migrating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('migrate')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  },
);

BatchMigrateDialog.displayName = 'BatchMigrateDialog';
