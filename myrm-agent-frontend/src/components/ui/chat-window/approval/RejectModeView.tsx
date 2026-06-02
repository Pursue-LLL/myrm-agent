'use client';

import { useTranslations } from 'next-intl';
import { MessageSquareX } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

interface RejectModeViewProps {
  feedback: string;
  setFeedback: (feedback: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
  isLoading: boolean;
}

export default function RejectModeView({ feedback, setFeedback, onConfirm, onCancel, isLoading }: RejectModeViewProps) {
  const t = useTranslations('toolApproval');

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <MessageSquareX className="h-4 w-4 text-destructive" />
        {t('rejectTitle')}
      </div>
      <Textarea
        placeholder={t('feedbackPlaceholder')}
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        className="min-h-[60px] text-sm"
        autoFocus
      />
      <div className="flex gap-2">
        <Button size="sm" variant="destructive" onClick={onConfirm} disabled={isLoading}>
          {t('confirmReject')}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={isLoading}>
          {t('cancel')}
        </Button>
      </div>
    </div>
  );
}
