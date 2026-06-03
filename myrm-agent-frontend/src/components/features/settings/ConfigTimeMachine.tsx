/**
 * [INPUT] '@/components/primitives/button'::Button (POS: UI 基础组件)
 * [INPUT] '@/components/primitives/dialog'::Dialog (POS: UI 基础组件)
 * [OUTPUT] ConfigTimeMachine: 配置时光机组件，展示配置历史记录并支持一键回滚。
 * [POS] 设置页通用组件。提供企业级配置审计和防手残恢复能力。
 */
import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/primitives/dialog';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { WorkHistoryIcon, Clock01Icon } from 'hugeicons-react';
import { toast } from 'sonner';
import { format } from 'date-fns';

interface ConfigHistoryRecord {
  id: string;
  version: string;
  previous_value: Record<string, unknown> | null;
  new_value: Record<string, unknown>;
  device_id: string;
  created_at: string;
}

interface ConfigTimeMachineProps {
  configKey: string;
  onRestore: (newValue: Record<string, unknown>) => void;
}

function resolveConfigFieldLabel(
  translate: (key: string) => string,
  hasKey: (key: string) => boolean,
  key: string,
): string {
  if (!hasKey(key)) return key;
  const label = translate(key);
  if (!label || label === `settings.${key}`) return key;
  return label;
}

export const ConfigTimeMachine: React.FC<ConfigTimeMachineProps> = ({ configKey, onRestore }) => {
  const t = useTranslations('settings.configTimeMachine');
  const tSettings = useTranslations('settings');
  const tCommon = useTranslations('common');
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<ConfigHistoryRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);

  const hasSettingsKey = (key: string) => tSettings.has(key as Parameters<typeof tSettings.has>[0]);
  const translateSettings = (key: string) => tSettings(key as Parameters<typeof tSettings>[0]);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/config/${configKey}/history`);
      if (!res.ok) throw new Error('Failed to fetch history');
      const data = await res.json();
      setHistory(data);
    } catch (error) {
      console.error('History fetch error:', error);
      toast.error(t('loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleOpenChange = (isOpen: boolean) => {
    setOpen(isOpen);
    if (isOpen) {
      fetchHistory();
    }
  };

  const handleRestore = async (record: ConfigHistoryRecord) => {
    setRestoring(record.version);
    try {
      const deviceId = 'web-ui-time-machine';
      const res = await fetch(`/api/v1/config/${configKey}/rollback/${record.version}?device_id=${deviceId}`, {
        method: 'POST',
      });

      if (!res.ok) throw new Error('Failed to rollback');

      const data = await res.json();
      onRestore(data.value);
      toast.success(t('restoreSuccess', { version: record.version }));
      setOpen(false);
    } catch (error) {
      console.error('Rollback error:', error);
      toast.error(t('restoreFailed'));
    } finally {
      setRestoring(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2 h-8">
          <WorkHistoryIcon size={14} />
          <span>{t('button')}</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Clock01Icon size={18} className="text-primary" />
            {t('title')}
          </DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <ScrollArea className="h-[400px] pr-4 mt-4">
          {loading ? (
            <div className="flex h-full items-center justify-center text-muted-foreground">{t('loading')}</div>
          ) : history.length === 0 ? (
            <div className="flex h-full items-center justify-center text-muted-foreground">{t('empty')}</div>
          ) : (
            <div className="space-y-4">
              {history.map((record, index) => {
                const date = new Date(record.created_at);
                const isLatest = index === 0;

                return (
                  <div
                    key={record.id}
                    className={`rounded-lg border p-4 ${isLatest ? 'border-primary/50 bg-primary/5' : 'border-border/40 bg-secondary/20'}`}
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <div className="flex flex-col">
                        <span className="text-sm font-medium">{format(date, 'yyyy-MM-dd HH:mm:ss')}</span>
                        <span className="text-xs text-muted-foreground">
                          {t('versionDevice', { version: record.version, device: record.device_id })}
                        </span>
                      </div>
                      {!isLatest && (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleRestore(record)}
                          disabled={restoring === record.version}
                        >
                          {restoring === record.version ? t('restoring') : t('restore')}
                        </Button>
                      )}
                      {isLatest && (
                        <span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-medium text-primary">
                          {t('currentVersion')}
                        </span>
                      )}
                    </div>

                    <div className="mt-3 overflow-x-auto rounded bg-background/50 p-3 font-mono text-[11px] text-muted-foreground/90">
                      {Object.entries(record.new_value).map(([k, v]) => {
                        const fieldLabel = resolveConfigFieldLabel(translateSettings, hasSettingsKey, k);
                        const displayValue = typeof v === 'boolean' ? (v ? tCommon('yes') : tCommon('no')) : String(v);

                        return (
                          <div key={k} className="flex gap-2">
                            <span className="font-semibold text-primary/70">{fieldLabel}:</span>
                            <span>{displayValue}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
};
