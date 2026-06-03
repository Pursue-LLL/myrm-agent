/**
 * [INPUT]
 * - @/components/primitives/dialog (POS: 通用弹窗组件)
 * - components/features/memory/MemoryTypeIcon (POS: 记忆类型图标组件)
 * - @/store/memory::MemoryType (POS: 记忆类型定义)
 * - next-intl::useTranslations (POS: 多语言国际化钩子)
 *
 * [OUTPUT]
 * MemoryGuide: 记忆类型说明弹窗（由父组件控制打开/关闭）
 *
 * [POS]
 * 记忆类型参考弹窗。通过设置页入口手动打开，介绍 7 种记忆类型的含义和示例。
 */
'use client';

import { useTranslations } from 'next-intl';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/primitives/dialog';
import { MemoryTypeIcon } from '@/components/features/memory';
import type { MemoryType } from '@/store/memory';
import { cn } from '@/lib/utils/classnameUtils';

const MEMORY_TYPES: MemoryType[] = [
  'profile',
  'semantic',
  'episodic',
  'procedural',
  'conversation',
  'claim',
  'task_digest',
];

interface MemoryGuideProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function MemoryGuide({ open, onOpenChange }: MemoryGuideProps) {
  const t = useTranslations('memory');

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('guide.title')}</DialogTitle>
          <DialogDescription>{t('guide.description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-4">
          {MEMORY_TYPES.map((type) => (
            <div
              key={type}
              className={cn(
                'p-3 rounded-lg border border-border/50',
                'bg-accent/30 hover:bg-accent/50',
                'transition-colors duration-200',
              )}
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5">
                  <MemoryTypeIcon type={type} size={18} />
                </div>
                <div className="flex-1 space-y-1">
                  <div className="font-medium text-sm text-foreground">{t(`types.${type}`)}</div>
                  <div className="text-xs text-muted-foreground">{t(`typeTooltips.${type}.description`)}</div>
                  <div className="text-xs text-muted-foreground/70 pt-1 pl-2 border-l-2 border-border/30">
                    {t(`typeTooltips.${type}.example`)}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        <DialogFooter>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className={cn(
              'w-full sm:w-auto px-4 py-2 rounded-lg',
              'bg-primary text-primary-foreground',
              'hover:bg-primary/90',
              'transition-colors duration-200',
              'font-medium text-sm',
            )}
          >
            {t('guide.gotIt')}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
