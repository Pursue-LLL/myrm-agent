'use client';

/**
 * [INPUT]
 * - @/services/pricing::ModelPricingItem, ModelPricingResponse, fetchModelPricing (POS: 模型单价数据服务)
 * - @/components/primitives/popover::Popover, PopoverContent, PopoverTrigger (POS: Radix 浮层基础组件)
 *
 * [OUTPUT]
 * - ModelPricingPopover: 点击展示当前模型与主流标杆四维单价矩阵与 Prompt Cache 经济学说明的浮层
 *
 * [POS]
 * 表现层/聊天窗：模型单价透视 Popover，向用户透明呈现真实 API 单价（$/1M）与 Prompt Cache 折扣，打破黑盒。
 */

import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { fetchModelPricing, type ModelPricingItem } from '@/services/pricing';
import { Coins, Zap, HelpCircle } from 'lucide-react';

interface ModelPricingPopoverProps {
  currentModel?: string;
  children: React.ReactNode;
}

export const ModelPricingPopover: React.FC<ModelPricingPopoverProps> = ({ currentModel, children }) => {
  const t = useTranslations('chat.modelPricing');
  const [pricingMap, setPricingMap] = useState<Record<string, ModelPricingItem>>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [open, setOpen] = useState<boolean>(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    let mounted = true;
    setLoading(true);

    fetchModelPricing(currentModel)
      .then((res) => {
        if (mounted) {
          setPricingMap(res.models);
        }
      })
      .catch(() => {
        // 静默降级
      })
      .finally(() => {
        if (mounted) {
          setLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [open, currentModel]);

  const activeItem = currentModel ? pricingMap[currentModel] : undefined;
  const otherItems = Object.values(pricingMap).filter((item) => !currentModel || item.model !== currentModel);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent
        align="start"
        side="top"
        sideOffset={8}
        className="w-96 p-4 rounded-xl shadow-xl bg-popover/95 backdrop-blur-md border border-border/80 text-xs"
      >
        <div className="space-y-3">
          <div className="flex items-center justify-between border-b pb-2 border-border/60">
            <div className="flex items-center gap-1.5 font-semibold text-foreground text-sm">
              <Coins className="w-4 h-4 text-amber-500" />
              <span>{t('title')}</span>
            </div>
            <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{t('sourceBadge')}</span>
          </div>

          {loading ? (
            <div className="py-6 text-center text-muted-foreground animate-pulse">{t('loading')}</div>
          ) : (
            <>
              {/* 当前选中模型卡片 */}
              {activeItem && (
                <div className="p-2.5 rounded-lg bg-primary/5 border border-primary/20 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-foreground text-xs truncate max-w-[200px]">
                      {activeItem.model}
                    </span>
                    {activeItem.supports_prompt_caching && (
                      <span className="flex items-center gap-0.5 text-[10px] text-emerald-600 dark:text-emerald-400 font-medium bg-emerald-500/10 px-1.5 py-0.5 rounded-full">
                        <Zap className="w-3 h-3 fill-current" />
                        {t('supportsCache')}
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div className="bg-background/80 p-1.5 rounded border border-border/40">
                      <div className="text-muted-foreground text-[10px]">{t('inputPrice')}</div>
                      <div className="font-semibold text-foreground">
                        ${activeItem.input_cost_per_mtoken.toFixed(2)} / 1M
                      </div>
                    </div>
                    <div className="bg-background/80 p-1.5 rounded border border-border/40">
                      <div className="text-muted-foreground text-[10px]">{t('outputPrice')}</div>
                      <div className="font-semibold text-foreground">
                        ${activeItem.output_cost_per_mtoken.toFixed(2)} / 1M
                      </div>
                    </div>
                    {activeItem.cache_read_cost_per_mtoken !== null && (
                      <div className="bg-emerald-50/50 dark:bg-emerald-950/20 p-1.5 rounded border border-emerald-500/20 col-span-2 flex items-center justify-between">
                        <div>
                          <div className="text-emerald-700 dark:text-emerald-300 text-[10px] flex items-center gap-1">
                            <Zap className="w-2.5 h-2.5 fill-current" />
                            {t('cacheReadPrice')}
                          </div>
                          <div className="font-bold text-emerald-600 dark:text-emerald-400">
                            ${activeItem.cache_read_cost_per_mtoken.toFixed(2)} / 1M
                          </div>
                        </div>
                        {activeItem.cache_read_discount !== null && (
                          <div className="text-right">
                            <span className="text-[10px] text-emerald-700 dark:text-emerald-300">{t('savings')}</span>
                            <div className="font-extrabold text-emerald-600 dark:text-emerald-400 text-sm">
                              {(activeItem.cache_read_discount * 100).toFixed(0)}%
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* 主流代表性模型四维单价矩阵 */}
              {otherItems.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
                    <span>{t('compareTitle')}</span>
                  </div>
                  <div className="max-h-40 overflow-y-auto space-y-1 pr-1 select-none text-[10px]">
                    {otherItems.slice(0, 6).map((item) => (
                      <div
                        key={item.model}
                        className="flex items-center justify-between p-1.5 rounded bg-muted/40 hover:bg-muted/70 transition-colors"
                      >
                        <span className="truncate max-w-[140px] font-mono text-foreground">{item.model}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">
                            {t('inPrice', { price: `$${item.input_cost_per_mtoken.toFixed(2)}` })}
                          </span>
                          <span className="text-muted-foreground">
                            {t('outPrice', { price: `$${item.output_cost_per_mtoken.toFixed(2)}` })}
                          </span>
                          {item.cache_read_discount !== null && (
                            <span className="text-emerald-600 font-medium">
                              -{(item.cache_read_discount * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="pt-1 border-t border-border/50 text-[10px] text-muted-foreground flex items-center gap-1">
                <HelpCircle className="w-3 h-3 flex-shrink-0" />
                <span>{t('footnote')}</span>
              </div>
            </>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
};
