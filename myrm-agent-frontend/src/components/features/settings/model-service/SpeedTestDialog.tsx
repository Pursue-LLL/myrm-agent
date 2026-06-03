'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Loader2, RotateCw } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { type ModelConfig, type SpeedTestResult, runSpeedTest } from '@/services/llm-config';

type TestState = 'idle' | 'testing' | 'done';

interface ModelTestItem {
  config: ModelConfig;
  displayName: string;
  result: SpeedTestResult | null;
  state: TestState;
}

interface SpeedTestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  modelConfigs: { config: ModelConfig; displayName: string }[];
}

const SpeedTestDialog = memo<SpeedTestDialogProps>(({ open, onOpenChange, modelConfigs }) => {
  const t = useTranslations('settings.modelService.speedTest');
  const [items, setItems] = useState<ModelTestItem[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  const initItems = useCallback((): ModelTestItem[] => {
    return modelConfigs.map((m) => ({
      config: m.config,
      displayName: m.displayName,
      result: null,
      state: 'idle' as const,
    }));
  }, [modelConfigs]);

  const runAllTests = useCallback(async () => {
    const testItems = initItems();
    setItems(testItems);
    setIsRunning(true);

    const updatedItems = [...testItems];

    for (let i = 0; i < updatedItems.length; i++) {
      updatedItems[i] = { ...updatedItems[i], state: 'testing' };
      setItems([...updatedItems]);

      const results = await runSpeedTest([updatedItems[i].config]);
      const result = results[0] ?? null;

      updatedItems[i] = { ...updatedItems[i], result, state: 'done' };
      setItems([...updatedItems]);
    }

    setIsRunning(false);
  }, [initItems]);

  const retestSingle = useCallback(async (index: number) => {
    let config: ModelConfig | undefined;
    setItems((prev) => {
      const next = [...prev];
      config = next[index]?.config;
      next[index] = { ...next[index], state: 'testing', result: null };
      return next;
    });

    if (!config) return;
    const results = await runSpeedTest([config]);
    const result = results[0] ?? null;

    setItems((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], result, state: 'done' };
      return next;
    });
  }, []);

  const handleOpenChange = useCallback(
    (value: boolean) => {
      if (!isRunning) {
        onOpenChange(value);
        if (!value) {
          setItems([]);
        }
      }
    },
    [isRunning, onOpenChange],
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        {modelConfigs.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">{t('noModels')}</p>
        ) : (
          <div className="space-y-4 py-2">
            <Button onClick={runAllTests} disabled={isRunning} size="sm" className="w-full">
              {isRunning ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
                  {t('testing')}
                </>
              ) : (
                t('runAll')
              )}
            </Button>

            <div className="space-y-2">
              {items.map((item, idx) => (
                <div
                  key={`${item.config.model}-${idx}`}
                  className="flex items-center justify-between p-3 rounded-lg border border-border/50 bg-background/50"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">{item.displayName}</p>
                    {item.state === 'done' && item.result && (
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
                        {item.result.status === 'ok' ? (
                          <>
                            <span className="text-xs text-muted-foreground">
                              {t('ttft')}{' '}
                              <span className="font-mono font-semibold text-foreground">{item.result.ttft_ms}ms</span>
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {t('tps')}{' '}
                              <span className="font-mono font-semibold text-foreground">
                                {item.result.throughput_tps}/s
                              </span>
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {item.result.total_tokens} {t('tokens')}
                            </span>
                          </>
                        ) : (
                          <span className="text-xs text-destructive truncate">{item.result.error}</span>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2 ml-3">
                    {item.state === 'testing' && <Loader2 className="w-4 h-4 animate-spin text-primary" />}
                    {item.state === 'done' && (
                      <>
                        <span
                          className={cn(
                            'text-xs font-medium px-1.5 py-0.5 rounded',
                            item.result?.status === 'ok'
                              ? 'bg-emerald-500/10 text-emerald-600'
                              : 'bg-destructive/10 text-destructive',
                          )}
                        >
                          {item.result?.status === 'ok' ? t('statusOk') : t('statusError')}
                        </span>
                        <button
                          onClick={() => retestSingle(idx)}
                          disabled={isRunning}
                          className="p-1 rounded hover:bg-muted transition-colors"
                          title={t('retest')}
                        >
                          <RotateCw className="w-3.5 h-3.5 text-muted-foreground" />
                        </button>
                      </>
                    )}
                    {item.state === 'idle' && (
                      <span className="text-xs text-muted-foreground">{t('statusPending')}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
});

SpeedTestDialog.displayName = 'SpeedTestDialog';

export default SpeedTestDialog;
