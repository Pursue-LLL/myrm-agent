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
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { getProviderUsage, ProviderUsageResponse } from '@/services/provider';
import { toast } from '@/hooks/useToast';

interface DeleteProviderDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  providerId: string;
  providerName: string;
  onConfirm: (force: boolean) => Promise<void>;
}

export const DeleteProviderDialog = memo<DeleteProviderDialogProps>(
  ({ open, onOpenChange, providerId, providerName, onConfirm }) => {
    const t = useTranslations('settings.modelService.deleteProvider');
    const [usage, setUsage] = useState<ProviderUsageResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [confirming, setConfirming] = useState(false);

    useEffect(() => {
      if (open && providerId) {
        setLoading(true);
        getProviderUsage(providerId)
          .then(setUsage)
          .catch((error) => {
            console.error('Failed to get provider usage:', error);
            toast({
              title: t('checkFailed'),
              description: error.message,
              variant: 'destructive',
            });
          })
          .finally(() => setLoading(false));
      } else {
        setUsage(null);
      }
    }, [open, providerId, t]);

    const handleConfirm = async (force: boolean) => {
      try {
        setConfirming(true);
        await onConfirm(force);
        onOpenChange(false);
      } catch (error) {
        console.error('Failed to delete provider:', error);
        toast({
          title: t('deleteFailed'),
          description: error instanceof Error ? error.message : 'Unknown error',
          variant: 'destructive',
        });
      } finally {
        setConfirming(false);
      }
    };

    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>{t('title', { name: providerName })}</DialogTitle>
            <DialogDescription>{t('description')}</DialogDescription>
          </DialogHeader>

          <div className="py-4">
            {loading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : usage?.has_usage ? (
              <div className="space-y-4">
                <Alert className="border-warning/50 bg-warning/10 text-warning-foreground">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertTitle>{t('warningTitle')}</AlertTitle>
                  <AlertDescription>{t('warningDescription', { count: usage.count })}</AlertDescription>
                </Alert>
                <div className="max-h-[200px] overflow-y-auto rounded-full border p-2 text-sm bg-muted/30">
                  <ul className="list-disc pl-4 space-y-1">
                    {usage.agents.map((agent) => (
                      <li key={agent.id}>
                        <span className="font-medium">{agent.name}</span>
                        {agent.model && <span className="text-muted-foreground ml-1">({agent.model})</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t('safeToDelete')}</p>
            )}
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={confirming}>
              {t('cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={() => handleConfirm(!!usage?.has_usage)}
              disabled={confirming || loading}
            >
              {confirming && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {usage?.has_usage ? t('forceDelete') : t('delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  },
);

DeleteProviderDialog.displayName = 'DeleteProviderDialog';
