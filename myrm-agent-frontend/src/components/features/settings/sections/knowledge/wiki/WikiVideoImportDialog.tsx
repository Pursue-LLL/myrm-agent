'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { wikiService, type ImportVideoResponse } from '@/services/wikiService';

interface WikiVideoImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentScopeId?: string | null;
  onImportFinished: (result: ImportVideoResponse) => void;
}

export function isValidVideoUrl(url: string): boolean {
  const trimmed = url.trim();
  if (!trimmed) return false;
  const isBili = /(?:bilibili\.com\/video\/|b23\.tv\/)/i.test(trimmed);
  const isYt = /(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)/i.test(trimmed);
  return isBili || isYt;
}

export function WikiVideoImportDialog({
  open,
  onOpenChange,
  agentScopeId,
  onImportFinished,
}: WikiVideoImportDialogProps) {
  const t = useTranslations('settings.wiki.import');
  const [videoUrl, setVideoUrl] = useState('');
  const [folderPath, setFolderPath] = useState('videos');
  const [windowDuration, setWindowDuration] = useState('45');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleClose = () => {
    if (isSubmitting) return;
    setVideoUrl('');
    setFolderPath('videos');
    setWindowDuration('45');
    onOpenChange(false);
  };

  const handleSubmit = async () => {
    const trimmedUrl = videoUrl.trim();
    if (!trimmedUrl) {
      toast.error(t('videoUrlEmptyError'));
      return;
    }

    if (!isValidVideoUrl(trimmedUrl)) {
      toast.error(t('videoUrlEmptyError'));
      return;
    }

    const durationNum = parseInt(windowDuration, 10);
    const validDuration = Number.isFinite(durationNum) && durationNum >= 10 && durationNum <= 300 ? durationNum : 45;

    setIsSubmitting(true);
    try {
      const res = await wikiService.importVideo(
        {
          url: trimmedUrl,
          folder_path: folderPath.trim() || 'videos',
          window_duration_seconds: validDuration,
          auto_compile: true,
        },
        agentScopeId,
      );

      if (res.success) {
        toast.success(t('videoImportSuccess'));
        onImportFinished(res);
        handleClose();
      } else {
        toast.error(res.error || res.message || t('importFailed'));
      }
    } catch (err) {
      console.error('Video import failed:', err);
      toast.error(t('importFailed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : handleClose())}>
      <DialogContent className="w-[calc(100vw-2rem)] max-w-[560px] sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{t('videoImportTitle')}</DialogTitle>
          <DialogDescription>{t('videoImportDescription')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t('video')} URL</label>
            <Input
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
              placeholder={t('videoUrlPlaceholder')}
              disabled={isSubmitting}
              className="text-sm"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t('videoFolderLabel')}</label>
              <Input
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                placeholder={t('videoFolderPlaceholder')}
                disabled={isSubmitting}
                className="text-xs"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t('videoWindowDuration')}</label>
              <Input
                type="number"
                min={10}
                max={300}
                value={windowDuration}
                onChange={(e) => setWindowDuration(e.target.value)}
                placeholder="45"
                disabled={isSubmitting}
                className="text-xs"
              />
            </div>
          </div>
        </div>

        <DialogFooter className="flex flex-row justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={handleClose} disabled={isSubmitting}>
            {useTranslations('common')('cancel')}
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={isSubmitting || !videoUrl.trim()}>
            {isSubmitting ? t('videoImporting') : t('videoImportStart')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
