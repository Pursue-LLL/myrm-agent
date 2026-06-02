'use client';

import { useTranslations } from 'next-intl';
import { Hand, CheckCircle2, X } from 'lucide-react';

import { Button } from '@/components/ui/button';

interface HandoverModeViewProps {
  prompt: string;
  onApprove: () => void;
  onReject: () => void;
  isLoading: boolean;
}

export default function HandoverModeView({ prompt, onApprove, onReject, isLoading }: HandoverModeViewProps) {
  const t = useTranslations('toolApproval');

  return (
    <div className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-4">
      <div className="flex items-center gap-2">
        <Hand className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium text-primary">{t('handoverTitle')}</span>
      </div>

      {prompt && <p className="text-sm text-foreground">{prompt}</p>}

      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={onApprove} disabled={isLoading}>
          <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
          {t('handoverDone')}
        </Button>
        <Button size="sm" variant="outline" onClick={onReject} disabled={isLoading}>
          <X className="mr-1 h-3.5 w-3.5" />
          {t('cancel')}
        </Button>
      </div>
    </div>
  );
}
