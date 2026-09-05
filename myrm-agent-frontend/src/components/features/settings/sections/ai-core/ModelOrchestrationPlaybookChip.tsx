'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Layers, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import dynamic from 'next/dynamic';

const ModelOrchestrationPlaybookDialog = dynamic(
  () => import('./ModelOrchestrationPlaybookDialog'),
  { ssr: false },
);

interface ModelOrchestrationPlaybookChipProps {
  className?: string;
}

export function ModelOrchestrationPlaybookChip({ className }: ModelOrchestrationPlaybookChipProps) {
  const t = useTranslations('settings.modelOrchestrationPlaybook');
  const [open, setOpen] = useState(false);

  return (
    <>
      <div
        data-testid="model-orchestration-playbook-chip"
        onClick={() => setOpen(true)}
        className={cn(
          'group flex items-center justify-between gap-3 px-3.5 py-2 rounded-full border cursor-pointer select-none transition-all duration-200',
          'bg-background/80 hover:bg-accent/50 border-primary/20 hover:border-primary/40 shadow-xs hover:shadow-sm backdrop-blur-md',
          'max-w-screen-md mx-auto',
          className,
        )}
      >
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1 rounded-full bg-primary/10 text-primary shrink-0">
            <Layers className="h-3.5 w-3.5 text-primary" />
          </div>
          <div className="flex items-center gap-2 truncate text-xs">
            <span className="font-semibold text-foreground truncate">{t('chipTitle')}</span>
            <span className="hidden sm:inline text-muted-foreground font-normal truncate">
              · {t('chipSubtitle')}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1 text-xs font-medium text-primary shrink-0">
          <span className="hidden xs:inline">{t('chipAction')}</span>
          <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
        </div>
      </div>

      {open && (
        <ModelOrchestrationPlaybookDialog open={open} onOpenChange={setOpen} />
      )}
    </>
  );
}

export default ModelOrchestrationPlaybookChip;
