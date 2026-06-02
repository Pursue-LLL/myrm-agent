'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { IconFolder } from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';

export default function MemoryArchivalSection() {
  const t = useTranslations('settings.memoryArchival');
  const [archiving, setArchiving] = useState(false);

  const runArchival = async () => {
    try {
      setArchiving(true);
      const response = await fetch('/api/v1/memory/archival/auto', {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Failed to run archival');
      const data = await response.json();
      if (data.archived_count > 0) {
        toast.success(
          t('archiveSuccess', { count: data.archived_count }) || `Archived ${data.archived_count} memories`,
        );
      } else {
        toast.info(t('noMemoriesToArchive') || 'No memories eligible for archival');
      }
    } catch (error) {
      toast.error(t('archiveError') || 'Failed to run archival');
      console.error('Archival error:', error);
    } finally {
      setArchiving(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t('title') || 'Memory Archival'}</CardTitle>
          <CardDescription>
            {t('description') || 'Automatically archive old, rarely-accessed memories to improve search performance.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border p-4 space-y-2">
            <h4 className="font-medium">{t('criteriaTitle') || 'Archival Criteria'}</h4>
            <ul className="text-sm text-muted-foreground space-y-1 ml-4 list-disc">
              <li>{t('criteriaAge') || 'Memory age ≥ 180 days (6 months)'}</li>
              <li>{t('criteriaAccess') || 'Access count ≤ 5 times'}</li>
              <li>{t('criteriaImportance') || 'Importance ≤ 0.3 (low priority)'}</li>
            </ul>
            <p className="text-sm text-muted-foreground mt-2">
              {t('criteriaNote') || 'All criteria must be met for a memory to be archived.'}
            </p>
          </div>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button disabled={archiving} className="w-full">
                <IconFolder className="mr-2 h-4 w-4" />
                {archiving ? t('archiving') || 'Archiving...' : t('runArchival') || 'Run Archival'}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t('confirmTitle') || 'Run Memory Archival'}</AlertDialogTitle>
                <AlertDialogDescription>
                  {t('confirmDescription') ||
                    'This will move old, rarely-accessed memories to archival storage. Archived memories can be searched and restored anytime.'}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('cancel') || 'Cancel'}</AlertDialogCancel>
                <AlertDialogAction onClick={runArchival}>{t('confirm') || 'Confirm'}</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('benefitsTitle') || 'Benefits'}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="text-sm text-muted-foreground space-y-2 ml-4 list-disc">
            <li>{t('benefit1') || 'Improved search performance by reducing active corpus size'}</li>
            <li>{t('benefit2') || 'Reduced BM25 index size for faster keyword matching'}</li>
            <li>{t('benefit3') || 'Historical data preserved without deletion'}</li>
            <li>{t('benefit4') || 'Archived memories remain searchable via dedicated API'}</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
